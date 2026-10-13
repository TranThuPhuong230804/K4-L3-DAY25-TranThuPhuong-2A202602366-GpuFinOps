from finops import pricing
from missions import m1_efficiency_audit, m2_inference_levers, m3_purchasing, m5_report


def test_cache_break_even_and_gate():
    assert pricing.cache_break_even_reads(1.25, 0.10) == 1
    assert not pricing.cache_is_worth_it(0, 1.25, 0.10)
    assert pricing.cache_is_worth_it(1, 1.25, 0.10)


def test_risk_adjusted_spot_and_reserved_terms():
    assert pricing.recommend_tier(
        8,
        True,
        gpu_type="A10G",
        on_demand_hr=10,
        spot_hr=9,
        interruption_rate=0.50,
    ) == "on_demand"
    assert pricing.select_reserved_term(30, 2.5, 2.0, 1.4)["term"] == "on_demand"
    assert pricing.select_reserved_term(1095, 2.5, 2.0, 1.4)["term"] == "3yr"


def test_mbu_rightsizing_has_capacity_and_bandwidth_headroom():
    result = m1_efficiency_audit.run(verbose=False)
    assert result["rightsize_monthly_savings"] > 0
    assert result["rightsize_recommendations"]
    for row in result["rightsize_recommendations"]:
        assert row["target_hbm_gb"] >= row["required_hbm_gb"]
        assert row["target_bw_tbs"] >= row["required_bw_tbs"]


def test_cache_and_reasoning_extensions_are_measured():
    result = m2_inference_levers.run(verbose=False)
    assert all(row["avg_reads"] >= row["break_even_reads"] for row in result["cache_analysis"].values())
    assert result["reasoning"]["energy_share_pct"] > result["reasoning"]["request_share_pct"]
    assert result["reasoning"]["cap_savings_usd"] > 0
    assert result["reasoning"]["cap_savings_wh"] > 0


def test_carbon_extension_compares_all_regions():
    result = m3_purchasing.run(verbose=False)
    carbon = result["carbon_scheduling"]
    assert len(carbon["regions"]) == 5
    assert carbon["cleanest_region"] == "europe-north1"
    assert carbon["carbon_saved_kg"] > 0
    assert len(result["policy_matrix"]) == 42


def test_report_records_all_extensions():
    result = m5_report.run(verbose=False)
    assert result["extensions_completed"] == 5
