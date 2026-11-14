"""Reproduce the local test-first stages and paired fault-detection experiment."""

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


STUDY = Path(__file__).resolve().parent
PROJECT = STUDY.parent
EVIDENCE = STUDY / "evidence"
ECJ = PROJECT / "lib/ecj-3.26.0.jar"
JSOUP = PROJECT / "lib/jsoup-1.17.2.jar"
CONDITIONS = ("direct", "xp_guided", "contract")
HYBRID_FIELDS = (
    "policy", "html_status", "ocr_status", "html_text", "ocr_text",
    "expected_status", "expected_text", "expected_ocr_calls",
)
HTML_FIELDS = ("markup", "expected_text")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_scenario(driver, case):
    if not isinstance(case, dict):
        return "Expected a scenario object"
    if not isinstance(case.get("name"), str) or not case["name"].strip():
        return "Missing case name"
    fields = HYBRID_FIELDS if driver == "hybrid" else HTML_FIELDS
    if set(case) != {"name", *fields}:
        return "Unexpected scenario fields"
    for field in fields:
        if field == "expected_ocr_calls":
            if type(case.get(field)) is not int or case[field] not in (-1, 0, 1):
                return "Invalid OCR call expectation"
        elif not isinstance(case.get(field), str) or len(case[field]) > 2000:
            return f"Invalid {field}"
    if driver == "html":
        if re.search(r"https?://|<(iframe|object|link|img)\b", case["markup"], re.IGNORECASE):
            return "Outside the local synthetic fixture scope"
        return None
    if case["policy"] not in ("default", "propagate", "return_html"):
        return "Unknown OCR failure policy"
    if case["html_status"] not in ("ok", "io") or case["ocr_status"] not in (
        "ok", "io", "runtime", "interrupted"
    ):
        return "Unknown dependency state"
    status, output, calls = expected_hybrid(case)
    if (case["expected_status"], case["expected_text"]) != (status, output):
        return "Expected result disagrees with the contract"
    if case["expected_ocr_calls"] not in (-1, calls):
        return "Expected call count disagrees with the contract"
    return None


def expected_hybrid(case):
    if case["html_status"] == "io":
        return "html_io", "", 0
    ocr = case["ocr_status"]
    html = "[HTML]\n" + case["html_text"]
    if ocr == "ok":
        return "return", html + "\n[OCR]\n" + case["ocr_text"], 1
    if ocr == "runtime":
        return "ocr_runtime", "", 1
    if ocr == "io" and case["policy"] == "return_html":
        return "return", html, 1
    return "ocr_io", "", 1


def scenario_records(suite, raw, *, strict_budget=False):
    seen = set()
    cases = []
    for driver, fields in (("hybrid", HYBRID_FIELDS), ("html", HTML_FIELDS)):
        entries = raw.get(driver)
        if not isinstance(entries, list) or (suite != "contract" and len(entries) != 3):
            if strict_budget:
                raise ValueError(f"{suite} must contain three {driver} cases")
            entries = [None] * 3
        for index, case in enumerate(entries, 1):
            issue = check_scenario(driver, case)
            if issue is None:
                signature = (driver, *(case[field] for field in fields))
                if signature in seen:
                    issue = "Exact duplicate scenario within this suite"
                seen.add(signature)
            cases.append({
                "id": f"{suite}.{driver}.{index}", "driver": driver,
                "name": case.get("name") if isinstance(case, dict) else None,
                "data": case, "validation_issue": issue,
            })
    return cases


def load_scenarios():
    input_paths = {
        "direct": EVIDENCE / "direct_cases.json",
        "xp_guided": EVIDENCE / "xp_guided_cases.json",
        "contract": STUDY / "contract_cases.json",
    }
    return {
        suite: scenario_records(suite, read_json(path), strict_budget=True)
        for suite, path in input_paths.items()
    }


def command(args, *, input_text=None):
    return subprocess.run(
        args, cwd=PROJECT, input=input_text, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=90,
    )


def read_sources(phase):
    java_files = sorted((PROJECT / "src").glob("*.java")) + sorted((PROJECT / "tests").glob("*.java"))
    sources = {path.name: path.read_bytes() for path in java_files}
    for name in ("HybridTextExtractor.java", "HtmlTextExtractor.java"):
        if phase in ("red", "green"):
            sources[name] = (STUDY / "snapshots" / phase / (name + ".txt")).read_bytes()
    sources["ScenarioCheck.java"] = (STUDY / "ScenarioCheck.java").read_bytes()
    return sources


def compile_sources(sources, work):
    source_paths = []
    for name, data in sources.items():
        path = work / name
        path.write_bytes(data)
        source_paths.append(str(path))
    classes = work / "classes"
    classes.mkdir()
    result = command([
        "java", "-jar", str(ECJ), "-1.8", "-proc:none", "-encoding", "UTF-8",
        "-cp", str(JSOUP), "-d", str(classes), *source_paths,
    ])
    if result.returncode:
        raise RuntimeError(f"Java compilation failed:\n{result.stdout}{result.stderr}")
    return os.pathsep.join((str(classes), str(JSOUP)))


def encoded_scenario(case):
    fields = HYBRID_FIELDS if case["driver"] == "hybrid" else HTML_FIELDS
    values = [case["id"], case["driver"], *(case["data"][key] for key in fields)]
    return "\t".join(base64.b64encode(str(v).encode("utf-8")).decode("ascii") for v in values)


def evaluate(sources, suites, work):
    return evaluate_compiled(compile_sources(sources, work), suites)


