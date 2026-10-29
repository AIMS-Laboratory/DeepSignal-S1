import pytest

from deepsignal_s1.data import read_json, write_json
from deepsignal_s1.summary import summarize


@pytest.fixture
def paired(tmp_path):
    suite = {
        "seeds": [1, 2],
        "cases": [{"scene": "demo", "regime": "east-west", "condition": "clean"}],
    }
    write_json(tmp_path / "suite.json", suite)
    for seed in suite["seeds"]:
        for controller, journey in [("s1", 15), ("fixed", 20)]:
            target = tmp_path / f"demo-east-west-clean-{seed}" / controller
            write_json(
                target / "plan.json", {"seed": seed, "vehicles": ["same-arrivals"]}
            )
            write_json(
                target / "report.json",
                {
                    "scene": "demo",
                    "regime": "east-west",
                    "condition": "clean",
                    "seed": seed,
                    "complete": True,
                    "failure": None,
                    "model_version": "release-a" if controller == "s1" else None,
                    "baseline": "engineering-fixed" if controller == "fixed" else None,
                    "metrics": {
                        "complete": True,
                        "vehicles": 10,
                        "mean_journey_s": journey,
                    },
                },
            )
    return tmp_path


def test_summary_requires_all_seeds_and_reports(paired):
    result = summarize(paired, paired / "suite.json", ("s1", "fixed"))
    assert result["rows"][0]["paired_runs"] == 2
    assert result["rows"][0]["improvement_pct"]["fixed"] == 25


def test_demand_regimes_are_not_merged(paired):
    suite = read_json(paired / "suite.json")
    suite["cases"].append(
        {"scene": "demo", "regime": "north-south", "condition": "clean"}
    )
    write_json(paired / "suite.json", suite)
    for seed in suite["seeds"]:
        for controller in ("s1", "fixed"):
            source = paired / f"demo-east-west-clean-{seed}" / controller
            target = paired / f"demo-north-south-clean-{seed}" / controller
            write_json(target / "plan.json", read_json(source / "plan.json"))
            report = read_json(source / "report.json")
            report["regime"] = "north-south"
            report["metrics"]["mean_journey_s"] *= 2
            write_json(target / "report.json", report)
    rows = summarize(paired, paired / "suite.json", ("s1", "fixed"))["rows"]
    assert [(r["regime"], r["paired_runs"]) for r in rows] == [
        ("east-west", 2), ("north-south", 2)
    ]
    assert [r["mean_journey_s"]["s1"] for r in rows] == [15, 30]


def test_model_versions_cannot_be_combined(paired):
    from deepsignal_s1.data import read_json

    path = paired / "demo-east-west-clean-2/s1/report.json"
    report = read_json(path)
    report["model_version"] = "release-b"
    write_json(path, report)
    with pytest.raises(ValueError, match="exactly one"):
        summarize(paired, paired / "suite.json", ("s1", "fixed"))


def test_incomplete_run_cannot_be_dropped(paired):
    from deepsignal_s1.data import read_json

    path = paired / "demo-east-west-clean-2/s1/report.json"
    report = read_json(path)
    report["complete"] = False
    write_json(path, report)
    with pytest.raises(ValueError, match="Incomplete"):
        summarize(paired, paired / "suite.json", ("s1", "fixed"))


def test_different_arrivals_cannot_be_compared(paired):
    write_json(
        paired / "demo-east-west-clean-2/fixed/plan.json",
        {"seed": 9, "vehicles": ["different"]},
    )
    with pytest.raises(ValueError, match="Arrival plans differ"):
        summarize(paired, paired / "suite.json", ("s1", "fixed"))


def test_special_summary_does_not_require_or_emit_fixed_records(paired):
    suite = read_json(paired / "suite.json")
    suite['cases'][0]['condition'] = 'defocus'
    write_json(paired / 'suite.json', suite)
    for seed in suite['seeds']:
        for controller in ('s1', 'visual-pressure'):
            source = paired / f'demo-east-west-clean-{seed}/s1'
            target = paired / f'demo-east-west-defocus-{seed}' / controller
            report = read_json(source / 'report.json')
            report.update(condition='defocus', controller=controller)
            write_json(target / 'report.json', report)
            write_json(target / 'plan.json', read_json(source / 'plan.json'))
    result = summarize(paired, paired / 'suite.json')
    assert set(result['rows'][0]['mean_journey_s']) == {'s1', 'visual-pressure'}
    assert 'fixed' not in result['rows'][0]['improvement_pct']
