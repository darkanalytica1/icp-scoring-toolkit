from icp_toolkit import synth


def test_generate_universe_is_deterministic_for_same_seed():
    run_1 = synth.generate_universe(n=250, seed=99)
    run_2 = synth.generate_universe(n=250, seed=99)
    assert [c.as_dict() for c in run_1] == [c.as_dict() for c in run_2]


def test_generate_universe_differs_across_seeds():
    run_1 = synth.generate_universe(n=250, seed=1)
    run_2 = synth.generate_universe(n=250, seed=2)
    assert [c.name for c in run_1] != [c.name for c in run_2]


def test_generate_universe_produces_the_requested_size():
    companies = synth.generate_universe(n=123, seed=1)
    assert len(companies) == 123
    ids = {c.company_id for c in companies}
    assert len(ids) == 123


def test_generate_universe_contains_realistic_messiness():
    companies = synth.generate_universe(n=2000, seed=synth.SEED)
    missing_phone = sum(1 for c in companies if not c.phone)
    missing_domain = sum(1 for c in companies if not c.domain)
    assert 0 < missing_phone < len(companies)
    assert 0 < missing_domain < len(companies)

    # At least one phone number must be shared across several companies,
    # otherwise the shared-phone teaching example has nothing to find.
    phone_counts: dict[str, int] = {}
    for c in companies:
        if c.phone:
            phone_counts[c.phone] = phone_counts.get(c.phone, 0) + 1
    assert max(phone_counts.values()) >= 4


def test_generate_call_history_matches_company_ids():
    companies = synth.generate_universe(n=200, seed=synth.SEED)
    history = synth.generate_call_history(companies, seed=synth.SEED)
    company_ids = {c.company_id for c in companies}
    assert {r.company_id for r in history} == company_ids
    for r in history:
        if not r.was_called:
            assert r.closed_won is None
        else:
            assert r.closed_won in (True, False)
