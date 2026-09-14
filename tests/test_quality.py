from icp_toolkit import quality


def test_normalize_name_folds_legal_suffix_and_punctuation():
    a = quality.normalize_name("Alder Systems Ltd")
    b = quality.normalize_name("ALDER SYSTEMS, Inc.")
    assert a == b == "aldersystems"


def test_normalize_name_handles_empty_input():
    assert quality.normalize_name("") == ""
    assert quality.normalize_name(None) == ""


def test_detect_shared_phones_respects_threshold():
    companies = [
        {"company_id": "1", "phone": "+1 555 0001"},
        {"company_id": "2", "phone": "+1 555 0001"},
        {"company_id": "3", "phone": "+1 555 0001"},
        {"company_id": "4", "phone": "+1 555 0002"},
        {"company_id": "5", "phone": None},
    ]
    shared = quality.detect_shared_phones(companies, threshold=3)
    assert "+1 555 0001" in shared
    assert sorted(shared["+1 555 0001"]) == ["1", "2", "3"]
    assert "+1 555 0002" not in shared


def test_verify_domain_name_present_true_and_false_cases():
    assert quality.verify_domain_name_present(
        "Alder Systems Ltd", "Welcome to Alder Systems, we build things."
    ) is True
    assert quality.verify_domain_name_present(
        "Alder Systems Ltd", "Generic homepage. Contact us for a quote."
    ) is False
    assert quality.verify_domain_name_present("Alder Systems Ltd", None) is False
    assert quality.verify_domain_name_present("Alder Systems Ltd", "") is False


def test_email_plausible_matching_domain_is_ok():
    ok, reason = quality.email_plausible("info@example.com", "example.com")
    assert ok is True
    assert reason == "ok"


def test_email_plausible_free_webmail_mismatched_domain():
    ok, reason = quality.email_plausible("someone@gmail.com", "example.com")
    assert ok is False
    assert "webmail" in reason


def test_email_plausible_domain_mismatch_non_webmail():
    ok, reason = quality.email_plausible("someone@another-company.com", "example.com")
    assert ok is False
    assert "mismatch" in reason


def test_email_plausible_malformed_address():
    ok, reason = quality.email_plausible("not-an-email", "example.com")
    assert ok is False
    assert "malformed" in reason


def test_email_plausible_missing_address():
    ok, reason = quality.email_plausible(None, "example.com")
    assert ok is False
    assert reason == "missing"


def test_find_duplicate_groups_groups_near_identical_names():
    companies = [
        {"company_id": "1", "name": "Alder Systems Ltd"},
        {"company_id": "2", "name": "Alder Systems, Inc."},
        {"company_id": "3", "name": "Birchwood Group LLC"},
    ]
    groups = quality.find_duplicate_groups(companies)
    assert len(groups) == 1
    (only_group,) = groups.values()
    assert set(only_group) == {"1", "2"}


def test_compute_quality_flags_integration(config):
    companies = [
        {
            "company_id": "1",
            "name": "Alder Systems Ltd",
            "phone": "+1 555 0001",
            "domain": "aldersystems.com",
            "homepage_text": "Alder Systems builds things.",
            "declared_domain_verified": True,
            "email": "info@aldersystems.com",
        },
        {
            "company_id": "2",
            "name": "Birchwood Group LLC",
            "phone": "+1 555 0001",
            "domain": None,
            "homepage_text": None,
            "declared_domain_verified": False,
            "email": "someone@gmail.com",
        },
    ]
    contactability_config = dict(config["contactability_model"])
    contactability_config["shared_phone_threshold"] = 2

    flags = quality.compute_quality_flags(companies, contactability_config)

    assert flags["1"].is_shared_phone is True
    assert flags["1"].domain_verified is True
    assert flags["2"].is_shared_phone is True
    assert flags["2"].domain_verified is False
