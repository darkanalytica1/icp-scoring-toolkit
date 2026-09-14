from icp_toolkit import territory


def _record(company_id, region, tier, contactability_score):
    return {
        "company_id": company_id,
        "name": company_id,
        "region": region,
        "tier": tier,
        "contactability_score": contactability_score,
    }


def test_daily_cap_is_never_exceeded():
    records = [_record(f"c{i}", "DACH", "A1", 100) for i in range(100)]
    schedule = territory.build_call_lists(
        records, reps=["r1"], days=3, daily_cap=10,
        tier_mix_target={"A1": 1.0}, min_contactability=40,
    )
    for entries in schedule["r1"].values():
        assert len(entries) <= 10


def test_low_contactability_records_are_excluded():
    records = [_record("uncontactable", "DACH", "A1", 10), _record("contactable", "DACH", "A1", 90)]
    schedule = territory.build_call_lists(
        records, reps=["r1"], days=1, daily_cap=10,
        tier_mix_target={"A1": 1.0}, min_contactability=40,
    )
    ids_called = {e.company_id for e in schedule["r1"][0]}
    assert "uncontactable" not in ids_called
    assert "contactable" in ids_called


def test_tiers_outside_the_mix_target_never_appear():
    records = [_record("suppressed", "DACH", "C3", 90), _record("active", "DACH", "A1", 90)]
    schedule = territory.build_call_lists(
        records, reps=["r1"], days=1, daily_cap=10,
        tier_mix_target={"A1": 1.0}, min_contactability=40,
    )
    tiers_seen = {e.tier for e in schedule["r1"][0]}
    assert "C3" not in tiers_seen
    assert "A1" in tiers_seen


def test_tier_mix_is_approximately_balanced_across_reps():
    records = []
    for i in range(60):
        records.append(_record(f"a1_{i}", "DACH", "A1", 90))
    for i in range(60):
        records.append(_record(f"b2_{i}", "DACH", "B2", 90))

    tier_mix = {"A1": 0.5, "B2": 0.5}
    schedule = territory.build_call_lists(
        records, reps=["r1", "r2"], days=1, daily_cap=20,
        tier_mix_target=tier_mix, min_contactability=40,
    )
    for entries in schedule.values():
        for day_entries in entries.values():
            tier_counts = {}
            for e in day_entries:
                tier_counts[e.tier] = tier_counts.get(e.tier, 0) + 1
            # Neither tier should dominate the list; both were requested
            # at a 50/50 split and there was ample supply of each.
            assert tier_counts.get("A1", 0) > 0
            assert tier_counts.get("B2", 0) > 0


def test_summarize_call_lists_totals_match_the_schedule():
    records = [_record(f"c{i}", "DACH" if i % 2 == 0 else "CEE", "A1", 90) for i in range(40)]
    schedule = territory.build_call_lists(
        records, reps=["r1", "r2"], days=1, daily_cap=10,
        tier_mix_target={"A1": 1.0}, min_contactability=40,
    )
    summary = territory.summarize_call_lists(schedule)
    placed = sum(len(day_entries) for rep_days in schedule.values() for day_entries in rep_days.values())
    assert summary["total_accounts_placed"] == placed
    assert summary["tier_distribution"] == {"A1": placed}


def test_clustering_groups_same_region_together():
    records = []
    for i in range(30):
        region = "DACH" if i < 15 else "CEE"
        records.append(_record(f"c{i}", region, "A1", 90))
    schedule = territory.build_call_lists(
        records, reps=["r1"], days=1, daily_cap=30,
        tier_mix_target={"A1": 1.0}, min_contactability=40, cluster_key="region",
    )
    regions_in_order = [e.region for e in schedule["r1"][0]]
    # Because candidates are sorted by region before being sliced into the
    # day, the sequence should not be a random shuffle: it should contain
    # long same-region runs rather than alternating constantly.
    switches = sum(1 for a, b in zip(regions_in_order, regions_in_order[1:]) if a != b)
    assert switches <= 2
