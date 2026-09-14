"""Data-quality heuristics for contactability scoring.

Three ideas live here, and they are the part of this toolkit most worth
stealing for a real pipeline:

1. Shared-phone detection. A phone number that appears on many unrelated
   companies is not a company phone number, it is an accountant, a
   registered-office / company-formation agent, or a shared call centre.
   It will look perfectly valid to any format check. The only way to
   catch it is to count how many distinct companies use the same number
   across your whole universe, which means this check cannot be done
   row-by-row, it needs the full data set in front of it.

2. Domain verification as a quality GATE, not a trusted input. Whether a
   domain was "verified" by whatever produced your source data should
   never be taken at face value. Re-derive it yourself from the cheapest
   available evidence (does the homepage actually mention the company
   name) and use your own result. This module treats the incoming
   declared_domain_verified flag as untrusted and recomputes it.

3. Everything here produces a REASON, not just a boolean. "email
   implausible" is a much weaker training signal for a rep than "email
   domain does not match the declared company domain."
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Optional

LEGAL_SUFFIX_PATTERN = re.compile(
    r"\b(ltd|llc|inc|gmbh|bv|ag|sa|kft|oy|srl|s\.r\.l\.?|plc|co)\.?\b",
    re.IGNORECASE,
)
NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9]+")

DISPOSABLE_EMAIL_DOMAINS = {
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "trashmail.com",
}

FREE_WEBMAIL_DOMAINS = {
    "gmail.com", "outlook.com", "hotmail.com", "yahoo.com", "protonmail.com",
    "icloud.com", "aol.com",
}


def normalize_name(name: str) -> str:
    """Fold a company name down to a comparison key for deduplication.

    Lowercases, strips common legal suffixes (Ltd, LLC, GmbH, SRL, ...),
    and removes everything that is not a letter or digit. This is
    deliberately aggressive: "Alder Systems Ltd" and "ALDER SYSTEMS, Inc."
    should collapse to the same key even though they are, formally,
    different legal name strings, because in a call-list context they are
    almost always the same target account seen through two data sources.
    """
    if not name:
        return ""
    folded = name.lower()
    folded = LEGAL_SUFFIX_PATTERN.sub(" ", folded)
    folded = NON_ALNUM_PATTERN.sub("", folded)
    return folded


def find_duplicate_groups(companies: Iterable[dict]) -> dict[str, list[str]]:
    """Group company_ids by normalized name. Only groups with 2+ members
    are returned, since a group of 1 is not a duplicate.
    """
    groups: dict[str, list[str]] = {}
    for c in companies:
        key = normalize_name(c["name"])
        groups.setdefault(key, []).append(c["company_id"])
    return {k: v for k, v in groups.items() if len(v) > 1}


def detect_shared_phones(companies: Iterable[dict], threshold: int) -> dict[str, list[str]]:
    """Return {phone_number: [company_id, ...]} for every phone number
    that appears on `threshold` or more distinct companies.

    threshold should come from config (contactability_model.shared_phone_threshold).
    A low threshold catches more shared lines but also risks flagging a
    handful of companies that coincidentally share a franchise or holding
    group's switchboard; a sales leader should own that trade-off, which
    is why it lives in the config file rather than as a hardcoded constant.
    """
    phone_to_ids: dict[str, list[str]] = {}
    for c in companies:
        phone = c.get("phone")
        if not phone:
            continue
        phone_to_ids.setdefault(phone, []).append(c["company_id"])
    return {phone: ids for phone, ids in phone_to_ids.items() if len(ids) >= threshold}


def verify_domain_name_present(name: str, homepage_text: Optional[str]) -> bool:
    """Re-derive domain verification ourselves: does the homepage text
    actually contain a recognizable form of the company name?

    We compare on the same normalized key used for deduplication, so
    punctuation and legal-suffix differences do not cause false negatives,
    but a generic template page or a parked-domain page (which contain no
    trace of the company name at all) correctly fail this check even if
    an upstream enrichment pass had marked the domain "verified".
    """
    if not homepage_text:
        return False
    name_key = normalize_name(name)
    if not name_key:
        return False
    page_key = NON_ALNUM_PATTERN.sub("", homepage_text.lower())
    return name_key in page_key


def email_plausible(email: Optional[str], domain: Optional[str]) -> tuple[bool, str]:
    """Return (is_plausible, reason). reason is always populated so the
    caller can show a rep or a QA reviewer WHY a record was down-scored,
    not just that it was.
    """
    if not email:
        return False, "missing"
    if "@" not in email or email.count("@") != 1:
        return False, "malformed (no single @)"
    local, _, email_domain = email.partition("@")
    if not local or not email_domain or "." not in email_domain:
        return False, "malformed (bad local or domain part)"
    email_domain = email_domain.lower()
    if email_domain in DISPOSABLE_EMAIL_DOMAINS:
        return False, "disposable domain"
    if domain and email_domain != domain.lower():
        if email_domain in FREE_WEBMAIL_DOMAINS:
            return False, f"free webmail ({email_domain}), does not match company domain {domain}"
        return False, f"domain mismatch: email is @{email_domain}, company domain is {domain}"
    if not domain and email_domain in FREE_WEBMAIL_DOMAINS:
        # No declared company domain to compare against, so a free
        # webmail address is weak evidence but not automatically wrong.
        return True, "no company domain on file; free webmail is weak but not disqualifying"
    return True, "ok"


@dataclass
class QualityFlags:
    company_id: str
    has_phone: bool
    is_shared_phone: bool
    phone_reason: str
    domain_verified: bool
    domain_reason: str
    email_ok: bool
    email_reason: str
    is_duplicate: bool


def compute_quality_flags(companies: list[dict], contactability_config: dict) -> dict[str, QualityFlags]:
    """Compute the full set of quality flags for every company in one pass.

    This is a whole-universe operation (not a per-row function) because
    shared-phone detection and deduplication are inherently comparisons
    across the population, not properties of a single record.
    """
    threshold = contactability_config["shared_phone_threshold"]
    shared_phones = detect_shared_phones(companies, threshold)
    duplicate_groups = find_duplicate_groups(companies)
    duplicated_ids = {cid for ids in duplicate_groups.values() for cid in ids}

    flags: dict[str, QualityFlags] = {}
    for c in companies:
        cid = c["company_id"]
        phone = c.get("phone")
        has_phone = bool(phone)
        is_shared = bool(phone) and phone in shared_phones
        if not has_phone:
            phone_reason = "missing"
        elif is_shared:
            phone_reason = f"shared across {len(shared_phones[phone])} companies (likely accountant/agent/call centre)"
        else:
            phone_reason = "ok"

        domain_verified = verify_domain_name_present(c["name"], c.get("homepage_text"))
        declared = c.get("declared_domain_verified")
        if not c.get("domain"):
            domain_reason = "no domain on file"
        elif domain_verified and not declared:
            domain_reason = "recovered: name present on page, source data under-verified this one"
        elif not domain_verified and declared:
            domain_reason = "corrected: source data marked verified, but name is not actually on the page"
        elif domain_verified:
            domain_reason = "confirmed: name present on page"
        else:
            domain_reason = "no name found on page (generic or parked page)"

        email_ok, email_reason = email_plausible(c.get("email"), c.get("domain"))

        flags[cid] = QualityFlags(
            company_id=cid,
            has_phone=has_phone,
            is_shared_phone=is_shared,
            phone_reason=phone_reason,
            domain_verified=domain_verified,
            domain_reason=domain_reason,
            email_ok=email_ok,
            email_reason=email_reason,
            is_duplicate=cid in duplicated_ids,
        )
    return flags
