"""Replay the fixed request schedule on the local model server."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

from generate_cases import API, COMMON, INSTRUCTIONS, MODEL, SCHEMA, get_json


STUDY = Path(__file__).resolve().parent
SEEDS = tuple(range(812, 836))
SETTINGS = {
    "temperature": 0.6, "top_p": 0.9, "top_k": 40, "num_ctx": 4096, "num_predict": 2000,
}
PILOT_DIGEST = "07d35212591fc27746f0a317c975a6d68754fb38e9053d82e25f06057af28522"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def submit(payload):
    request = Request(
        f"{API}/api/generate", json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=600) as response:
        return response.read()


def generate(output, row):
    seed, condition = row["seed"], row["condition"]
    cell = output / f"seed_{seed}" / condition
    cell.mkdir(parents=True, exist_ok=True)
    terminal = cell / "status.json"
    if terminal.exists():
        return json.loads(terminal.read_text(encoding="utf-8"))
    payload = {
        "model": MODEL,
        "prompt": COMMON + "\n" + INSTRUCTIONS[condition] + "\n",
        "format": SCHEMA, "stream": False, "think": False, "keep_alive": "15m",
        "options": {**SETTINGS, "seed": seed},
    }
    write(cell / "request.json", payload)
    errors = []
    response_path = cell / "response.json"
    if not response_path.exists():
        for attempt in (1, 2):
            try:
                response_path.write_bytes(submit(payload))
                break
            except (URLError, TimeoutError, ConnectionError) as error:
                errors.append({"attempt": attempt, "utc": utc_now(), "detail": str(error)})
                write(cell / "transport_errors.json", errors)
    if not response_path.exists():
        result = {**row, "status": "missing", "transport_errors": len(errors)}
    else:
        try:
            response = json.loads(response_path.read_bytes())
            cases = json.loads(response["response"])
            if not response.get("done") or not isinstance(cases, dict):
                raise ValueError("The response did not contain a completed object")
            write(cell / "cases.json", cases)
            result = {**row, "status": "returned", "done_reason": response.get("done_reason")}
        except (ValueError, TypeError, KeyError) as error:
            result = {**row, "status": "unusable", "detail": str(error)}
    write(terminal, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=STUDY / "new_replication")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    model = next(item for item in get_json("/api/tags")["models"] if item["name"] == MODEL)
    if model["digest"] != PILOT_DIGEST:
        raise SystemExit("The installed local model digest differs from the planned weights.")
    schedule = [
        {"seed": seed, "position": position, "condition": condition}
        for seed in SEEDS
        for position, condition in enumerate(
            ("direct", "xp_guided") if seed % 2 == 0 else ("xp_guided", "direct"), 1
        )
    ]
    plan = output / "design.json"
    design = {
        "server": get_json("/api/version"), "model": model, "settings": SETTINGS, "schedule": schedule,
        "protocol_sha256": hashlib.sha256((STUDY / "replication_protocol.md").read_bytes()).hexdigest(),
        "faults_sha256": hashlib.sha256((STUDY / "faults.json").read_bytes()).hexdigest(),
        "contract_cases_sha256": hashlib.sha256((STUDY / "contract_cases.json").read_bytes()).hexdigest(),
    }
    if plan.exists():
        recorded = json.loads(plan.read_text(encoding="utf-8"))
        if any(recorded[key] != design[key] for key in design):
            raise SystemExit("This output folder belongs to a different design.")
    else:
        write(plan, {**design, "start_utc": utc_now()})
    warmup = output / "warmup.json"
    if not warmup.exists():
        warmup.write_bytes(submit({"model": MODEL, "prompt": "", "stream": False, "keep_alive": "15m"}))
    results = []
    for index, row in enumerate(schedule, 1):
        result = generate(output, row)
        results.append(result)
        print(f"{index:02d}/{len(schedule)} seed {row['seed']} {row['condition']}: {result['status']}", flush=True)
    write(output / "completed.json", {"end_utc": utc_now(), "outcomes": results})


if __name__ == "__main__":
    main()
