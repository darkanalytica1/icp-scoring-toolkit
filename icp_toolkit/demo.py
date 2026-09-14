"""End-to-end runnable demo. No network access, no third-party
dependencies. Run with:

    python -m icp_toolkit.demo

This generates a synthetic 5,000-company universe, bands it, computes
data-quality flags, scores fit / intent / contactability, tiers every
account into the fit x intent quadrant, builds a sample of daily call
lists, and prints coverage and backtest reports. Every table below is
generated from the synthetic data in this repository, not from any real
company or client.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict

from icp_toolkit import banding, evaluate, quality, scoring, synth, territory

CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "icp_example.json")


def load_config(path: str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _print_header(title: str) -> None:
    print()
    print("=" * 78)
    print(title)
    print("=" * 78)


def _print_table(rows: list[dict], columns: list[str], col_widths: dict[str, int] | None = None) -> None:
    col_widths = col_widths or {}
    widths = {c: col_widths.get(c, max(len(c), *(len(str(r.get(c, ""))) for r in rows)) if rows else len(c)) for c in columns}
    header = "  ".join(c.ljust(widths[c]) for c in columns)
    print(header)
    print("-" * len(header))
    for r in rows:
        print("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in columns))


def main() -> None:
    config = load_config()

    _print_header("1. GENERATING THE SYNTHETIC UNIVERSE")
    n = 5000
    companies_objs = synth.generate_universe(n=n, seed=synth.SEED)
    companies = [c.as_dict() for c in companies_objs]
    print(f"Generated {len(companies)} synthetic companies (seed={synth.SEED}, fully deterministic).")
    print("No real company, contact, or client data is used anywhere in this repository.")

    _print_header("2. BANDING (why boundaries matter more than precise values)")
    print("Revenue bands (EUR):")
    for line in banding.describe_bands(config["banding"]["revenue_bands_eur"], unit=" EUR"):
        print(f"  - {line}")
    print("Headcount bands:")
    for line in banding.describe_bands(config["banding"]["headcount_bands"]):
        print(f"  - {line}")

    band_counts: dict[str, int] = defaultdict(int)
    for c in companies:
        b = banding.band_company(c, config["banding"])
        band_counts[b["revenue_band"]] += 1
    print("\nRevenue band distribution across the synthetic universe:")
    _print_table(
        [{"band": k, "count": v, "pct": f"{100 * v / n:.1f}%"} for k, v in sorted(band_counts.items())],
        ["band", "count", "pct"],
    )

    _print_header("3. DATA-QUALITY HEURISTICS (contactability inputs)")
    quality_flags = quality.compute_quality_flags(companies, config["contactability_model"])
    shared_pool = quality.detect_shared_phones(companies, config["contactability_model"]["shared_phone_threshold"])
    dup_groups = quality.find_duplicate_groups(companies)

    print(f"Shared phone numbers detected (used by >= {config['contactability_model']['shared_phone_threshold']} distinct companies): {len(shared_pool)}")
    total_flagged = sum(len(ids) for ids in shared_pool.values())
    print(f"Companies whose phone was flagged as shared (accountant / registered-office agent / call centre pattern): {total_flagged}")
    if shared_pool:
        example_phone, example_ids = max(shared_pool.items(), key=lambda kv: len(kv[1]))
        print(f"  Worst offender: {example_phone} appears on {len(example_ids)} companies, e.g. {example_ids[:5]}")

    declared_verified = sum(1 for c in companies if c.get("declared_domain_verified"))
    recomputed_verified = sum(1 for c in companies if quality_flags[c["company_id"]].domain_verified)
    corrected_to_false = sum(
        1 for c in companies
        if c.get("declared_domain_verified") and not quality_flags[c["company_id"]].domain_verified
    )
    recovered_to_true = sum(
        1 for c in companies
        if not c.get("declared_domain_verified") and quality_flags[c["company_id"]].domain_verified
    )
    print(f"\nDomain verification: never trust the declared flag, recheck it yourself.")
    print(f"  Declared 'verified' by source data: {declared_verified}")
    print(f"  Verified after rechecking homepage text ourselves: {recomputed_verified}")
    print(f"  Corrected FALSE (source said verified, name not actually on page): {corrected_to_false}")
    print(f"  Recovered TRUE (source under-verified, name was actually there): {recovered_to_true}")

    print(f"\nDuplicate company groups found by normalized-name matching: {len(dup_groups)}")

    _print_header("4. FIT x INTENT SCORING AND QUADRANT TIERING")
    scores = scoring.score_universe(companies, quality_flags, config)
    scores_by_id = {s.company_id: s for s in scores}
    companies_by_id = {c["company_id"]: c for c in companies}

    tier_counts: dict[str, int] = defaultdict(int)
    for s in scores:
        tier_counts[s.tier] += 1

    print("Quadrant tier distribution (fit tier A/B/C x intent tier 1/2/3):")
    tier_order = [f"{f}{i}" for f in "ABC" for i in "123"]
    rows = [
        {"tier": t, "count": tier_counts.get(t, 0), "meaning": config["tiering"]["tier_notes"].get(t, "")}
        for t in tier_order
    ]
    _print_table(rows, ["tier", "count", "meaning"])

    print("\nSample of top A1 accounts (best fit, active buying signal):")
    a1 = sorted((s for s in scores if s.tier == "A1"), key=lambda s: -s.intent_score)[:8]
    a1_rows = []
    for s in a1:
        c = companies_by_id[s.company_id]
        a1_rows.append({
            "company_id": s.company_id,
            "region": c["region"],
            "fit": s.fit_score,
            "intent": s.intent_score,
            "contactability": s.contactability_score,
        })
    _print_table(a1_rows, ["company_id", "region", "fit", "intent", "contactability"])

    _print_header("5. COVERAGE REPORT")
    coverage = evaluate.coverage_report(companies, quality_flags, scores_by_id)
    for k, v in coverage.items():
        if k == "tier_distribution":
            continue
        print(f"  {k}: {v}")

    _print_header("6. TERRITORY: SAMPLE DAILY CALL LISTS")
    scored_records = []
    for c in companies:
        s = scores_by_id[c["company_id"]]
        scored_records.append({
            "company_id": c["company_id"],
            "name": c["name"],
            "region": c["region"],
            "tier": s.tier,
            "contactability_score": s.contactability_score,
        })

    reps = ["rep_alpha", "rep_bravo", "rep_charlie"]
    days = 3
    territory_cfg = config["territory"]
    schedule = territory.build_call_lists(
        scored_records,
        reps=reps,
        days=days,
        daily_cap=territory_cfg["daily_cap_per_rep"],
        tier_mix_target=territory_cfg["tier_mix_target"],
        min_contactability=config["quality_gates"]["min_contactability_to_call"],
        cluster_key=territory_cfg["cluster_by"],
    )
    summary = territory.summarize_call_lists(schedule)
    print(f"Reps: {reps}, days: {days}, daily cap: {territory_cfg['daily_cap_per_rep']}")
    print(f"Total accounts placed across all lists: {summary['total_accounts_placed']}")
    print(f"Average same-region concentration per day (1.0 = perfectly clustered): {summary['avg_region_cluster_ratio']}")
    print("Tier mix actually achieved across all lists:")
    _print_table(
        [{"tier": t, "count": c} for t, c in sorted(summary["tier_distribution"].items())],
        ["tier", "count"],
    )

    print("\nExample: rep_alpha, day 1 (first 10 rows):")
    example_day = schedule["rep_alpha"][0][:10]
    _print_table(
        [{"company_id": e.company_id, "region": e.region, "tier": e.tier, "contactability": e.contactability_score} for e in example_day],
        ["company_id", "region", "tier", "contactability"],
    )

    _print_header("7. BACKTESTING AGAINST HISTORICAL OUTCOMES (and the survivorship-bias trap)")
    call_history = synth.generate_call_history(companies_objs, seed=synth.SEED)
    backtest_rows = evaluate.backtest_report(companies, scores_by_id, call_history)
    _print_table(
        [
            {
                "tier": r.tier,
                "universe": r.universe_size,
                "called": r.called,
                "coverage_%": r.call_coverage_pct,
                "wins": r.wins,
                "win_rate_%": r.win_rate_pct,
                "confidence": r.confidence,
            }
            for r in backtest_rows
        ],
        ["tier", "universe", "called", "coverage_%", "wins", "win_rate_%", "confidence"],
    )

    print("\nSurvivorship-bias warnings:")
    for w in evaluate.survivorship_bias_check(backtest_rows):
        print(f"  - {w}")

    _print_header("DONE")
    print("This entire run used only synthetic, seeded data generated inside this repository.")


if __name__ == "__main__":
    main()
