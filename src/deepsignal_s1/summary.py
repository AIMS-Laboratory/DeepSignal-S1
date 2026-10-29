"""Paired comparisons from complete, same-version test records."""

from pathlib import Path

from .data import read_json, write_json


def summarize(root, suite_path, controllers=("s1", "fixed", "visual-pressure")):
    root = Path(root)
    suite = read_json(suite_path)
    pairs = []
    versions = set()
    for case in suite["cases"]:
        active_controllers = [c for c in controllers if c != "fixed" or case["condition"] == "clean"]
        if case["condition"] != "clean" and not {"s1", "visual-pressure"}.issubset(active_controllers):
            raise ValueError("Perturbed comparisons require S1 and YOLO+MP, not fixed timing")
        for seed in suite["seeds"]:
            case_id = f"{case['scene']}-{case['regime']}-{case['condition']}-{seed}"
            reports = {}
            reference_plan = None
            for controller in active_controllers:
                directory = root / case_id / controller
                report = read_json(directory / "report.json")
                if controller == "fixed" and report.get("baseline") != "engineering-fixed":
                    raise ValueError("Only identified engineering-fixed records may be compared")
                plan = read_json(directory / "plan.json")
                if (
                    not report["complete"]
                    or report.get("failure")
                    or not report["metrics"]["complete"]
                ):
                    raise ValueError(f"Incomplete paired run: {case_id}/{controller}")
                if reference_plan is not None and plan != reference_plan:
                    raise ValueError(f"Arrival plans differ: {case_id}")
                reference_plan = plan
                if (
                    report["scene"],
                    report["regime"],
                    report["seed"],
                    report["condition"],
                ) != (case["scene"], case["regime"], seed, case["condition"]):
                    raise ValueError(f"Report does not match the suite case: {case_id}")
                if controller == "s1":
                    if not report["model_version"]:
                        raise ValueError("A tested model version is required")
                    versions.add(report["model_version"])
                reports[controller] = report
            if len({r["metrics"]["vehicles"] for r in reports.values()}) != 1:
                raise ValueError("Paired vehicle counts differ")
            pairs.append(
                {
                    "case": case_id,
                    "scene": case["scene"],
                    "regime": case["regime"],
                    "condition": case["condition"],
                    "seed": seed,
                    "reports": reports,
                }
            )
    if len(versions) != 1:
        raise ValueError(
            "All published comparisons must use exactly one serving model version"
        )
    rows = []
    for scene, regime, condition in sorted(
        {(p["scene"], p["regime"], p["condition"]) for p in pairs}
    ):
        selected = [
            p for p in pairs
            if (p["scene"], p["regime"], p["condition"]) == (scene, regime, condition)
        ]
        means = {}
        for controller in selected[0]["reports"]:
            total = sum(
                p["reports"][controller]["metrics"]["vehicles"] for p in selected
            )
            means[controller] = (
                sum(
                    p["reports"][controller]["metrics"]["mean_journey_s"]
                    * p["reports"][controller]["metrics"]["vehicles"]
                    for p in selected
                )
                / total
            )
        rows.append(
            {
                "scene": scene,
                "regime": regime,
                "condition": condition,
                "paired_runs": len(selected),
                "mean_journey_s": means,
                "improvement_pct": {
                    c: 100 * (1 - means["s1"] / means[c])
                    for c in means
                    if c != "s1"
                },
            }
        )
    result = {
        "model_version": versions.pop(),
        "selection": "selected demonstration scenarios; not a network-wide benchmark",
        "suite": suite,
        "rows": rows,
        "pairs": pairs,
    }
    write_json(root / "comparison.json", result)
    lines = []
    for clean, title, columns in [
        (True, "正常视觉三方对照 / Clean Views",
         (("s1", "DeepSignal-S1"), ("fixed", "Engineering fixed"), ("visual-pressure", "YOLO+MP"))),
        (False, "特殊视觉双方对照 / Perturbed Views",
         (("s1", "DeepSignal-S1"), ("visual-pressure", "YOLO+MP"))),
    ]:
        selected = [row for row in rows if (row["condition"] == "clean") == clean]
        if not selected:
            continue
        lines.extend(["", "## " + title, "",
                      "| Scenario | Demand | Condition | Pairs | " +
                      " | ".join(label + " (s)" for _, label in columns) + " |",
                      "| --- | --- | --- | ---: | " + " | ".join("---:" for _ in columns) + " |"])
        for row in selected:
            means = row["mean_journey_s"]
            values = [f"{means[c]:.2f}" if c in means else "--" for c, _ in columns]
            lines.append(
                f"| {row['scene']} | {row['regime']} | {row['condition']} | {row['paired_runs']} | "
                + " | ".join(values) + " |"
            )
    (root / "comparison.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
