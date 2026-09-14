"""Turning a scored universe into workable daily call lists.

A scoring model that stops at "here are 5,000 rows with a tier column" has
not actually helped a sales team. The last mile is turning that ranked
universe into daily lists that a rep can pick up and work without extra
thinking: a sane number of accounts, a deliberate mix of tiers (not only
the best accounts, which burns them out fast and ignores the nurture
tiers), and a geographic cluster per day so the rep is not mentally
context-switching between a DACH manufacturer and an Iberian retailer
every other call.

Three rules encoded here:

1. Never send only A1s. A daily list that is 100% top-tier accounts looks
   great on paper and burns through your best accounts in a week, with no
   plan for what happens after they say no. tier_mix_target in the config
   is a deliberate blend across tiers, including a small dose of C1
   ("poor fit, active signal") because those need a quick verify call,
   not a full sales cycle.
2. Respect the daily cap. A list a rep cannot realistically work in a day
   is not a call list, it is a backlog with extra steps.
3. Cluster by region where possible. Working one region's worth of
   accounts in a sitting keeps context (language, business hours, local
   holidays, current events worth referencing) loaded once instead of
   per call.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class CallListEntry:
    company_id: str
    name: str
    region: str
    tier: str
    contactability_score: float


def _eligible_records(scored_records: list[dict], min_contactability: float, tier_mix_target: dict) -> list[dict]:
    """Apply the quality gate (contactability floor) and drop any tier
    that has no target share at all, which is how C2/C3 (deprioritize /
    suppress) get excluded from active call lists without a separate
    special case: they simply are not present in tier_mix_target.
    """
    allowed_tiers = set(tier_mix_target.keys())
    return [
        r for r in scored_records
        if r["contactability_score"] >= min_contactability and r["tier"] in allowed_tiers
    ]


def build_call_lists(
    scored_records: list[dict],
    reps: list[str],
    days: int,
    daily_cap: int,
    tier_mix_target: dict,
    min_contactability: float,
    cluster_key: str = "region",
) -> dict[str, dict[int, list[CallListEntry]]]:
    """Build `days` days of call lists for each rep in `reps`.

    scored_records: one dict per company with at least company_id, name,
    tier, contactability_score, and the field named by cluster_key
    (region by default).

    Returns {rep: {day_index (0-based): [CallListEntry, ...]}}.

    The algorithm is deliberately simple and auditable rather than an
    optimizer: for every tier, sort candidates by cluster_key so that
    consecutive picks tend to share a region, then round-robin slices of
    that sorted-by-tier pool across every (rep, day) slot in proportion to
    tier_mix_target. This means a rep's day is not guaranteed to be a
    single region, but it will tend to run in short regional streaks
    rather than being shuffled uniformly at random, which is what a naive
    "sort by score only" approach would produce.
    """
    eligible = _eligible_records(scored_records, min_contactability, tier_mix_target)

    # One queue per tier, sorted by region so same-region accounts sit
    # next to each other (the "clustering" behaviour).
    pools: dict[str, list[dict]] = defaultdict(list)
    for r in eligible:
        pools[r["tier"]].append(r)
    for tier in pools:
        pools[tier].sort(key=lambda r: (r[cluster_key], r["company_id"]))

    per_tier_daily_count = {
        tier: max(0, round(daily_cap * share)) for tier, share in tier_mix_target.items()
    }
    # Rounding can leave the day short of daily_cap; top up from whichever
    # tier still has the most supply left, so the cap is honored as
    # closely as the data allows.
    def top_up(counts: dict[str, int], remaining_cap: int) -> dict[str, int]:
        counts = dict(counts)
        tiers_by_supply = sorted(pools.keys(), key=lambda t: -len(pools[t]))
        i = 0
        while remaining_cap > 0 and tiers_by_supply:
            t = tiers_by_supply[i % len(tiers_by_supply)]
            if pools[t]:
                counts[t] = counts.get(t, 0) + 1
                remaining_cap -= 1
            i += 1
            if i > 10_000:
                break
        return counts

    schedule: dict[str, dict[int, list[CallListEntry]]] = {rep: {} for rep in reps}

    for day in range(days):
        for rep in reps:
            day_counts = dict(per_tier_daily_count)
            planned = sum(min(day_counts.get(t, 0), len(pools[t])) for t in day_counts)
            if planned < daily_cap:
                day_counts = top_up(day_counts, daily_cap - planned)

            day_entries: list[CallListEntry] = []
            for tier, n in day_counts.items():
                take = pools[tier][:n]
                del pools[tier][:n]
                for r in take:
                    day_entries.append(
                        CallListEntry(
                            company_id=r["company_id"],
                            name=r["name"],
                            region=r[cluster_key],
                            tier=r["tier"],
                            contactability_score=r["contactability_score"],
                        )
                    )
            schedule[rep][day] = day_entries

    return schedule


def summarize_call_lists(schedule: dict[str, dict[int, list[CallListEntry]]]) -> dict:
    """Aggregate stats useful for sanity-checking the output: total
    accounts placed, tier distribution actually achieved, and, for each
    (rep, day), how concentrated that day was in its single most common
    region (1.0 = perfectly clustered, low values = shuffled).
    """
    total = 0
    tier_counts: dict[str, int] = defaultdict(int)
    cluster_ratios: list[float] = []

    for rep, days in schedule.items():
        for day, entries in days.items():
            if not entries:
                continue
            total += len(entries)
            region_counts: dict[str, int] = defaultdict(int)
            for e in entries:
                tier_counts[e.tier] += 1
                region_counts[e.region] += 1
            top_region_count = max(region_counts.values())
            cluster_ratios.append(top_region_count / len(entries))

    avg_cluster_ratio = sum(cluster_ratios) / len(cluster_ratios) if cluster_ratios else 0.0
    return {
        "total_accounts_placed": total,
        "tier_distribution": dict(tier_counts),
        "avg_region_cluster_ratio": round(avg_cluster_ratio, 2),
    }
