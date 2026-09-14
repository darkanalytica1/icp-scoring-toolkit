from icp_toolkit import evaluate, quality, scoring, synth


def test_coverage_report_percentages_are_bounded(config):
    companies = [c.as_dict() for c in synth.generate_universe(n=300, seed=3)]
    flags = quality.compute_quality_flags(companies, config["contactability_model"])
    scored = scoring.score_universe(companies, flags, config)
    scores_by_id = {s.company_id: s for s in scored}

    report = evaluate.coverage_report(companies, flags, scores_by_id)

    assert report["universe_size"] == 300
    for key in (
        "pct_has_phone", "pct_shared_phone_of_universe", "pct_domain_verified_recomputed",
        "pct_domain_verified_declared", "pct_email_plausible", "pct_duplicate_rows",
    ):
        assert 0.0 <= report[key] <= 100.0
    assert sum(report["tier_distribution"].values()) == 300


def test_backtest_report_covers_every_tier(config):
    companies = [c.as_dict() for c in synth.generate_universe(n=400, seed=5)]
    flags = quality.compute_quality_flags(companies, config["contactability_model"])
    scored = scoring.score_universe(companies, flags, config)
    scores_by_id = {s.company_id: s for s in scored}
    call_history = synth.generate_call_history(
        [c for c in synth.generate_universe(n=400, seed=5)], seed=5
    )

    rows = evaluate.backtest_report(companies, scores_by_id, call_history)

    tiers_seen = {r.tier for r in rows}
    expected_tiers = {f"{f}{i}" for f in "ABC" for i in "123"}
    assert tiers_seen == expected_tiers
    for r in rows:
        assert r.called <= r.universe_size
        assert 0.0 <= r.win_rate_pct <= 100.0


def test_survivorship_bias_check_flags_sparse_tiers(config):
    row_low = evaluate.TierBacktestRow(
        tier="C3", universe_size=1000, called=3, call_coverage_pct=0.3,
        wins=0, win_rate_pct=0.0, confidence="low (sparse or biased sample, do not trust ranking)",
    )
    row_ok = evaluate.TierBacktestRow(
        tier="A1", universe_size=1000, called=500, call_coverage_pct=50.0,
        wins=100, win_rate_pct=20.0, confidence="ok",
    )
    warnings = evaluate.survivorship_bias_check([row_low, row_ok])
    assert any("C3" in w for w in warnings)


def test_survivorship_bias_check_handles_no_data():
    row = evaluate.TierBacktestRow(
        tier="C3", universe_size=10, called=0, call_coverage_pct=0.0,
        wins=0, win_rate_pct=0.0, confidence="no data",
    )
    warnings = evaluate.survivorship_bias_check([row])
    assert warnings == ["No historical call data available; cannot backtest yet."]
