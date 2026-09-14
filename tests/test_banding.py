from icp_toolkit import banding


def test_band_revenue_boundaries_are_inclusive_on_the_lower_band(config):
    bands = config["banding"]["revenue_bands_eur"]
    assert banding.band_revenue(200_000, bands) == "micro"
    assert banding.band_revenue(200_001, bands) == "small"
    assert banding.band_revenue(0, bands) == "micro"


def test_band_revenue_open_ended_top_band(config):
    bands = config["banding"]["revenue_bands_eur"]
    assert banding.band_revenue(10_000_000_000, bands) == "enterprise"


def test_band_revenue_unknown_value(config):
    bands = config["banding"]["revenue_bands_eur"]
    assert banding.band_revenue(None, bands) == "unknown"


def test_band_headcount_boundaries(config):
    bands = config["banding"]["headcount_bands"]
    assert banding.band_headcount(9, bands) == "micro"
    assert banding.band_headcount(10, bands) == "small"
    assert banding.band_headcount(1000, bands) == "enterprise"


def test_band_industry_group_known_and_unknown(config):
    groups = config["banding"]["industry_groups"]
    assert banding.band_industry_group("software", groups) == "technology"
    assert banding.band_industry_group("financial_services", groups) == "services"
    assert banding.band_industry_group("some_sector_not_in_the_config", groups) == "other"


def test_band_company_returns_all_three_bands(config):
    company = {"revenue_eur": 2_000_000, "headcount": 80, "industry": "software"}
    bands = banding.band_company(company, config["banding"])
    assert bands == {
        "revenue_band": "mid",
        "headcount_band": "medium",
        "industry_group": "technology",
    }


def test_describe_bands_is_human_readable(config):
    lines = banding.describe_bands(config["banding"]["revenue_bands_eur"], unit=" EUR")
    assert any(line.startswith("micro") for line in lines)
    assert lines[-1].startswith("enterprise")
    assert all(" EUR" in line for line in lines)
