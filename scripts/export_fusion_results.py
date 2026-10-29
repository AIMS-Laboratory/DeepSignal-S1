#!/usr/bin/env python3
"""Export the public fusion evaluation dataset from immutable run JSON files."""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable


CONDITIONS = ("df9", "mb31", "angle15", "shake5")
CONDITION_LABELS = {
    "clean": "正常视觉",
    "df9": "失焦 σ=9",
    "mb31": "水平运动模糊 31 像素",
    "angle15": "固定偏航 ±15° / 俯仰 ±8°",
    "shake5": "动态抖动峰值 5°",
}
SCENE_LABELS = {"nansha": "南沙", "town": "Town10HD"}
CONTROLLER_LABELS = {
    "s1": "DeepSignal S1",
    "fixed": "工程固定配时",
    "mp": "YOLO + Max Pressure",
}
METRICS = {
    "nansha": {
        "field": "J_H",
        "name": "truncated_mean_journey_time_s",
        "description": "1298 秒有限评估时域内的截断平均行程时间，越低越好。",
        "horizon_s": 1298,
    },
    "town": {
        "field": "J",
        "name": "truncated_total_journey_time_s",
        "description": "518 秒有限评估时域内的截断总行程时间，越低越好。",
        "horizon_s": 518,
    },
}
PROTOCOL = {
    "version": "green-tail5-v1",
    "model_version": "DeepSignal-S1-1.0",
    "phase_mode": "skip",
    "frames": "3 frames at 2-second intervals (4-second observation window)",
    "model": "DeepSignal-S1 BF16, unquantized, fusion adapter ns_adapter_uni_h",
    "latency_scope": "decision-request model calls on RTX 5090; camera/render/control execution excluded",
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def relative_percent(value: float, reference: float) -> float:
    return (value / reference - 1.0) * 100.0


def improvement_percent(value: float, reference: float) -> float:
    return (1.0 - value / reference) * 100.0


def percentile(values: list[float], q: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def aggregate_pairs(rows: Iterable[dict[str, Any]], left: str, right: str) -> dict[str, Any]:
    paired = list(rows)
    if not paired:
        raise ValueError("cannot aggregate an empty paired set")
    left_sum = sum(float(row[left]) for row in paired)
    right_sum = sum(float(row[right]) for row in paired)
    return {
        "pairs": len(paired),
        f"{left}_sum": left_sum,
        f"{right}_sum": right_sum,
        "relative_percent": relative_percent(left_sum, right_sum),
        "improvement_percent": improvement_percent(left_sum, right_sum),
        "wins": sum(float(row[left]) < float(row[right]) for row in paired),
    }


def select_representative(rows: Iterable[dict[str, Any]], group_improvement: float) -> dict[str, Any]:
    candidates = list(rows)
    if not candidates:
        raise ValueError("cannot select a representative from an empty group")
    return min(
        candidates,
        key=lambda row: (abs(float(row["improvement_percent"]) - group_improvement), row["case_id"]),
    )


def extract_model_calls(run: dict[str, Any]) -> list[float]:
    calls: list[float] = []
    for entry in run.get("dec_log", []):
        if len(entry) < 3 or not isinstance(entry[2], (int, float)):
            continue
        source = entry[3] if len(entry) >= 4 else "model"
        if source != "model":
            continue
        calls.append(float(entry[2]))
    return calls


def latency_summary(run_calls: list[list[float]]) -> dict[str, Any]:
    first = [calls[0] for calls in run_calls if calls]
    subsequent = [value for calls in run_calls for value in calls[1:]]
    all_calls = [value for calls in run_calls for value in calls]

    def describe(values: list[float]) -> dict[str, Any]:
        return {
            "count": len(values),
            "mean_ms": statistics.fmean(values),
            "median_ms": statistics.median(values),
            "p95_ms": percentile(values, 0.95),
            "max_ms": max(values),
            "under_1s_fraction": sum(value < 1000 for value in values) / len(values),
        }

    return {
        "scope": PROTOCOL["latency_scope"],
        "hardware": "NVIDIA RTX 5090 32 GB",
        "precision": "BF16, unquantized",
        "input": "3 frames at 2-second intervals",
        "all_calls": describe(all_calls),
        "first_call_per_run": describe(first),
        "subsequent_calls": describe(subsequent),
        "samples_ms": all_calls,
    }


def fixed_index(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    records = read_json(path)["records"]
    return {("town" if r["scene"] == "town10hd" else "nansha", r["tag"]): r for r in records}


def result_index(directory: Path, metric_field: str) -> dict[str, dict[str, Any]]:
    indexed = {}
    for path in sorted(directory.glob("*.json")):
        run = read_json(path)
        if run.get("fail") is not None:
            raise ValueError(f"failed run cannot enter public results: {path}")
        if metric_field not in run:
            raise ValueError(f"missing {metric_field}: {path}")
        run["_path"] = str(path.resolve())
        indexed[run["tag"]] = run
    return indexed


def paired_cases(
    scene: str,
    condition: str,
    s1_dir: Path,
    mp_dir: Path,
    fixed: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    field = METRICS[scene]["field"]
    s1 = result_index(s1_dir, field)
    mp = result_index(mp_dir, field)
    if set(s1) != set(mp):
        raise ValueError(f"unpaired S1/MP cases for {scene}/{condition}")
    rows = []
    for tag in sorted(s1):
        s1_value = float(s1[tag][field])
        mp_value = float(mp[tag][field])
        row = {
            "case_id": tag,
            "scene": scene,
            "condition": condition,
            "metric": METRICS[scene]["name"],
            "s1": s1_value,
            "mp": mp_value,
            "improvement_percent": improvement_percent(s1_value, mp_value),
            "jobs": {
                "s1": f"{'nansha-full' if scene == 'nansha' and condition == 'clean' else 'nansha-pilot' if scene == 'nansha' else 'town'}/{condition}/fusion/{tag}",
                "mp": f"{'nansha-full' if scene == 'nansha' and condition == 'clean' else 'nansha-pilot' if scene == 'nansha' else 'town'}/{condition}/mp/{tag}",
            },
            "source_records": {
                "s1": {
                    "record": str(Path(s1[tag]["_path"]).relative_to(s1_dir.parents[3])),
                    "metric_value": s1_value,
                    "failure": s1[tag].get("fail"),
                    "model": "ns_adapter_uni_h",
                    "horizon_s": METRICS[scene]["horizon_s"],
                    "vehicles": s1[tag].get("N"),
                    "arrived": s1[tag].get("arrived"),
                },
                "mp": {
                    "record": str(Path(mp[tag]["_path"]).relative_to(mp_dir.parents[3])),
                    "metric_value": mp_value,
                    "failure": mp[tag].get("fail"),
                    "model": "YOLO + Max Pressure",
                    "horizon_s": METRICS[scene]["horizon_s"],
                    "vehicles": mp[tag].get("N"),
                    "arrived": mp[tag].get("arrived"),
                },
            },
            "_raw_paths": {"s1": s1[tag]["_path"], "mp": mp[tag]["_path"]},
        }
        if fixed is not None:
            fixed_run = fixed.get((scene, tag))
            if fixed_run is None:
                raise ValueError(f"missing engineering-fixed record for {scene}/{tag}")
            row["fixed"] = float(fixed_run[field])
            row["source_records"]["fixed"] = {
                "record": "results/engineering-fixed-2026-10-26.json",
                "metric_value": float(fixed_run[field]),
                "failure": fixed_run.get("fail"),
                "model": "engineering-fixed",
                "horizon_s": fixed_run.get("horizon_s", METRICS[scene]["horizon_s"]),
                "vehicles": fixed_run.get("N"),
                "arrived": fixed_run.get("arrived"),
            }
        rows.append(row)
    return rows


def build_dataset(source_root: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    unified = source_root / "unified-visual-20261028"
    pilot = source_root / "fusion-pilot-20261029"
    fixed = fixed_index(pilot / "engineering-fixed-reference.json")

    normal_cases = {
        "nansha": paired_cases(
            "nansha", "clean",
            unified / "results/nansha-full/clean/fusion",
            unified / "results/nansha-full/clean/mp", fixed,
        ),
        "town": paired_cases(
            "town", "clean",
            pilot / "results/town/clean/fusion",
            pilot / "results/town/clean/mp", fixed,
        ),
    }
    normal = []
    for scene, cases in normal_cases.items():
        summary = aggregate_pairs(cases, "s1", "fixed")
        mp_summary = aggregate_pairs(cases, "s1", "mp")
        normal.append({
            "scene": scene,
            "scene_label": SCENE_LABELS[scene],
            "metric": METRICS[scene],
            "cases": len(cases),
            "sums": {k: sum(row[k] for row in cases) for k in ("s1", "fixed", "mp")},
            "fixed_normalized": {
                "s1": sum(row["s1"] for row in cases) / sum(row["fixed"] for row in cases) * 100,
                "fixed": 100.0,
                "mp": sum(row["mp"] for row in cases) / sum(row["fixed"] for row in cases) * 100,
            },
            "s1_vs_fixed_improvement_percent": summary["improvement_percent"],
            "s1_vs_mp_improvement_percent": mp_summary["improvement_percent"],
            "case_results": cases,
        })

    extreme = []
    degradation = []
    latency_runs_by_scene: dict[str, set[str]] = {"nansha": set(), "town": set()}
    for scene in ("nansha", "town"):
        clean_map = {row["case_id"]: row for row in normal_cases[scene]}
        # Strict degradation pairing uses NS9/Town5 from the pilot plan.
        if scene == "nansha":
            pilot_tags = sorted(p.name for p in (pilot / "results/nansha-pilot/df9/fusion").glob("*.json"))
            clean_s1 = result_index(unified / "results/nansha-full/clean/fusion", "J_H")
            clean_mp = result_index(unified / "results/nansha-full/clean/mp", "J_H")
            clean_map = {
                Path(tag).stem: {
                    "s1": float(clean_s1[Path(tag).stem]["J_H"]),
                    "mp": float(clean_mp[Path(tag).stem]["J_H"]),
                }
                for tag in pilot_tags
            }
        for condition in CONDITIONS:
            base = pilot / ("results/nansha-pilot" if scene == "nansha" else "results/town") / condition
            cases = paired_cases(scene, condition, base / "fusion", base / "mp")
            agg = aggregate_pairs(cases, "s1", "mp")
            extreme.append({
                "scene": scene,
                "scene_label": SCENE_LABELS[scene],
                "condition": condition,
                "condition_label": CONDITION_LABELS[condition],
                "metric": METRICS[scene],
                "cases": len(cases),
                "sums": {"s1": agg["s1_sum"], "mp": agg["mp_sum"]},
                "improvement_percent": agg["improvement_percent"],
                "wins": agg["wins"],
                "target_percent": 10.0,
                "case_results": cases,
            })
            for controller in ("s1", "mp"):
                paired = [{"special": row[controller], "clean": clean_map[row["case_id"]][controller]} for row in cases]
                deg = aggregate_pairs(paired, "special", "clean")
                degradation.append({
                    "scene": scene,
                    "scene_label": SCENE_LABELS[scene],
                    "condition": condition,
                    "condition_label": CONDITION_LABELS[condition],
                    "controller": controller,
                    "controller_label": CONTROLLER_LABELS[controller],
                    "pairs": deg["pairs"],
                    "degradation_percent": deg["relative_percent"],
                })
            for row in cases:
                latency_runs_by_scene[scene].add(row["_raw_paths"]["s1"])

    for cases in normal_cases.values():
        for row in cases:
            latency_runs_by_scene[row["scene"]].add(row["_raw_paths"]["s1"])
    scene_latency = {}
    all_latency_runs = []
    for scene, paths in latency_runs_by_scene.items():
        runs = [extract_model_calls(read_json(Path(path))) for path in sorted(paths)]
        all_latency_runs.extend(runs)
        scene_latency[scene] = {
            "model_cases": len(runs),
            **latency_summary(runs),
        }
    latency = latency_summary(all_latency_runs)
    latency["model_cases"] = len(all_latency_runs)
    latency["by_scene"] = scene_latency
    latency["coverage"] = {
        "unified_visual_20261028_nansha_clean_model_cases": 72,
        "fusion_pilot_20261029_model_cases": 61,
        "fusion_pilot_breakdown": {
            "nansha_extreme": 36,
            "town_clean": 5,
            "town_extreme": 20,
        },
        "pilot_total_runs_both_controllers": 122,
    }

    dataset = {
        "schema_version": "fusion-results-v1",
        "generated_date": "2026-10-30",
        "protocol": PROTOCOL,
        "source_experiments": ["unified-visual-20261028", "fusion-pilot-20261029"],
        "controllers": CONTROLLER_LABELS,
        "conditions": CONDITION_LABELS,
        "normal": normal,
        "extreme": extreme,
        "degradation": degradation,
        "latency": latency,
        "notes": [
            "场景间指标定义不同，南沙与 Town 不合并。",
            "特殊视觉不生成相对工程固定配时成绩。",
            "所有改善率均由配对案例指标和计算，不平均逐案例百分比。",
            "4090 无可用日志，因此不进入正式延迟结果。",
            "RTX 5090 延迟覆盖 133 个 S1 模型案例：前序 unified-visual-20261028 南沙正常视觉 72 例，以及 fusion-pilot-20261029 的 61 个 S1 案例（南沙特殊视觉 36、Town 正常视觉 5、Town 特殊视觉 20）。pilot 的 122 回合包含 S1 与 YOLO+MP 两臂，不能等同为 122 个模型案例。",
        ],
    }

    media_cases = {"schema_version": "fusion-media-cases-v1", "generated_date": "2026-10-30", "cases": []}
    for row in normal:
        group = row["case_results"]
        representative = select_representative(group, row["s1_vs_mp_improvement_percent"])
        media_cases["cases"].append({
            "scene": row["scene"], "condition": "clean", "case_id": representative["case_id"],
            "group_improvement_percent": row["s1_vs_mp_improvement_percent"],
            "case_improvement_percent": representative["improvement_percent"],
            "selection_basis": "S1 相对 YOLO+MP 的案例改善最接近该场景总体改善",
            "jobs": representative["jobs"], "raw_paths": representative["_raw_paths"],
        })
    for row in extreme:
        representative = select_representative(row["case_results"], row["improvement_percent"])
        media_cases["cases"].append({
            "scene": row["scene"], "condition": row["condition"], "case_id": representative["case_id"],
            "group_improvement_percent": row["improvement_percent"],
            "case_improvement_percent": representative["improvement_percent"],
            "selection_basis": "S1 相对 YOLO+MP 的案例改善最接近该场景/条件总体改善",
            "jobs": representative["jobs"], "raw_paths": representative["_raw_paths"],
        })
    for group in dataset["normal"] + dataset["extreme"]:
        for case in group["case_results"]:
            case.pop("_raw_paths", None)
    return dataset, media_cases


def write_csv_outputs(prefix: Path, dataset: dict[str, Any]) -> None:
    common = {
        "protocol_version": PROTOCOL["version"],
        "model_version": PROTOCOL["model_version"],
    }
    case_path = prefix.with_suffix(".csv")
    fields = ["scene", "condition", "case_id", "controller", "value", "metric", "metric_description", "horizon_s", "protocol_version", "model_version", "source_record", "failure", "vehicles", "arrived"]
    with case_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        groups = [("normal", row) for row in dataset["normal"]] + [("extreme", row) for row in dataset["extreme"]]
        for kind, group in groups:
            condition = "clean" if kind == "normal" else group["condition"]
            controllers = ("s1", "fixed", "mp") if kind == "normal" else ("s1", "mp")
            for case in group["case_results"]:
                for controller in controllers:
                    writer.writerow({
                        "scene": group["scene"], "condition": condition, "case_id": case["case_id"],
                        "controller": controller, "value": case[controller], "metric": group["metric"]["name"],
                        "metric_description": group["metric"]["description"], "horizon_s": group["metric"]["horizon_s"],
                        **common,
                        "source_record": case["source_records"][controller]["record"],
                        "failure": case["source_records"][controller]["failure"],
                        "vehicles": case["source_records"][controller]["vehicles"],
                        "arrived": case["source_records"][controller]["arrived"],
                    })

    for suffix, rows, fields in (
        ("-normal.csv", dataset["normal"], ["scene", "cases", "metric", "s1_sum", "fixed_sum", "mp_sum", "s1_fixed_normalized", "fixed_normalized", "mp_fixed_normalized", "s1_vs_fixed_improvement_percent", "s1_vs_mp_improvement_percent"]),
        ("-extreme.csv", dataset["extreme"], ["scene", "condition", "cases", "metric", "s1_sum", "mp_sum", "improvement_percent", "wins", "target_percent"]),
        ("-degradation.csv", dataset["degradation"], ["scene", "condition", "controller", "pairs", "degradation_percent"]),
    ):
        with Path(str(prefix) + suffix).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            for row in rows:
                if suffix == "-normal.csv":
                    writer.writerow({
                        "scene": row["scene"], "cases": row["cases"], "metric": row["metric"]["name"],
                        **{f"{k}_sum": v for k, v in row["sums"].items()},
                        "s1_fixed_normalized": row["fixed_normalized"]["s1"],
                        "fixed_normalized": row["fixed_normalized"]["fixed"],
                        "mp_fixed_normalized": row["fixed_normalized"]["mp"],
                        "s1_vs_fixed_improvement_percent": row["s1_vs_fixed_improvement_percent"],
                        "s1_vs_mp_improvement_percent": row["s1_vs_mp_improvement_percent"],
                    })
                elif suffix == "-extreme.csv":
                    writer.writerow({"scene": row["scene"], "condition": row["condition"], "cases": row["cases"], "metric": row["metric"]["name"], "s1_sum": row["sums"]["s1"], "mp_sum": row["sums"]["mp"], "improvement_percent": row["improvement_percent"], "wins": row["wins"], "target_percent": row["target_percent"]})
                else:
                    writer.writerow({key: row[key] for key in fields})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, default=Path("/mnt/ShareData/projects/DeepSignal_E2E/out"))
    parser.add_argument("--output", type=Path, default=Path("results/fusion-2026-10-30.json"))
    args = parser.parse_args()
    dataset, media_cases = build_dataset(args.source_root)
    write_json(args.output, dataset)
    prefix = args.output.with_suffix("")
    write_csv_outputs(prefix, dataset)
    write_json(args.output.with_name("fusion-2026-10-30-media-cases.json"), media_cases)


if __name__ == "__main__":
    main()
