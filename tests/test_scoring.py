from icp_toolkit import quality, scoring, synth


def _no_signal_company():
    return {
        "hiring_open_roles": 0,
        "funding_event_days_ago": None,
        "expansion_signal": False,
        "expansion_signal_days_ago": None,
        "tech_adoption_signal": False,
        "tech_adoption_signal_days_ago": None,
    }


def test_compute_fit_score_is_deterministic(config):
    company = {"revenue_eur": 3_000_000, "headcount": 80, "industry": "software", "region": "DACH"}
    score_1, _ = scoring.compute_fit_score(company, config)
    score_2, _ = scoring.compute_fit_score(company, config)
    assert score_1 == score_2


def test_fit_score_rewards_the_configured_sweet_spot(config):
    sweet_spot = {"revenue_eur": 3_000_000, "headcount": 80, "industry": "software", "region": "UK_I"}
    off_target = {"revenue_eur": 30_000, "headcount": 2, "industry": "agriculture", "region": "Overseas"}
    sweet_score, _ = scoring.compute_fit_score(sweet_spot, config)
    off_score, _ = scoring.compute_fit_score(off_target, config)
    assert sweet_score > off_score


def test_intent_score_with_no_signals_is_zero(config):
    score, components = scoring.compute_intent_score(_no_signal_company(), config)
    assert score == 0.0
    assert all(v == 0.0 for v in components.values())


def test_intent_score_decays_with_signal_age(config):
    fresh = dict(_no_signal_company(), funding_event_days_ago=1)
    old = dict(_no_signal_company(), funding_event_days_ago=500)
    fresh_score, _ = scoring.compute_intent_score(fresh, config)
    old_score, _ = scoring.compute_intent_score(old, config)
    assert fresh_score > old_score > 0.0


def test_intent_score_hiring_is_capped(config):
    lots_of_roles = dict(_no_signal_company(), hiring_open_roles=50)
    few_roles = dict(_no_signal_company(), hiring_open_roles=1)
    lots_score, lots_components = scoring.compute_intent_score(lots_of_roles, config)
    few_score, _ = scoring.compute_intent_score(few_roles, config)
    cap = config["intent_model"]["hiring_points_cap"]
    assert lots_components["hiring"] == cap
    assert lots_score > few_score


def test_fit_and_intent_tier_boundaries(config):
    a_threshold = config["tiering"]["fit_thresholds"]["A"]
    b_threshold = config["tiering"]["fit_thresholds"]["B"]
    assert scoring.fit_tier_for(a_threshold, config) == "A"
    assert scoring.fit_tier_for(a_threshold - 0.1, config) != "A"
    assert scoring.fit_tier_for(b_threshold, config) == "B"
    assert scoring.fit_tier_for(0, config) == "C"

    one_threshold = config["tiering"]["intent_thresholds"]["1"]
    assert scoring.intent_tier_for(one_threshold, config) == "1"
    assert scoring.intent_tier_for(0, config) == "3"


def test_tier_is_always_one_of_the_nine_valid_combinations(config):
    valid_tiers = {f"{f}{i}" for f in "ABC" for i in "123"}
    companies = [c.as_dict() for c in synth.generate_universe(n=300, seed=11)]
    flags = quality.compute_quality_flags(companies, config["contactability_model"])
    scored = scoring.score_universe(companies, flags, config)
    assert all(s.tier in valid_tiers for s in scored)


def test_score_universe_is_deterministic(config):
    companies = [c.as_dict() for c in synth.generate_universe(n=200, seed=7)]
    flags = quality.compute_quality_flags(companies, config["contactability_model"])

    run_1 = scoring.score_universe(companies, flags, config)
    run_2 = scoring.score_universe(companies, flags, config)

    assert [s.tier for s in run_1] == [s.tier for s in run_2]
    assert [s.fit_score for s in run_1] == [s.fit_score for s in run_2]
    assert [s.intent_score for s in run_1] == [s.intent_score for s in run_2]


def test_contactability_score_penalizes_shared_phone_and_bad_domain(config):
    good_flags = quality.QualityFlags(
        company_id="1", has_phone=True, is_shared_phone=False, phone_reason="ok",
        domain_verified=True, domain_reason="confirmed", email_ok=True, email_reason="ok",
        is_duplicate=False,
    )
    bad_flags = quality.QualityFlags(
        company_id="2", has_phone=True, is_shared_phone=True, phone_reason="shared",
        domain_verified=False, domain_reason="not found", email_ok=False, email_reason="bad",
        is_duplicate=False,
    )
    good_score, _ = scoring.compute_contactability_score(good_flags, config)
    bad_score, _ = scoring.compute_contactability_score(bad_flags, config)
    assert good_score > bad_score
