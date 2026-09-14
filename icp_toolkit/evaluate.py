"""Coverage metrics and backtesting, including the survivorship-bias trap.

Two different questions get asked of a scoring model, and they need two
different kinds of measurement:

1. "How much of my universe can I actually act on?" -> coverage metrics.
   This is just counting: how many records have a phone, a verified
   domain, a plausible email, and how the universe splits across tiers.

2. "Does the model actually predict who buys?" -> backtesting against
   historical closed-won outcomes.

Backtesting is where most homegrown ICP models quietly lie to their
owners, via survivorship bias: historical call records only exist for
accounts that were, in fact, called, and who got called historically was
never a random sample. Reps preferentially called bigger, easier-to-reach
accounts. If you compute "win rate by tier" only from the called subset
and stop there, a tier that was rarely called will show a noisy win rate
built on a handful of data points, and a tier that was called a lot will
look artificially well-validated. Both are measurement artefacts of who
picked up the phone historically, not evidence about the tier itself.

This module does not pretend to solve that problem (there is no honest
way to know the outcome for an account nobody ever called). Instead it
measures and reports the CALL COVERAGE per tier alongside the win rate, so
a low-coverage tier's win-rate number comes with an explicit low-
confidence flag rather than being presented at face value.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from icp_toolkit.quality import QualityFlags
from icp_toolkit.scoring import ScoreBreakdown


def coverage_report(companies: list[dict], quality_flags_by_id: dict[str, QualityFlags], scores_by_id: dict[str, ScoreBreakdown]) -> dict:
    n = len(companies)
    has_phone = sum(1 for c in companies if quality_flags_by_id[c["company_id"]].has_phone)
    shared_phone = sum(1 for c in companies if quality_flags_by_id[c["company_id"]].is_shared_phone)
    domain_verified = sum(1 for c in companies if quality_flags_by_id[c["company_id"]].domain_verified)
    declared_verified = sum(1 for c in companies if c.get("declared_domain_verified"))
    email_ok = sum(1 for c in companies if quality_flags_by_id[c["company_id"]].email_ok)
    duplicates = sum(1 for c in companies if quality_flags_by_id[c["company_id"]].is_duplicate)

    tier_counts: dict[str, int] = defaultdict(int)
    for c in companies:
        tier_counts[scores_by_id[c["company_id"]].tier] += 1

    def pct(x: int) -> float:
        return round(100.0 * x / n, 1) if n else 0.0

    return {
        "universe_size": n,
        "pct_has_phone": pct(has_phone),
        "pct_shared_phone_of_universe": pct(shared_phone),
        "pct_domain_verified_recomputed": pct(domain_verified),
        "pct_domain_verified_declared": pct(declared_verified),
        "verification_correction_points": round(pct(domain_verified) - pct(declared_verified), 1),
        "pct_email_plausible": pct(email_ok),
        "pct_duplicate_rows": pct(duplicates),
        "tier_distribution": dict(sorted(tier_counts.items())),
    }


@dataclass
class TierBacktestRow:
    tier: str
    universe_size: int
    called: int
    call_coverage_pct: float
    wins: int
    win_rate_pct: float
    confidence: str


def backtest_report(
    companies: list[dict],
    scores_by_id: dict[str, ScoreBreakdown],
    call_history: list,
    min_coverage_for_confidence: float = 15.0,
) -> list[TierBacktestRow]:
    """call_history is a list of synth.CallRecord (company_id, was_called,
    closed_won). Returns one row per tier, ordered A1..C3 by the natural
    tier order, each carrying both the win rate AND the call coverage that
    win rate was computed from.
    """
    tier_of = {cid: sb.tier for cid, sb in scores_by_id.items()}
    universe_by_tier: dict[str, int] = defaultdict(int)
    for c in companies:
        universe_by_tier[tier_of[c["company_id"]]] += 1

    called_by_tier: dict[str, int] = defaultdict(int)
    wins_by_tier: dict[str, int] = defaultdict(int)
    for rec in call_history:
        tier = tier_of.get(rec.company_id)
        if tier is None or not rec.was_called:
            continue
        called_by_tier[tier] += 1
        if rec.closed_won:
            wins_by_tier[tier] += 1

    tier_order = [f"{f}{i}" for f in "ABC" for i in "123"]
    rows: list[TierBacktestRow] = []
    for tier in tier_order:
        uni = universe_by_tier.get(tier, 0)
        called = called_by_tier.get(tier, 0)
        wins = wins_by_tier.get(tier, 0)
        coverage_pct = round(100.0 * called / uni, 1) if uni else 0.0
        win_rate_pct = round(100.0 * wins / called, 1) if called else 0.0
        if called == 0:
            confidence = "no data"
        elif coverage_pct < min_coverage_for_confidence or called < 20:
            confidence = "low (sparse or biased sample, do not trust ranking)"
        else:
            confidence = "ok"
        rows.append(
            TierBacktestRow(
                tier=tier,
                universe_size=uni,
                called=called,
                call_coverage_pct=coverage_pct,
                wins=wins,
                win_rate_pct=win_rate_pct,
                confidence=confidence,
            )
        )
    return rows


def survivorship_bias_check(rows: list[TierBacktestRow]) -> list[str]:
    """Plain-language warnings for any tier whose backtest numbers should
    not be trusted at face value, driven purely by the coverage figures
    already computed in backtest_report. This is the antidote to reading
    a win-rate table as ground truth.
    """
    warnings: list[str] = []
    coverages = [r.call_coverage_pct for r in rows if r.called > 0]
    if not coverages:
        return ["No historical call data available; cannot backtest yet."]

    spread = max(coverages) - min(coverages)
    if spread > 25:
        warnings.append(
            f"Call coverage varies by {spread:.0f} points across tiers. Historical calling was not random, "
            "so comparing win rates across tiers directly overstates confidence in the ranking."
        )
    for r in rows:
        if r.confidence.startswith("low"):
            warnings.append(
                f"Tier {r.tier}: only {r.called} historical calls ({r.call_coverage_pct}% of that tier's "
                "universe). Treat its win rate as noise, not a validated result."
            )
    return warnings
