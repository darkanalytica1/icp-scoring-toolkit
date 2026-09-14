"""Deterministic synthetic company-universe generator.

Nothing in this module reads from the network or from any external file.
Every company, phone number, email address, and domain here is fabricated
by a seeded random-number generator. Names are built from generic word
lists (no real company, brand, or person is referenced). Any resemblance
to a real organization is coincidental and unintended.

The generator deliberately injects the kind of messiness a real B2B data
set actually has, because a scoring model that only ever sees clean rows
teaches the wrong lesson:

- missing phone numbers
- a small pool of PHONE NUMBERS SHARED across many companies (this is the
  single most common false signal in call-list data: the number usually
  belongs to an accountant, a registered-office / company-formation agent,
  or a shared call centre, not to the company itself)
- domains that were marked "verified" by a lazy enrichment pass but whose
  homepage text does not actually contain the company name, and the
  opposite case: unmarked domains whose homepage text clearly does
  contain the name
- emails whose domain does not match the company's declared domain
- a handful of revenue/headcount outliers and data-entry-shaped nonsense
  (huge revenue with a three-person headcount, and so on)
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional

SEED = 42
DEFAULT_N = 5000

# ---------------------------------------------------------------------------
# Vocabulary. Generic, invented, brand-free.
# ---------------------------------------------------------------------------

NAME_STEMS = [
    "Alder", "Birchwood", "Cedarline", "Northgate", "Silverbrook", "Ironvale",
    "Meridian", "Harborview", "Riverstone", "Oakfield", "Stonebridge",
    "Brightwell", "Fernhollow", "Westmark", "Clearwater", "Greystone",
    "Amberlane", "Sparrowhill", "Foxglove", "Larkspur", "Thistledown",
    "Copperfield", "Millrace", "Hazelmoor", "Falconridge", "Windermere",
    "Pinehaven", "Cobalt", "Marlowe", "Ashgrove", "Kestrel", "Redwood",
    "Bramblewick", "Draycott", "Elmsworth", "Granby", "Hollowell",
    "Ivywood", "Juniper", "Keswick", "Lockridge", "Moorfield", "Norwich",
    "Overton", "Prescott", "Quarrymont", "Rutherford", "Sedgewick",
    "Talbridge", "Underwood",
]

NAME_SUFFIXES = [
    "Systems", "Dynamics", "Group", "Partners", "Solutions", "Technologies",
    "Industries", "Works", "Holdings", "Logistics", "Studio", "Labs",
    "Consulting", "Networks", "Manufacturing", "Digital", "Ventures",
    "Analytics", "Robotics", "Foods", "Materials", "Freight", "Capital",
]

LEGAL_SUFFIXES = ["Ltd", "LLC", "Inc", "GmbH", "BV", "AG", "SA", "Kft", "Oy", "SRL"]

NAME_MODIFIERS = [
    "International", "Global", "Europe", "Advanced", "Precision", "National",
    "United", "Allied", "Prime", "Summit", "Vertex", "Nova", "Atlas", "Orbit",
    "Delta", "Sigma", "Apex", "Crown", "Vanguard", "Pioneer", "Frontier",
    "Horizon", "Zenith", "Nexus", "Cascade",
]

INDUSTRIES = [
    "software", "it_services", "telecom",
    "manufacturing", "industrial_equipment", "construction", "logistics",
    "wholesale_distribution",
    "retail", "hospitality", "consumer_goods",
    "professional_services", "financial_services", "healthcare", "education",
    "public_sector", "agriculture",
]

# Rough relative weight so the universe is not uniform across industries.
INDUSTRY_WEIGHTS = [
    10, 6, 3,
    9, 6, 8, 7,
    6,
    9, 5, 5,
    9, 5, 6, 4,
    3, 4,
]

REGIONS = ["DACH", "Benelux", "Nordics", "UK_I", "CEE", "Iberia", "Southern_EU", "Overseas"]
REGION_WEIGHTS = [16, 10, 8, 14, 18, 10, 14, 10]

FIRST_NAMES = [
    "Anna", "Marco", "Elena", "Tomas", "Sofia", "Lukas", "Nora", "Paulo",
    "Ingrid", "Dario", "Petra", "Milo", "Ines", "Viktor", "Clara", "Adrian",
]
LAST_NAMES = [
    "Berg", "Rossi", "Novak", "Keller", "Larsen", "Dubois", "Weiss", "Costa",
    "Horvat", "Meier", "Nilsson", "Fischer", "Bianchi", "Kovacs", "Lund",
]

TLDS = ["com", "eu", "io", "co"]

PAGE_TEMPLATE_WITH_NAME = (
    "{name} is a {industry_label} company operating in the {region_label} "
    "market. Learn more about our products and get in touch with the "
    "{name} team."
)
PAGE_TEMPLATE_GENERIC = (
    "Welcome. We help clients grow. Contact us to learn about our services "
    "and request a quote. Site under construction, more content coming soon."
)
PAGE_TEMPLATE_PARKED = (
    "This domain is available. Contact the registrar for pricing and "
    "availability of this premium domain name."
)


@dataclass
class Company:
    company_id: str
    name: str
    industry: str
    region: str
    revenue_eur: float
    headcount: int
    founded_year: int

    domain: Optional[str]
    homepage_text: Optional[str]
    declared_domain_verified: bool

    phone: Optional[str]
    email: Optional[str]

    hiring_open_roles: int
    funding_event_days_ago: Optional[int]
    expansion_signal: bool
    expansion_signal_days_ago: Optional[int]
    tech_adoption_signal: bool
    tech_adoption_signal_days_ago: Optional[int]

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _weighted_choice(rng: random.Random, options: list, weights: list):
    return rng.choices(options, weights=weights, k=1)[0]


def _slugify(name: str) -> str:
    return (
        name.lower()
        .replace(" ", "")
        .replace(".", "")
        .replace(",", "")
        .replace("&", "and")
    )


def _strip_legal_suffix(name: str) -> str:
    for legal in LEGAL_SUFFIXES:
        if name.endswith(f" {legal}"):
            return name[: -(len(legal) + 1)]
    return name


def _make_name(rng: random.Random) -> str:
    stem = rng.choice(NAME_STEMS)
    suffix = rng.choice(NAME_SUFFIXES)
    legal = rng.choice(LEGAL_SUFFIXES)

    # Small chance of a double-barrel name, which stresses normalization
    # (quality.dedupe) a bit harder.
    if rng.random() < 0.12:
        stem2 = rng.choice([s for s in NAME_STEMS if s != stem])
        base = f"{stem}-{stem2} {suffix}"
    # Most names carry a modifier word (International, Europe, Nova, ...),
    # which is realistic (most real company names are not just two generic
    # nouns) and keeps the name space large enough that the ~12% of names
    # left without a modifier are the ones that occasionally collide on
    # their normalized form, giving quality.find_duplicate_groups()
    # something real to find without making almost the whole universe
    # look duplicated.
    elif rng.random() < 0.88:
        modifier = rng.choice(NAME_MODIFIERS)
        base = f"{stem} {modifier} {suffix}"
    else:
        base = f"{stem} {suffix}"

    return f"{base} {legal}"


def _make_phone(rng: random.Random, region: str) -> str:
    country_code = {
        "DACH": "49", "Benelux": "31", "Nordics": "46", "UK_I": "44",
        "CEE": "40", "Iberia": "34", "Southern_EU": "39", "Overseas": "1",
    }.get(region, "44")
    return f"+{country_code} {rng.randint(100, 999)} {rng.randint(1000000, 9999999)}"


def _build_shared_phone_pool(rng: random.Random, region_list: list[str]) -> list[str]:
    """A handful of numbers that will be reused across many companies.

    In real data these are almost always an accountant's office line, a
    registered-office / company-formation agent, or an outsourced call
    centre. They look like valid phone numbers and will pass any basic
    format check, which is exactly why they are dangerous: nothing about
    the number itself flags it, only the fact that many unrelated
    companies share it.
    """
    return [_make_phone(rng, rng.choice(region_list)) for _ in range(6)]


def _make_email(rng: random.Random, name: str, domain: Optional[str], mismatched: bool) -> Optional[str]:
    if domain is None:
        return None
    local_options = ["info", "office", "contact", "sales", "hello"]
    if rng.random() < 0.45:
        first = rng.choice(FIRST_NAMES).lower()
        last = rng.choice(LAST_NAMES).lower()
        local = f"{first}.{last}"
    else:
        local = rng.choice(local_options)
    use_domain = domain
    if mismatched:
        # Email domain does not match the company's own declared domain.
        # This happens constantly in the wild: a generic webmail address
        # copied from a directory listing, a freelancer's personal domain
        # used on an old contact form, or simply bad enrichment.
        use_domain = rng.choice(["gmail.com", "outlook.com", "yahoo.com", "protonmail.com"])
    return f"{local}@{use_domain}"


def generate_universe(n: int = DEFAULT_N, seed: int = SEED) -> list[Company]:
    """Generate a deterministic synthetic company universe of size n.

    Calling this twice with the same (n, seed) always returns identical
    data. That determinism is intentional: scoring is only trustworthy to
    review if the underlying data does not silently shift between runs.
    """
    rng = random.Random(seed)
    shared_phone_pool = _build_shared_phone_pool(rng, REGIONS)

    companies: list[Company] = []
    used_names: set[str] = set()

    for i in range(n):
        company_id = f"SYN-{i + 1:05d}"

        name = _make_name(rng)
        while name in used_names:
            name = _make_name(rng)
        used_names.add(name)

        industry = _weighted_choice(rng, INDUSTRIES, INDUSTRY_WEIGHTS)
        region = _weighted_choice(rng, REGIONS, REGION_WEIGHTS)

        # Headcount first, revenue correlated to it with noise, so the
        # bulk of the universe is internally consistent...
        headcount = max(1, int(rng.lognormvariate(3.2, 1.3)))
        revenue_per_head = rng.uniform(60_000, 220_000)
        revenue_eur = round(headcount * revenue_per_head * rng.uniform(0.6, 1.4), -2)

        # ...but about 2% of rows get a deliberately nonsensical pairing,
        # the kind that shows up from fat-finger entry or a bad OCR pass
        # on a paper filing, and that a scoring model must not blow up on.
        if rng.random() < 0.02:
            if rng.random() < 0.5:
                revenue_eur = round(rng.uniform(20_000_000, 90_000_000), -2)
                headcount = rng.randint(1, 5)
            else:
                revenue_eur = round(rng.uniform(10_000, 60_000), -2)
                headcount = rng.randint(400, 1500)

        founded_year = rng.randint(1975, 2025)

        has_domain = rng.random() > 0.08
        domain = None
        homepage_text = None
        declared_domain_verified = False
        if has_domain:
            domain = f"{_slugify(_strip_legal_suffix(name))[:24]}.{rng.choice(TLDS)}"
            industry_label = industry.replace("_", " ")
            region_label = region.replace("_", " ")
            roll = rng.random()
            if roll < 0.70:
                # Genuinely good homepage: name present, correctly marked verified.
                homepage_text = PAGE_TEMPLATE_WITH_NAME.format(
                    name=name, industry_label=industry_label, region_label=region_label
                )
                declared_domain_verified = True
            elif roll < 0.85:
                # Generic/thin page, but an enrichment pass rubber-stamped it
                # as verified anyway. This is the case quality.py must catch:
                # never trust a declared "verified" flag without rechecking it.
                homepage_text = PAGE_TEMPLATE_GENERIC
                declared_domain_verified = True
            elif roll < 0.93:
                # Genuinely good page that a conservative enrichment pass
                # under-verified (marked False even though the name is
                # right there). Re-checking should recover this as a win.
                homepage_text = PAGE_TEMPLATE_WITH_NAME.format(
                    name=name, industry_label=industry_label, region_label=region_label
                )
                declared_domain_verified = False
            else:
                # Parked / expired-looking domain, correctly unverified.
                homepage_text = PAGE_TEMPLATE_PARKED
                declared_domain_verified = False

        has_phone = rng.random() > 0.12
        phone = None
        if has_phone:
            if rng.random() < 0.09:
                phone = rng.choice(shared_phone_pool)
            else:
                phone = _make_phone(rng, region)

        email_mismatched = rng.random() < 0.10
        email = _make_email(rng, name, domain, mismatched=email_mismatched)
        if email is not None and rng.random() < 0.02:
            # Malformed address: missing "@", the kind a form field with no
            # validation happily accepts.
            email = email.replace("@", "_at_")

        hiring_open_roles = 0
        if rng.random() < 0.30:
            hiring_open_roles = rng.randint(1, 9)

        funding_event_days_ago = None
        if rng.random() < 0.12:
            funding_event_days_ago = rng.randint(1, 540)

        expansion_signal = rng.random() < 0.10
        expansion_signal_days_ago = rng.randint(1, 400) if expansion_signal else None

        tech_adoption_signal = rng.random() < 0.15
        tech_adoption_signal_days_ago = rng.randint(1, 400) if tech_adoption_signal else None

        companies.append(
            Company(
                company_id=company_id,
                name=name,
                industry=industry,
                region=region,
                revenue_eur=float(revenue_eur),
                headcount=headcount,
                founded_year=founded_year,
                domain=domain,
                homepage_text=homepage_text,
                declared_domain_verified=declared_domain_verified,
                phone=phone,
                email=email,
                hiring_open_roles=hiring_open_roles,
                funding_event_days_ago=funding_event_days_ago,
                expansion_signal=expansion_signal,
                expansion_signal_days_ago=expansion_signal_days_ago,
                tech_adoption_signal=tech_adoption_signal,
                tech_adoption_signal_days_ago=tech_adoption_signal_days_ago,
            )
        )

    return companies


@dataclass
class CallRecord:
    company_id: str
    was_called: bool
    closed_won: Optional[bool]


def generate_call_history(companies: list[Company], seed: int = SEED) -> list[CallRecord]:
    """Simulate a year of historical outbound activity for backtesting.

    This is where survivorship bias is baked into the sample on purpose,
    because that is exactly how it happens in real sales orgs: reps do not
    call a random sample of the universe, they call the accounts that
    looked most promising or that were easiest to reach. Revenue and
    headcount (both fit inputs) are used below to decide who got called at
    all, which means any later "win rate by tier" computed only from
    called records is contaminated by that original selection: the tiers
    that were rarely called will show noisy, unreliable rates, not
    necessarily bad ones. evaluate.py measures and reports this gap
    instead of pretending it does not exist.
    """
    rng = random.Random(seed + 1)
    records: list[CallRecord] = []

    for c in companies:
        # Bigger, more "obviously enterprise-looking" accounts got called
        # far more often historically, regardless of true fit.
        call_propensity = 0.15
        if c.headcount >= 50:
            call_propensity += 0.35
        if c.revenue_eur >= 1_000_000:
            call_propensity += 0.20
        if c.region in ("DACH", "UK_I", "Benelux"):
            call_propensity += 0.10
        call_propensity = min(call_propensity, 0.9)

        was_called = rng.random() < call_propensity
        closed_won = None
        if was_called:
            # Baseline win rate, nudged by signals that a decent scoring
            # model should also pick up on (hiring, funding, tech
            # adoption), plus noise. This is intentionally a simplified
            # simulation, not a claim about any real market.
            base = 0.09
            if c.hiring_open_roles > 0:
                base += 0.05
            if c.funding_event_days_ago is not None and c.funding_event_days_ago < 180:
                base += 0.06
            if c.tech_adoption_signal:
                base += 0.04
            if c.headcount < 5 or c.revenue_eur < 30_000:
                base -= 0.05
            base = max(0.02, min(base, 0.55))
            closed_won = rng.random() < base

        records.append(CallRecord(company_id=c.company_id, was_called=was_called, closed_won=closed_won))

    return records
