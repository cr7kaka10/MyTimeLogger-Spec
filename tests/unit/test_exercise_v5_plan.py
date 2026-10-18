import json
from pathlib import Path


PLAN_PATH = Path(__file__).parents[2] / "server" / "domain" / "exercise_plan_sample_data.json"


def _plan():
    return json.loads(PLAN_PATH.read_text(encoding="utf-8"))["v5"]


def test_v5_has_monday_rest_and_six_exact_ninety_minute_days():
    plan = _plan()
    assert plan["exercisePlan"]["周一"]["gym"] == []
    for day in ("周二", "周三", "周四", "周五", "六", "日"):
        items = plan["exercisePlan"][day]["gym"]
        assert sum(item["durationMinutes"] for item in items) == 90
        assert sum(item["scorePoints"] for item in items) == 75
    assert all("杠铃" not in item["name"] for day in plan["exercisePlan"].values() for item in day["gym"])


def test_v5_prescriptions_are_executable_and_cover_three_strength_days():
    plan = _plan()
    for day in ("周二", "周四", "六"):
        strength = [item for item in plan["exercisePlan"][day]["gym"] if item["s"] == "力量"]
        assert len(strength) == 6
        assert all("组" in item["sets"] or "×" in item["sets"] for item in strength)
        assert all(len(item["intensity"]) >= 25 for item in strength)
    cardio_names = " ".join(item["name"] for day in plan["exercisePlan"].values() for item in day["gym"])
    assert all(name in cardio_names for name in ("跑步机", "爬楼机", "椭圆漫步机"))
    assert "卧式健身车" not in cardio_names


def test_v5_has_three_stair_days_and_walking_only_treadmills():
    plan = _plan()
    stair_days = [day for day, value in plan["exercisePlan"].items()
                  if any("爬楼机" in item["name"] for item in value["gym"])]
    assert stair_days == ["周三", "周五", "日"]
    treadmills = [item for day in plan["exercisePlan"].values()
                  for item in day["gym"] if "跑步机" in item["name"]]
    assert treadmills and all("不跑" in item["intensity"] for item in treadmills)
    sunday = plan["exercisePlan"]["日"]["gym"]
    assert next(item for item in sunday if "爬楼机" in item["name"])["durationRange"] == [5, 10]
    assert sum(item["durationMinutes"] for item in sunday) == 90


def test_v5_personal_calorie_budget_contract():
    text = " ".join(item["when"] + item["text"] for item in _plan()["progress"])
    assert all(value in text for value in ("37岁", "5000步", "1800", "2000", "2100", "1950"))
    assert all(value in text for value in ("1990", "150g", "7日均值", "150–200"))
    assert "不吃回" in text


def test_v5_diet_progression_and_safety_contract():
    plan = _plan()
    assert [rule["ruleKey"] for rule in plan["diet"]] == [
        "protein_at_lunch_and_dinner", "vegetables_at_lunch_and_dinner",
        "controlled_staple_and_no_sugary_drink",
    ]
    progress = " ".join(item["when"] + item["text"] for item in plan["progress"])
    assert all(phase in progress for phase in ("第1–2周", "第3–4周", "第5–8周", "第9–12周"))
    assert sum("外食" in item["when"] for item in plan["progress"]) == 5
    assert all(word in progress for word in ("胸闷", "眩晕", "关节痛", "0.5–1.0kg"))
