import pytest

from app.services import sip


def test_zero_return_is_plain_addition():
    g = sip.goal_projection(0, 1000, 0, 1, 12000)
    assert g["projected_value"] == 12000 and g["on_track"] is True


def test_lump_sum_compounds_monthly():
    g = sip.goal_projection(10000, 0, 12, 1, 1)
    assert g["projected_value"] == pytest.approx(10000 * 1.01**12, abs=0.01)


def test_sip_matches_annuity_formula():
    # 5000/month, 12% a year (1%/month), 10 years, end-of-month contributions
    expected = 5000 * ((1.01**120 - 1) / 0.01)
    assert sip.future_value(0, 5000, 12, 120) == pytest.approx(expected)
    g = sip.goal_projection(0, 5000, 12, 10, 1)
    assert g["projected_value"] == pytest.approx(expected, abs=0.01)
    assert g["total_invested"] == 600000
    assert g["estimated_returns"] == pytest.approx(expected - 600000, abs=0.01)


def test_required_sip_reaches_target():
    g = sip.goal_projection(0, 0, 10, 5, 100000)
    again = sip.goal_projection(0, g["required_monthly_sip"], 10, 5, 100000)
    assert again["projected_value"] == pytest.approx(100000, rel=0.001)


def test_required_sip_is_zero_when_lump_sum_already_enough():
    assert sip.required_sip(1_000_000, 100_000, 8, 60) == 0.0


def test_year_wise_series_is_consistent():
    g = sip.goal_projection(1000, 100, 8, 3, 5000)
    assert [r["year"] for r in g["series"]] == [1, 2, 3]
    last = g["series"][-1]
    assert last["value"] == g["projected_value"] and last["invested"] == 1000 + 100 * 36
    assert last["returns"] == pytest.approx(last["value"] - last["invested"], abs=0.01)


def test_estimates_are_labelled():
    g = sip.goal_projection(0, 100, 8, 2, 10000)
    assert g["is_estimate"] is True and "not a guaranteed" in g["disclaimer"]


def test_validation():
    for args in ((0, 100, 8, 0, 1), (0, 100, 8, 51, 1), (0, 100, 31, 5, 1), (0, -1, 8, 5, 1), (-5, 0, 8, 5, 1)):
        with pytest.raises(sip.PlanError):
            sip.goal_projection(*args)


def test_compare_scenarios_solves_missing_sip():
    out = sip.compare_scenarios(0, 1_000_000, [
        {"name": "Safe", "years": 10, "annual_return_pct": 7},
        {"name": "Bold", "years": 10, "annual_return_pct": 12},
        {"name": "Fixed", "years": 10, "annual_return_pct": 10, "monthly_sip": 1000}])
    assert out[0]["sip_was_solved"] and out[0]["projected_value"] == pytest.approx(1_000_000, rel=0.001)
    assert out[0]["monthly_sip"] > out[1]["monthly_sip"]   # lower assumed return needs a bigger SIP
    assert out[2]["sip_was_solved"] is False and out[2]["on_track"] is False
    with pytest.raises(sip.PlanError):
        sip.compare_scenarios(0, 1, [])