def evaluate_compiled(classpath, suites):
    baseline = command(["java", "-cp", classpath, "StrategyTests", "--local-only"])
    baseline_passes = sum(line.startswith("PASS ") for line in baseline.stdout.splitlines())
    if baseline.returncode and "java.lang.AssertionError" not in baseline.stderr:
        raise RuntimeError(f"Baseline execution error:\n{baseline.stdout}{baseline.stderr}")
    if baseline.returncode == 0 and baseline_passes != 6:
        raise RuntimeError("A passing baseline must run all six local checks")
    cases = [case for group in suites.values() for case in group]
    text = "\n".join(encoded_scenario(c) for c in cases if c["validation_issue"] is None)
    result = command(["java", "-cp", classpath, "ScenarioCheck"], input_text=text + "\n")
    if result.returncode:
        raise RuntimeError(f"Scenario execution error:\n{result.stdout}{result.stderr}")
    results = {}
    for line in result.stdout.splitlines():
        identifier, status, *detail = line.split("\t")
        if identifier in results or status not in ("PASS", "FAIL"):
            raise RuntimeError(f"Unexpected test output: {line}")
        results[identifier] = {
            "status": status,
            "detail": base64.b64decode(detail[0]).decode("utf-8") if detail else None,
        }
    assert len(results) == sum(case["validation_issue"] is None for case in cases)
    return {
        "baseline": {
            "status": "PASS" if baseline.returncode == 0 else "FAIL",
            "checks_before_exit": baseline_passes,
            "output": baseline.stdout + baseline.stderr,
        },
        "scenarios": {
            suite: [
                {"id": case["id"], "name": case["name"], "driver": case["driver"],
                 **(results[case["id"]] if case["validation_issue"] is None else {
                     "status": "INVALID", "detail": case["validation_issue"],
                 })}
                for case in suites[suite]
            ]
            for suite in suites
        },
    }


def fault_sources(sources, fault):
    modified = sources.copy()
    code = modified[fault["file"]].decode("utf-8")
    if code.count(fault["before"]) != 1:
        raise ValueError(f"Fault {fault['id']} must match exactly one source location")
    modified[fault["file"]] = code.replace(fault["before"], fault["after"], 1).encode("utf-8")
    return modified


def phase_receipt(phase, suites, work):
    sources = read_sources(phase)
    checks = evaluate(sources, suites, work)
    if checks["baseline"]["status"] != "PASS":
        raise RuntimeError("The inherited regression suite failed on the stage version")
    contract = checks["scenarios"]["contract"]
    failed = {case["driver"] for case in contract if case["status"] == "FAIL"}
    if phase == "red":
        assert failed == {"hybrid", "html"}, "Both changes must show a behavioral red"
    else:
        assert all(case["status"] == "PASS" for case in contract), "Contract suite failed"
    return {
        "phase": phase,
        "executed_utc": datetime.now(timezone.utc).isoformat(),
        "java_version": command(["java", "-version"]).stderr.strip(),
        "source_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()},
        "checks": checks,
    }


def score(suites, work):
    sources = read_sources("refactor")
    clean_work = work / "clean"
    clean_work.mkdir()
    clean = evaluate(sources, suites, clean_work)
    assert clean["baseline"]["status"] == "PASS"
    assert all(case["status"] == "PASS" for case in clean["scenarios"]["contract"])
    eligible = {
        suite: {case["id"] for case in clean["scenarios"][suite] if case["status"] == "PASS"}
        for suite in CONDITIONS
    }
    measurements = []
    for fault in read_json(STUDY / "faults.json"):
        case_sources = fault_sources(sources, fault)
        variant_work = work / fault["id"]
        variant_work.mkdir()
        outcome = evaluate(case_sources, suites, variant_work)
        detected = {"baseline": outcome["baseline"]["status"] == "FAIL"}
        for suite in CONDITIONS:
            detected[suite] = any(
                case["id"] in eligible[suite] and case["status"] == "FAIL"
                for case in outcome["scenarios"][suite]
            )
        for suite in ("direct", "xp_guided"):
            detected[f"baseline_plus_{suite}"] = detected["baseline"] or detected[suite]
        measurements.append({
            "id": fault["id"], "description": fault["description"], "detected": detected,
            "checks": outcome,
        })
    return {
        "phase": "score",
        "executed_utc": datetime.now(timezone.utc).isoformat(),
        "eligible": {name: sorted(ids) for name, ids in eligible.items()},
        "clean": clean,
        "fault_count": len(measurements),
        "detection_counts": {
            suite: sum(item["detected"][suite] for item in measurements)
            for suite in measurements[0]["detected"]
        },
        "faults": measurements,
        "fault_recipes_sha256": file_hash(STUDY / "faults.json"),
        "model_receipt_sha256": file_hash(EVIDENCE / "model.json"),
        "source_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in sources.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("red", "green", "refactor", "score"), default="score")
    parser.add_argument("--output", type=Path, default=STUDY / "replay")
    args = parser.parse_args()
    if shutil.which("java") is None:
        raise SystemExit("Java 8 or newer must be on PATH.")
    args.output.mkdir(parents=True, exist_ok=True)
    suites = load_scenarios()
    with tempfile.TemporaryDirectory(prefix="mscs811-study-") as temp:
        work = Path(temp).resolve()
        report = score(suites, work) if args.phase == "score" else phase_receipt(args.phase, suites, work)
    target = args.output / f"{args.phase}.json"
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=args.output, delete=False) as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    Path(stream.name).replace(target)
    print(f"{args.phase}: {target.resolve()}")
    if args.phase == "score":
        for name, count in report["detection_counts"].items():
            print(f"{name}: {count}/{report['fault_count']} faults detected")
    else:
        checks = report["checks"]
        print(f"baseline: {checks['baseline']['checks_before_exit']}/6")
        for name, results in checks["scenarios"].items():
            print(f"{name}: {sum(c['status'] == 'PASS' for c in results)}/{len(results)}")


if __name__ == "__main__":
    main()
