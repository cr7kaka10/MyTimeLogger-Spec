import json
from pathlib import Path


PLAN_PATH = Path(__file__).parents[2] / "server" / "domain" / "exercise_plan_sample_data.json"
DAYS = ("周一", "周二", "周三", "周四", "周五", "六", "日")


def _plan():
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))["v6"]


def test_v6_week_has_four_strength_days_two_cardio_days_and_six_machine_core_items():
    days = _plan()["exercisePlan"]
    assert tuple(days) == DAYS
    assert days["周一"]["gym"] == []
    strength_days = [day for day in DAYS if any(item["s"] == "力量" for item in days[day]["gym"])]
    assert strength_days == ["周二", "周三", "周五", "六"]
    assert all(sum(item["scorePoints"] for item in days[day]["gym"]) == 100 for day in DAYS[1:])
    cores = [item for day in DAYS[1:] for item in days[day]["gym"] if item["s"] == "核心"]
    assert len(cores) == 6
    assert all("卷腹机" in item["name"] or "力量塔" in item["name"] for item in cores)


def test_v6_formal_cardio_phase_totals_are_250_280_300_minutes():
    days = _plan()["exercisePlan"]
    for phase, expected in enumerate((250, 280, 300)):
        minutes = sum(item["phaseMinutes"][phase] for day in DAYS[1:]
                      for item in days[day]["gym"] if item["s"] == "有氧")
        assert minutes == expected
    assert all(any(item["s"] == "有氧" for item in days[day]["gym"]) for day in ("周四", "日"))


def test_v6_is_exercise_only_and_uses_available_machines():
    plan = _plan()
    assert plan["exercisePoints"] == 100
    assert plan["categoryOrder"] == ["运动训练"]
    assert plan["diet"] == []
    items = [item for day in DAYS for item in plan["exercisePlan"][day]["gym"]]
    assert all(item["scoreScope"] == "training" for item in items)
    names = " ".join(item["name"] for item in items)
    assert not any(forbidden in names for forbidden in ("单车", "哑铃", "杠铃", "龙门架", "鸟狗式", "侧平板"))
    assert all(item["sets"] and item["intensity"] for item in items)


def test_v6_stairs_progression_and_machine_substitution_share_one_score():
    days = _plan()["exercisePlan"]
    thursday_stairs = next(item for item in days["周四"]["gym"] if "爬楼机" in item["name"])
    sunday_stairs = next(item for item in days["日"]["gym"] if "爬楼机" in item["name"])
    assert thursday_stairs["phaseMinutes"] == [10, 15, 20]
    assert sunday_stairs["phaseMinutes"] == [10, 10, 10]
    assert "改椭圆同等时长" in thursday_stairs["intensity"]
    substitute = [item for item in days["周五"]["gym"] if "肩不适改蝴蝶机" in item["name"]]
    assert len(substitute) == 1 and substitute[0]["scorePoints"] == 8
    assert "二选一只计一次分" in substitute[0]["intensity"]
