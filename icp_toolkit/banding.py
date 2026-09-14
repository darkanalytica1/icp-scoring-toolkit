"""Firmographic banding: revenue, headcount, and industry grouping.

The core teaching point of this module is not the arithmetic, it is that
band BOUNDARIES matter more than precise input values. Two companies with
revenue of 995,000 and 1,005,000 are, for scoring purposes, the same
company: they should land in the same band and score identically. A model
that instead multiplies a weight directly against raw revenue will treat
them as meaningfully different and will also be extremely sensitive to
currency conversion noise, one-off years, and reporting lag.

Banding also makes the model reviewable. A sales leader can read "mid =
1,000,000 to 10,000,000 EUR" and immediately agree or disagree. They
cannot usefully review a hidden coefficient on a continuous revenue
variable.
"""

from __future__ import annotations

from typing import Optional


def _band_lookup(value: float, bands: list[dict]) -> str:
    """bands is a list of {"label": str, "max": float|None}, in ascending
    order of "max". The first band whose max is >= value wins; a band with
    max=None is the open-ended top band.
    """
    for band in bands:
        if band["max"] is None or value <= band["max"]:
            return band["label"]
    # Should not happen if the config ends with an open-ended band, but
    # fail safe into the last defined label rather than raising.
    return bands[-1]["label"]


def band_revenue(revenue_eur: float, bands: list[dict]) -> str:
    if revenue_eur is None:
        return "unknown"
    return _band_lookup(max(0.0, float(revenue_eur)), bands)


def band_headcount(headcount: int, bands: list[dict]) -> str:
    if headcount is None:
        return "unknown"
    return _band_lookup(max(0, int(headcount)), bands)


def band_industry_group(industry: str, industry_groups: dict) -> str:
    if industry is None:
        return "other"
    return industry_groups.get(industry, "other")


def band_company(company_like: dict, banding_config: dict) -> dict:
    """Convenience wrapper: given a company (as a dict with at least
    revenue_eur, headcount, industry) and the "banding" section of the
    ICP config, return the three derived band labels.
    """
    return {
        "revenue_band": band_revenue(company_like.get("revenue_eur"), banding_config["revenue_bands_eur"]),
        "headcount_band": band_headcount(company_like.get("headcount"), banding_config["headcount_bands"]),
        "industry_group": band_industry_group(company_like.get("industry"), banding_config["industry_groups"]),
    }


def describe_bands(bands: list[dict], unit: str = "") -> list[str]:
    """Human-readable band boundaries, useful for printing in the demo and
    for a sales leader sanity-checking config/icp_example.json.
    """
    lines = []
    floor: Optional[float] = 0
    for band in bands:
        if band["max"] is None:
            lines.append(f"{band['label']}: > {floor:,.0f}{unit}")
        else:
            lines.append(f"{band['label']}: {floor:,.0f}{unit} to {band['max']:,.0f}{unit}")
            floor = band["max"]
    return lines
