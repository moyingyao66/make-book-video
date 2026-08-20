#!/usr/bin/env python3
"""Validate and score evidence-bound implicit-trigger observations for this Skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SUITE = SKILL_DIR / "evals/skill-evals.json"


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"missing JSON file: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"JSON root must be an object: {path}")
    return document


def normalize_route(value: Any) -> str:
    return str(value or "").strip().lstrip("$")


def suite_sha256(document: dict[str, Any]) -> str:
    canonical = json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_sha256(value: Any) -> bool:
    candidate = str(value or "")
    return bool(re.fullmatch(r"[0-9a-f]{64}", candidate))


def is_reproducible_host_version(value: Any) -> bool:
    """Reject empty/generic labels that cannot identify the evaluated host build."""

    candidate = str(value or "").strip().lower()
    if not candidate:
        return False
    if re.match(
        r"^(?:current|dev(?:elopment)?|fixture|latest|n/?a|none|"
        r"placeholder|test(?:ing)?|tbd|todo|unknown)(?:$|[-_.+ ])",
        candidate,
    ):
        return False
    # A stable semantic version, date-coded build, or commit-like build ID has a
    # digit. Pure labels such as "production" still drift over time.
    return bool(re.search(r"\d", candidate))


def validate_suite(document: dict[str, Any], skill_dir: Path = SKILL_DIR) -> list[str]:
    errors: list[str] = []
    try:
        runs = int(document.get("runsPerPrompt") or 0)
        if runs != 3:
            raise ValueError
    except (TypeError, ValueError):
        errors.append("runsPerPrompt must equal 3")
        runs = 0
    cases = document.get("triggerCases")
    if not isinstance(cases, list):
        errors.append("triggerCases must be an array")
        cases = []
    ids: set[str] = set()
    counts = {"use": 0, "skip": 0}
    unnamed_use_cases = 0
    for index, item in enumerate(cases, start=1):
        if not isinstance(item, dict):
            errors.append(f"trigger case {index} must be an object")
            continue
        case_id = str(item.get("id") or "").strip()
        if not case_id:
            errors.append(f"trigger case {index} has no id")
        elif case_id in ids:
            errors.append(f"duplicate trigger case id: {case_id}")
        ids.add(case_id)
        expectation = str(item.get("expect") or "")
        if expectation not in counts:
            errors.append(f"trigger case {case_id or index} must expect use or skip")
        else:
            counts[expectation] += 1
        prompt = str(item.get("prompt") or "").strip()
        if not prompt:
            errors.append(f"trigger case {case_id or index} has no prompt")
        if not str(item.get("reason") or "").strip():
            errors.append(f"trigger case {case_id or index} has no reason")
        if expectation == "use" and "make-book-video" not in prompt.lower():
            unnamed_use_cases += 1
        if expectation == "skip":
            raw_route = item.get("expectedRoute")
            expected_route = normalize_route(raw_route)
            if not isinstance(raw_route, str) or not expected_route:
                errors.append(
                    f"skip trigger case {case_id or index} has no expectedRoute"
                )
            elif expected_route == "make-book-video":
                errors.append(
                    f"skip trigger case {case_id or index} cannot route to make-book-video"
                )
    for expectation, count in counts.items():
        if count != 10:
            errors.append(f"{expectation} cases must contain exactly 10 prompts; found {count}")
    if unnamed_use_cases < 8:
        errors.append("at least 8 use cases must test implicit triggering without the Skill name")

    thresholds = document.get("thresholds")
    if not isinstance(thresholds, dict):
        errors.append("thresholds must be an object")
        thresholds = {}
    for field in (
        "minimumShouldTriggerRate",
        "minimumUseCaseSuccessRate",
        "maximumFalsePositiveRate",
        "minimumExpectedRouteRate",
        "minimumCaseStabilityRate",
    ):
        try:
            value = float(thresholds.get(field))
            if not 0 <= value <= 1:
                raise ValueError
        except (TypeError, ValueError):
            errors.append(f"thresholds.{field} must be between 0 and 1")
    try:
        execution_thresholds = document.get("executionThresholds")
        if not isinstance(execution_thresholds, dict):
            raise ValueError
        execution_threshold = float(
            execution_thresholds.get("minimumGatePassRate")
        )
        if not 0 <= execution_threshold <= 1:
            raise ValueError
    except (TypeError, ValueError):
        errors.append(
            "executionThresholds.minimumGatePassRate must be between 0 and 1"
        )

    assertions = document.get("executionAssertions")
    if not isinstance(assertions, list):
        errors.append("executionAssertions must be an array")
        assertions = []
    if len(assertions) != 11:
        errors.append("executionAssertions must contain exactly 11 objective gates")
    assertion_ids: set[str] = set()
    for index, item in enumerate(assertions, start=1):
        if not isinstance(item, dict):
            errors.append(f"execution assertion {index} must be an object")
            continue
        assertion_id = str(item.get("id") or "").strip()
        if not assertion_id:
            errors.append(f"execution assertion {index} has no id")
        elif assertion_id in assertion_ids:
            errors.append(f"duplicate execution assertion id: {assertion_id}")
        assertion_ids.add(assertion_id)
        stage = str(item.get("stage") or "").strip()
        if stage not in ("draft", "synthesis", "render", "delivery"):
            errors.append(
                f"execution assertion {assertion_id or index} has invalid stage: {stage!r}"
            )
        validator = str(item.get("validator") or "").strip()
        if not validator:
            errors.append(f"execution assertion {assertion_id or index} has no validator")
        elif not (skill_dir / validator).is_file():
            errors.append(f"execution assertion validator does not exist: {validator}")
        if not str(item.get("assertion") or "").strip():
            errors.append(f"execution assertion {assertion_id or index} has no assertion")
    return errors


def result_template(suite: dict[str, Any]) -> dict[str, Any]:
    runs = int(suite["runsPerPrompt"])
    return {
        "suiteVersion": suite.get("version"),
        "suiteSha256": suite_sha256(suite),
        "runsPerPrompt": runs,
        "targetHost": "",
        "targetHostVersion": "",
        "evaluationDate": "",
        "results": [
            {
                "id": item["id"],
                "triggered": [None for _ in range(runs)],
                "selectedSkill": ["" for _ in range(runs)],
                "runEvidence": [
                    {
                        "sessionId": "",
                        "recordPath": "",
                        "recordSha256": "",
                    }
                    for _ in range(runs)
                ],
            }
            for item in suite.get("triggerCases") or []
        ],
    }


def score_results(
    suite: dict[str, Any],
    observations: dict[str, Any],
    evidence_root: Path | None = None,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    expected_runs = int(suite.get("runsPerPrompt") or 0)
    if observations.get("suiteVersion") != suite.get("version"):
        errors.append("results suiteVersion differs from the evaluation suite")
    if observations.get("runsPerPrompt") != expected_runs:
        errors.append("results runsPerPrompt differs from the evaluation suite")
    if observations.get("suiteSha256") != suite_sha256(suite):
        errors.append("results suiteSha256 differs from the evaluation suite")
    for field in ("targetHost", "targetHostVersion"):
        if not str(observations.get(field) or "").strip():
            errors.append(f"results {field} is required")
    host_version = str(observations.get("targetHostVersion") or "").strip()
    if host_version and not is_reproducible_host_version(host_version):
        errors.append("results targetHostVersion must be a reproducible build identifier")
    evaluation_date = str(observations.get("evaluationDate") or "").strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", evaluation_date) is None:
            raise ValueError
        parsed_date = date.fromisoformat(evaluation_date)
        if parsed_date > date.today():
            errors.append("results evaluationDate cannot be in the future")
    except ValueError:
        errors.append("results evaluationDate must use YYYY-MM-DD")

    raw_items = observations.get("results")
    observed_items: dict[str, dict[str, Any]] = {}
    if not isinstance(raw_items, list):
        errors.append("results must be an array")
        raw_items = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            errors.append(f"result {index} must be an object")
            continue
        case_id = str(item.get("id") or "").strip()
        if not case_id:
            errors.append(f"result {index} has no id")
        elif case_id in observed_items:
            errors.append(f"duplicate result id: {case_id}")
        else:
            observed_items[case_id] = item
    expected_ids = {
        str(item.get("id") or "") for item in suite.get("triggerCases") or []
    }
    for case_id in sorted(set(observed_items) - expected_ids):
        errors.append(f"unexpected result for trigger case: {case_id}")
    should_total = should_hits = skip_total = false_positives = stable_cases = 0
    route_total = route_hits = 0
    seen_session_ids: set[str] = set()
    seen_record_paths: set[str] = set()
    seen_resolved_record_paths: set[Path] = set()
    per_case = []
    if evidence_root is None:
        errors.append(
            "an evidence root is required to verify every trigger run record"
        )
    else:
        evidence_root = evidence_root.resolve()
    for case in suite.get("triggerCases") or []:
        case_id = str(case.get("id") or "")
        item = observed_items.get(case_id)
        if not item:
            errors.append(f"missing result for trigger case: {case_id}")
            continue
        values = item.get("triggered") or []
        if len(values) != expected_runs or any(type(value) is not bool for value in values):
            errors.append(
                f"trigger case {case_id} needs exactly {expected_runs} boolean observations"
            )
            continue
        selected = item.get("selectedSkill") or []
        if len(selected) != expected_runs or any(
            not isinstance(value, str) for value in selected
        ):
            errors.append(
                f"trigger case {case_id} needs exactly {expected_runs} selectedSkill strings"
            )
            continue
        run_evidence = item.get("runEvidence")
        if not isinstance(run_evidence, list) or len(run_evidence) != expected_runs:
            errors.append(
                f"trigger case {case_id} needs exactly {expected_runs} runEvidence records"
            )
            run_evidence = []
        normalized_selected: list[str] = []
        for run_index, (triggered, skill_name) in enumerate(
            zip(values, selected), start=1
        ):
            normalized = skill_name.strip().lstrip("$")
            normalized_selected.append(normalized)
            if not normalized:
                errors.append(
                    f"trigger case {case_id} run {run_index} has no selectedSkill; "
                    "record none when the host selected no Skill"
                )
            if triggered and normalized != "make-book-video":
                errors.append(
                    f"trigger case {case_id} run {run_index} was marked triggered "
                    "without selecting make-book-video"
                )
            if not triggered and normalized == "make-book-video":
                errors.append(
                    f"trigger case {case_id} run {run_index} selected make-book-video "
                    "but was marked not triggered"
                )
        for run_index, evidence in enumerate(run_evidence, start=1):
            if not isinstance(evidence, dict):
                errors.append(
                    f"trigger case {case_id} run {run_index} evidence must be an object"
                )
                continue
            session_id = str(evidence.get("sessionId") or "").strip()
            record_value = str(evidence.get("recordPath") or "").strip()
            record_hash = str(evidence.get("recordSha256") or "")
            if not session_id:
                errors.append(
                    f"trigger case {case_id} run {run_index} evidence sessionId is required"
                )
            elif session_id in seen_session_ids:
                errors.append(f"duplicate trigger evidence sessionId: {session_id}")
            else:
                seen_session_ids.add(session_id)
            record_path = Path(record_value)
            if (
                not record_value
                or record_path.is_absolute()
                or record_path.suffix.lower() != ".json"
                or ".." in record_path.parts
            ):
                errors.append(
                    f"trigger case {case_id} run {run_index} evidence recordPath must be a relative JSON path"
                )
            else:
                normalized_record_path = record_path.as_posix()
                if normalized_record_path in seen_record_paths:
                    errors.append(
                        f"duplicate trigger evidence recordPath: {normalized_record_path}"
                    )
                else:
                    seen_record_paths.add(normalized_record_path)
            if not is_sha256(record_hash):
                errors.append(
                    f"trigger case {case_id} run {run_index} evidence recordSha256 is invalid"
                )
            if (
                evidence_root is not None
                and record_value
                and not record_path.is_absolute()
                and ".." not in record_path.parts
                and record_path.suffix.lower() == ".json"
            ):
                root = evidence_root
                resolved = (root / record_path).resolve()
                try:
                    resolved.relative_to(root)
                except ValueError:
                    errors.append(
                        f"trigger case {case_id} run {run_index} evidence recordPath escapes the results directory"
                    )
                    continue
                if resolved in seen_resolved_record_paths:
                    errors.append(
                        f"duplicate trigger evidence resolved recordPath: {record_value}"
                    )
                    continue
                seen_resolved_record_paths.add(resolved)
                if not resolved.is_file():
                    errors.append(
                        f"trigger case {case_id} run {run_index} evidence record is missing"
                    )
                    continue
                if is_sha256(record_hash) and file_sha256(resolved) != record_hash:
                    errors.append(
                        f"trigger case {case_id} run {run_index} evidence recordSha256 is stale"
                    )
                    continue
                try:
                    record = load_json(resolved)
                except (ValueError, json.JSONDecodeError) as exc:
                    errors.append(
                        f"trigger case {case_id} run {run_index} evidence record is invalid: {exc}"
                    )
                    continue
                expected_selected = normalized_selected[run_index - 1]
                if str(record.get("caseId") or "").strip() != case_id:
                    errors.append(
                        f"trigger case {case_id} run {run_index} evidence caseId differs from its record"
                    )
                record_run_index = record.get("runIndex")
                if type(record_run_index) is not int or record_run_index != run_index:
                    errors.append(
                        f"trigger case {case_id} run {run_index} evidence runIndex differs from its record"
                    )
                if str(record.get("sessionId") or "").strip() != session_id:
                    errors.append(
                        f"trigger case {case_id} run {run_index} evidence sessionId differs from its record"
                    )
                if record.get("triggered") is not values[run_index - 1]:
                    errors.append(
                        f"trigger case {case_id} run {run_index} evidence triggered value differs from its record"
                    )
                if normalize_route(record.get("selectedSkill")) != expected_selected:
                    errors.append(
                        f"trigger case {case_id} run {run_index} evidence selectedSkill differs from its record"
                    )
        stable = len(set(zip(values, normalized_selected))) == 1
        stable_cases += int(stable)
        if case.get("expect") == "use":
            expected_route = "make-book-video"
            should_total += len(values)
            run_successes = [
                triggered and selected_skill == "make-book-video"
                for triggered, selected_skill in zip(values, normalized_selected)
            ]
            should_hits += sum(run_successes)
        else:
            skip_total += len(values)
            false_positives += sum(1 for value in values if value)
            expected_route = normalize_route(case.get("expectedRoute"))
            run_successes = [
                not triggered and selected_skill == expected_route
                for triggered, selected_skill in zip(values, normalized_selected)
            ]
            route_total += len(values)
            route_hits += sum(run_successes)
        success_rate = sum(run_successes) / len(run_successes)
        per_case.append(
            {
                "id": case_id,
                "expect": case.get("expect"),
                "expectedRoute": expected_route,
                "selectedSkill": normalized_selected,
                "successRate": success_rate,
                "stable": stable,
            }
        )
    total_cases = len(suite.get("triggerCases") or [])
    should_rate = should_hits / should_total if should_total else 0.0
    false_positive_rate = false_positives / skip_total if skip_total else 1.0
    expected_route_rate = route_hits / route_total if route_total else 0.0
    stability_rate = stable_cases / total_cases if total_cases else 0.0
    thresholds = suite.get("thresholds") or {}
    use_case_rates = [
        float(item["successRate"])
        for item in per_case
        if item.get("expect") == "use"
    ]
    minimum_use_case_rate = min(use_case_rates) if use_case_rates else 0.0
    passed = (
        not errors
        and should_rate >= float(thresholds["minimumShouldTriggerRate"])
        and minimum_use_case_rate
        >= float(thresholds["minimumUseCaseSuccessRate"])
        and false_positive_rate <= float(thresholds["maximumFalsePositiveRate"])
        and expected_route_rate >= float(thresholds["minimumExpectedRouteRate"])
        and stability_rate >= float(thresholds["minimumCaseStabilityRate"])
    )
    return (
        {
            "ok": passed,
            "shouldTriggerRate": should_rate,
            "minimumUseCaseSuccessRate": minimum_use_case_rate,
            "falsePositiveRate": false_positive_rate,
            "expectedRouteRate": expected_route_rate,
            "caseStabilityRate": stability_rate,
            "thresholds": thresholds,
            "perCase": per_case,
        },
        errors,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--init-results", type=Path)
    group.add_argument("--results", type=Path)
    args = parser.parse_args()
    try:
        suite = load_json(args.suite.resolve())
    except (ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "errors": [str(exc)]}, indent=2))
        return 2
    errors = validate_suite(suite)
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, ensure_ascii=False, indent=2))
        return 2
    if args.init_results:
        output = args.init_results.resolve()
        if output.exists():
            raise SystemExit(f"Refusing to overwrite existing results file: {output}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result_template(suite), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({"ok": True, "resultsTemplate": str(output)}, indent=2))
        return 0
    if args.results:
        try:
            observations = load_json(args.results.resolve())
        except (ValueError, json.JSONDecodeError) as exc:
            print(json.dumps({"ok": False, "errors": [str(exc)]}, indent=2))
            return 2
        report, score_errors = score_results(
            suite, observations, evidence_root=args.results.resolve().parent
        )
        report["errors"] = score_errors
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 2
    print(
        json.dumps(
            {
                "ok": True,
                "triggerCases": len(suite.get("triggerCases") or []),
                "runsPerPrompt": suite.get("runsPerPrompt"),
                "executionAssertions": len(suite.get("executionAssertions") or []),
                "thresholds": suite.get("thresholds"),
                "executionThresholds": suite.get("executionThresholds"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
