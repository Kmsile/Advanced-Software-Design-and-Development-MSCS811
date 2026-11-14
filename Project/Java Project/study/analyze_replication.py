"""Replay the recorded prompt comparison locally and recover all reported statistics."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import re
from statistics import mean, median
from tempfile import TemporaryDirectory

from generate_cases import COMMON, INSTRUCTIONS, MODEL, SCHEMA
from run_study import (
    EVIDENCE, STUDY, command, compile_sources, evaluate_compiled, fault_sources,
    file_hash, read_json, read_sources, scenario_records,
)


PROMPTS = ("direct", "xp_guided")
CRITERION = re.compile(r"^([HT][1-4])(?=$|[\s\-_:.)])", re.IGNORECASE)


def load_experiment(folder):
    design = read_json(folder / "design.json")
    completed = read_json(folder / "completed.json")
    for name, key in (
        ("replication_protocol.md", "protocol_sha256"),
        ("faults.json", "faults_sha256"),
        ("contract_cases.json", "contract_cases_sha256"),
    ):
        if file_hash(STUDY / name) != design[key]:
            raise ValueError(f"Recorded design hash differs for {name}")

    roster = [(row["seed"], row["position"], row["condition"]) for row in design["schedule"]]
    observed = [(row["seed"], row["position"], row["condition"]) for row in completed["outcomes"]]
    if roster != observed or len(set(roster)) != 48:
        raise ValueError("The completed runs do not match the fixed schedule")

    contract = scenario_records("contract", read_json(STUDY / "contract_cases.json"), strict_budget=True)
    suites = {"contract": contract}
    cases = []
    for row in completed["outcomes"]:
        seed, prompt = row["seed"], row["condition"]
        folder_cell = folder / f"seed_{seed}" / prompt
        status = read_json(folder_cell / "status.json")
        if row != status or row["status"] not in {"returned", "unusable", "missing"}:
            raise ValueError(f"Inconsistent cell status in {folder_cell}")
        request = read_json(folder_cell / "request.json")
        if (
            request["format"] != SCHEMA
            or request["model"] != MODEL
            or request["options"] != dict(design["settings"], seed=seed)
            or request["prompt"] != COMMON + "\n" + INSTRUCTIONS[prompt] + "\n"
            or request["think"] is not False
            or request["stream"] is not False
        ):
            raise ValueError(f"Request differs from the paired design in {folder_cell}")
        key = f"{seed}_{prompt}"
        if row["status"] == "returned":
            response = read_json(folder_cell / "response.json")
            raw = json.loads(response["response"])
            if not response["done"] or raw != read_json(folder_cell / "cases.json"):
                raise ValueError(f"Case JSON differs from the returned response in {folder_cell}")
            suites[key] = scenario_records(key, raw)
        elif row["status"] == "unusable":
            suites[key] = scenario_records(key, {})
        cases.append({**row, "suite": key})
    return design, cases, suites


def get_criterion(case):
    match = CRITERION.match(case["name"] or "")
    return match.group(1).upper() if match else None


def describe(values):
    return {"mean": mean(values), "median": median(values), "min": min(values), "max": max(values)}


def quantile(values, probability):
    position = (len(values) - 1) * probability
    lower = int(position)
    fraction = position - lower
    return values[lower] * (1 - fraction) + values[min(lower + 1, len(values) - 1)] * fraction


def summarize(design, runs, observations, panel):
    available = [row for row in runs if row["status"] != "missing"]
    by_seed = {(row["seed"], row["condition"]): row for row in available}
    paired = []
    for seed in sorted({row["seed"] for row in runs}):
        if any((seed, condition) not in by_seed for condition in PROMPTS):
            continue
        direct, guided = (by_seed[(seed, condition)] for condition in PROMPTS)
        first, second = set(direct["detected"]), set(guided["detected"])
        paired.append({
            "seed": seed, "first": "direct" if direct["position"] == 1 else "xp_guided",
            "direct": len(first), "xp_guided": len(second), "difference": len(second) - len(first),
            "jaccard": len(first & second) / len(first | second) if first or second else 1.0,
            "identical_fault_set": first == second,
            "baseline_plus_direct": len(direct["baseline_union"]),
            "baseline_plus_xp_guided": len(guided["baseline_union"]),
            "both_suites_fully_eligible": all(
                sum(case["eligible"] for case in run["cases"]) == 6 for run in (direct, guided)
            ),
        })
    if not paired:
        raise RuntimeError("The analysis requires at least one complete pair")
    paired_seeds = {row["seed"] for row in paired}
    differences = [row["difference"] for row in paired]
    generator = random.Random(20261114)
    resampled = sorted(mean(generator.choices(differences, k=len(differences))) for _ in range(10000))
    fully_eligible = [row["difference"] for row in paired if row["both_suites_fully_eligible"]]
    leave_one_out = [
        mean(differences[:i] + differences[i + 1:]) for i in range(len(differences))
    ] if len(differences) > 1 else []
    conditions = {}
    for condition in PROMPTS:
        group = [run for run in available if run["condition"] == condition and run["seed"] in paired_seeds]
        evaluated = [case for run in group for case in run["cases"]]
        eligible = [case for case in evaluated if case["eligible"]]
        conditions[condition] = {
            "suites": len(group),
            "candidate_slots": len(evaluated),
            "eligible_cases": len(eligible),
            "eligible_by_suite": describe([sum(case["eligible"] for case in row["cases"]) for row in group]),
            "criteria_prefixed_eligible": sum(case["criterion_prefix"] is not None for case in eligible),
            "red_failures": sum(case["red_status"] == "FAIL" for case in eligible),
            "suites_with_red_failure": sum(any(case["eligible"] and case["red_status"] == "FAIL" for case in row["cases"]) for row in group),
            "faults_detected": describe([len(row["detected"]) for row in group]),
            "baseline_union": describe([len(row["baseline_union"]) for row in group]),
        }
    for datum in panel:
        datum["frequency"] = {
            condition: sum(
                datum["id"] in by_seed[(seed, condition)]["detected"] for seed in paired_seeds
            )
            for condition in PROMPTS
        }
    return {
        "design": design,
        "java_version": command(["java", "-version"]).stderr.strip(),
        "clean_source_sha256": observations,
        "counts": {
            "scheduled": len(runs), "complete_pairs": len(paired),
            **{status: sum(run["status"] == status for run in runs) for status in ("returned", "unusable", "missing")},
        },
        "faults": panel,
        "conditions": conditions,
        "paired_difference": {
            **describe(differences),
            "bootstrap_95": [quantile(resampled, 0.025), quantile(resampled, 0.975)],
            "guided_wins": sum(value > 0 for value in differences),
            "ties": sum(value == 0 for value in differences),
            "guided_losses": sum(value < 0 for value in differences),
        },
        "jaccard": describe([row["jaccard"] for row in paired]),
        "equal_fault_sets": sum(row["identical_fault_set"] for row in paired),
        "exploratory_sensitivity": {
            "fully_eligible_pairs": len(fully_eligible),
            "fully_eligible_difference": describe(fully_eligible) if fully_eligible else None,
            "leave_one_out_mean_range": [min(leave_one_out), max(leave_one_out)] if leave_one_out else None,
        },
        "order": {
            name: describe([row["difference"] for row in paired if row["first"] == name])
            for name in PROMPTS if any(row["first"] == name for row in paired)
        },
        "pairs": paired,
        "runs": runs,
    }


def evaluate_experiment(folder):
    design, runs, suites = load_experiment(folder)
    sources = read_sources("refactor")
    red_sources = read_sources("red")
    faults = read_json(STUDY / "faults.json")
    outcomes = {}
    with TemporaryDirectory(prefix="mscs811-article-") as temp:
        base = Path(temp)
        versions = [("clean", sources), ("red", red_sources)]
        versions.extend((fault["id"], fault_sources(sources, fault)) for fault in faults)
        for label, content in versions:
            work = base / label
            work.mkdir()
            outcomes[label] = evaluate_compiled(compile_sources(content, work), suites)
            print(f"Evaluated {label}", flush=True)

    clean, red = outcomes["clean"], outcomes["red"]
    if clean["baseline"]["status"] != "PASS" or red["baseline"]["status"] != "PASS":
        raise RuntimeError("The regression reference failed on a stage version")
    if any(case["status"] != "PASS" for case in clean["scenarios"]["contract"]):
        raise RuntimeError("The clean implementation failed a contract check")
    panel = []
    for fault in faults:
        result = outcomes[fault["id"]]
        detectable = any(case["status"] == "FAIL" for case in result["scenarios"]["contract"])
        if not detectable:
            raise RuntimeError(f"Contract checks did not distinguish {fault['id']}")
        panel.append({
            "id": fault["id"], "description": fault["description"],
            "baseline": result["baseline"]["status"] == "FAIL",
            "contract": detectable,
        })
    inherited = {fault["id"] for fault in panel if fault["baseline"]}
    for run in runs:
        if run["status"] == "missing":
            continue
        suite = run["suite"]
        reference = suites[suite]
        before = {row["id"]: row for row in red["scenarios"][suite]}
        fault_checks = {
            fault["id"]: {case["id"]: case for case in outcomes[fault["id"]]["scenarios"][suite]}
            for fault in panel
        }
        cases = []
        for raw, case in zip(reference, clean["scenarios"][suite]):
            if raw["id"] != case["id"]:
                raise RuntimeError("Test runner changed scenario order")
            key = case["id"]
            eligible = case["status"] == "PASS"
            cases.append({
                **case, "eligible": eligible, "criterion_prefix": get_criterion(case),
                "input": raw["data"], "red_status": before[key]["status"],
                "red_detail": before[key]["detail"],
                "fault_checks": {fault: checks[key] for fault, checks in fault_checks.items()},
            })
        detected = {
            fault for case in cases if case["eligible"]
            for fault, check in case["fault_checks"].items() if check["status"] == "FAIL"
        }
        run.update(cases=cases, detected=sorted(detected), baseline_union=sorted(inherited | detected))
    return summarize(design, runs, {name: hashlib.sha256(code).hexdigest() for name, code in sources.items()}, panel)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, default=EVIDENCE / "replication")
    parser.add_argument("--output", type=Path, default=STUDY / "replay" / "paired_analysis.json")
    args = parser.parse_args()
    result = evaluate_experiment(args.runs)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(f"{result['counts']['complete_pairs']} complete pairs")
    for condition, summary in result["conditions"].items():
        print(f"{condition}: {summary['faults_detected']['mean']:.2f}/{len(result['faults'])} mean")
    print(f"Paired mean difference: {result['paired_difference']['mean']:+.2f}")
    print(args.output.resolve())


if __name__ == "__main__":
    main()
