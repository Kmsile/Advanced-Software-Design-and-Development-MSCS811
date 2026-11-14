"""Generate and log two bounded test-design requests on local Ollama."""

import argparse
import hashlib
import json
from pathlib import Path
import urllib.request


ROOT = Path(__file__).resolve().parent
MODEL = "qwen3.6:latest"
API = "http://127.0.0.1:11434"
OPTIONS = {"seed": 811, "temperature": 0, "num_ctx": 4096, "num_predict": 2000}


def field(kind, **constraints):
    return {"type": kind, **constraints}


def object_schema(fields):
    return field("object", properties=fields, required=list(fields), additionalProperties=False)


def choices(*values):
    return field("string", enum=list(values))


def three(schema):
    return field("array", items=schema, minItems=3, maxItems=3)


SCHEMA = object_schema({
    "hybrid": three(object_schema({
        "name": field("string"),
        "policy": choices("default", "propagate", "return_html"),
        "html_status": choices("ok", "io"),
        "ocr_status": choices("ok", "io", "runtime", "interrupted"),
        "html_text": field("string"),
        "ocr_text": field("string"),
        "expected_status": choices("return", "html_io", "ocr_io", "ocr_runtime"),
        "expected_text": field("string"),
        "expected_ocr_calls": field("integer", minimum=-1, maximum=1),
    })),
    "html": three(object_schema({
        "name": field("string"),
        "markup": field("string"),
        "expected_text": field("string"),
    })),
})

COMMON = r"""You are drafting unit-test scenarios for two changes to a Java text extractor before those changes are implemented. Produce exactly three hybrid scenarios and exactly three HTML scenarios, following the JSON schema. Use short synthetic examples. These are data records, not Java code.

Contract H1: The hybrid extractor calls the HTML strategy first. On success, it calls OCR once. Its exact successful result is "[HTML]\n" + html_text + "\n[OCR]\n" + ocr_text.
Contract H2: On OCR IOException, default and propagate policies return status ocr_io. The return_html policy yields status return with exact text "[HTML]\n" + html_text.
Contract H3: An HTML IOException returns status html_io and skips OCR. An OCR runtime exception returns ocr_runtime under every policy.
Contract H4: An interrupted OCR call returns ocr_io under every policy and the interrupt status remains set.

For a hybrid case, choose a policy, the status of each mocked strategy and short text for each. expected_status is the result of the combined extraction. Set expected_text to the exact output for status return and an empty string for exception statuses. Set expected_ocr_calls to -1 if the case does not assert the number of calls, otherwise use 0 or 1.

Contract T1: HTML extraction ignores script, style, and noscript elements.
Contract T2: The updated extractor ignores template elements and their contents.
Contract T3: The updated extractor ignores elements that carry the HTML hidden attribute and their contents.
Contract T4: The extractor returns normalized body text, including text of normal nested elements and decoded entities.

For each HTML case supply local, short HTML markup and the exact expected text. Use standalone body examples with harmless labels. No URLs or external resources. An expected string for an empty body is valid. Return only the structured JSON object.
"""

INSTRUCTIONS = {
    "direct": "Choose representative unit-test scenarios for the two changes.",
    "xp_guided": (
        "Apply XP test-first design. Start from the listed acceptance criteria and put the criterion "
        "ID at the beginning of each case name. Use the case budget for distinct observable behaviors. "
        "Include cases that would fail before the new implementation and a relevant boundary or failure "
        "case. Assert exact outcomes and call counts when the contract specifies them."
    ),
}


def get_json(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=10) as response:
        return json.load(response)


def generate(condition, output):
    prompt = COMMON + "\n" + INSTRUCTIONS[condition] + "\n"
    request = {
        "model": MODEL, "prompt": prompt, "format": SCHEMA, "stream": False,
        "think": False, "options": OPTIONS, "keep_alive": "10m",
    }
    (output / f"{condition}_request.json").write_text(
        json.dumps(request, indent=2) + "\n", encoding="utf-8"
    )
    req = urllib.request.Request(
        f"{API}/api/generate", json.dumps(request).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as response:
        raw = response.read()
    (output / f"{condition}_response.json").write_bytes(raw)
    receipt = json.loads(raw)
    cases = json.loads(receipt["response"])
    if not receipt.get("done") or len(cases["hybrid"]) != 3 or len(cases["html"]) != 3:
        raise ValueError(f"Unexpected generation result for {condition}")
    (output / f"{condition}_cases.json").write_text(
        json.dumps(cases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        f'{condition}: six cases, {receipt.get("eval_count")} output tokens, '
        f'{receipt.get("total_duration", 0) / 1_000_000_000:.1f} seconds',
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "regenerated")
    output = parser.parse_args().output
    output.mkdir(parents=True, exist_ok=False)
    model = next(entry for entry in get_json("/api/tags")["models"] if entry["name"] == MODEL)
    details = {
        "server": get_json("/api/version"), "model": model, "options": OPTIONS,
        "protocol_sha256": hashlib.sha256((ROOT / "protocol.md").read_bytes()).hexdigest(),
    }
    (output / "model.json").write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
    for condition in INSTRUCTIONS:
        generate(condition, output)
