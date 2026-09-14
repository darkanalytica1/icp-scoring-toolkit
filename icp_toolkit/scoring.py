"""Fit, intent, contactability, and tiering.

The central design decision in this module, and the one most ICP scoring
spreadsheets get wrong, is that fit and intent are computed and reported
SEPARATELY and are never averaged into one number.

Fit answers "is this the kind of company we sell to" (size, industry,
geography). It changes slowly, it can be cached for weeks, and a company
with excellent fit is worth nurturing even during a quiet quarter.

Intent answers "is something happening right now that makes this a good
moment to reach out" (hiring, funding, expansion, new tech). It is
time-decayed, it must be recomputed often, and a company with strong
intent but poor fit is usually noise, not a hot lead.

Blending them into a single score throws away exactly the information a
rep needs to decide what to do next: call now, nurture, or ignore. Keeping
them separate and placing every account on a fit x intent quadrant
produces nine tiers (A1..C3) that map directly onto a sales action, which
is the point of scoring accounts in the first place.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from icp_toolkit import banding
from icp_toolkit.quality import QualityFlags


def _decay(full_points: float, days_ago: Optional[int], half_life_days: float, floor_points: float) -> float:
    """Exponential half-life decay. A signal that is `half_life_days` old
    is worth half its fresh value; one that is very old settles at
    `floor_points` rather than zero, because "this happened at some point"
    is still weakly informative.
    """
    if days_ago is None:
        return 0.0
    value = full_points * (0.5 ** (days_ago / half_life_days))
    return max(value, floor_points)


@dataclass
class ScoreBreakdown:
    company_id: str
    fit_score: float
    fit_components: dict
    intent_score: float
    intent_components: dict
    contactability_score: float
    contactability_components: dict
    fit_tier: str
    intent_tier: str
    tier: str
    tier_note: str


def compute_fit_score(company: dict, config: dict) -> tuple[float, dict]:
    banding_cfg = config["banding"]
    fit_cfg = config["fit_model"]

    bands = banding.band_company(company, banding_cfg)
    revenue_band, headcount_band, industry_group = (
        bands["revenue_band"], bands["headcount_band"], bands["industry_group"],
    )
    region = company.get("region")

    components = {
        "revenue_band": fit_cfg["revenue_band_scores"].get(revenue_band, 0),
        "headcount_band": fit_cfg["headcount_band_scores"].get(headcount_band, 0),
        "industry_group": fit_cfg["industry_group_scores"].get(industry_group, 0),
        "region": fit_cfg["region_scores"].get(region, 0),
    }
    weights = fit_cfg["weights"]
    score = sum(components[k] * weights[k] for k in weights)
    components["_bands"] = bands
    return score, components


def compute_intent_score(company: dict, config: dict) -> tuple[float, dict]:
    intent_cfg = config["intent_model"]
    decay_cfg = intent_cfg["recency_decay"]
    half_life = decay_cfg["half_life_days"]
    floor = decay_cfg["floor_points"]

    hiring_points = min(
        company.get("hiring_open_roles", 0) * intent_cfg["hiring_points_per_open_role"],
        intent_cfg["hiring_points_cap"],
    )

    funding_days = company.get("funding_event_days_ago")
    funding_points = _decay(intent_cfg["funding_event_max_points"], funding_days, half_life, floor) if funding_days is not None else 0.0

    expansion_points = 0.0
    if company.get("expansion_signal"):
        expansion_points = _decay(
            intent_cfg["expansion_signal_points"], company.get("expansion_signal_days_ago"), half_life, floor
        )

    tech_points = 0.0
    if company.get("tech_adoption_signal"):
        tech_points = _decay(
            intent_cfg["tech_adoption_signal_points"], company.get("tech_adoption_signal_days_ago"), half_life, floor
        )

    components = {
        "hiring": hiring_points,
        "funding": funding_points,
        "expansion": expansion_points,
        "tech_adoption": tech_points,
    }
    weights = intent_cfg["weights"]
    score = sum(components[k] * weights[k] for k in weights)
    return score, components


def compute_contactability_score(quality_flags: QualityFlags, config: dict) -> tuple[float, dict]:
    weights = config["contactability_model"]["weights"]

    phone_present = 100.0 if quality_flags.has_phone else 0.0
    phone_not_shared = 100.0 if (quality_flags.has_phone and not quality_flags.is_shared_phone) else 0.0
    domain_verified = 100.0 if quality_flags.domain_verified else 0.0
    email_plausible = 100.0 if quality_flags.email_ok else 0.0

    components = {
        "phone_present": phone_present,
        "phone_not_shared": phone_not_shared,
        "domain_verified": domain_verified,
        "email_plausible": email_plausible,
    }
    score = sum(components[k] * weights[k] for k in weights)
    return score, components


def fit_tier_for(score: float, config: dict) -> str:
    t = config["tiering"]["fit_thresholds"]
    if score >= t["A"]:
        return "A"
    if score >= t["B"]:
        return "B"
    return "C"


def intent_tier_for(score: float, config: dict) -> str:
    t = config["tiering"]["intent_thresholds"]
    if score >= t["1"]:
        return "1"
    if score >= t["2"]:
        return "2"
    return "3"


def score_company(company: dict, quality_flags: QualityFlags, config: dict) -> ScoreBreakdown:
    fit_score, fit_components = compute_fit_score(company, config)
    intent_score, intent_components = compute_intent_score(company, config)
    contactability_score, contactability_components = compute_contactability_score(quality_flags, config)

    ft = fit_tier_for(fit_score, config)
    it = intent_tier_for(intent_score, config)
    tier = f"{ft}{it}"
    tier_note = config["tiering"]["tier_notes"].get(tier, "")

    return ScoreBreakdown(
        company_id=company["company_id"],
        fit_score=round(fit_score, 1),
        fit_components=fit_components,
        intent_score=round(intent_score, 1),
        intent_components=intent_components,
        contactability_score=round(contactability_score, 1),
        contactability_components=contactability_components,
        fit_tier=ft,
        intent_tier=it,
        tier=tier,
        tier_note=tier_note,
    )


def score_universe(companies: list[dict], quality_flags_by_id: dict[str, QualityFlags], config: dict) -> list[ScoreBreakdown]:
    return [score_company(c, quality_flags_by_id[c["company_id"]], config) for c in companies]
