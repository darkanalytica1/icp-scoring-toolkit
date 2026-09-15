# Method

This document is the deeper writeup behind the toolkit. The README shows what it does; this explains why it is built this way.

## 1. Start from a decision, not a spreadsheet

An ICP definition is only useful if it changes what a rep does next. Before writing a single weight, answer three questions:

- Who gets called this week, and who gets ignored.
- Who gets a different message because they are clearly mid-cycle on something (hiring, funding, a new site), versus a cold approach.
- Who gets suppressed entirely because the data cannot support a real conversation (no working phone, no verifiable domain).

Those three questions map directly onto the three pieces of this toolkit: tiering (`scoring.py`), intent separation (also `scoring.py`), and contactability gating (`quality.py`). If a scoring model cannot answer at least those three questions, it is a report, not a tool.

## 2. Band before you weight

Raw firmographic values are noisy and not directly comparable: revenue is reported in different currencies, different fiscal years, and with different accounting conventions; headcount lags reality by months. Banding (`banding.py`) collapses that noise into a small number of labeled buckets whose boundaries a sales leader can read, argue with, and change.

The practical rule: pick boundaries where a company one unit on either side would obviously be treated the same by a human seller. If your revenue bands are so fine-grained that 995,000 and 1,005,000 land in different bands, your bands are wrong, not your data.

## 3. Never blend fit and intent

This is the single most consequential decision in the toolkit, covered at length in the README. To restate the mechanical reason briefly: fit and intent decay at different rates and answer different questions. Averaging them produces a score that cannot be explained to a rep in one sentence, which means the rep will ignore it and go back to gut feel. Keeping them on two axes, producing a 3x3 quadrant of nine tiers (`A1` through `C3`), keeps the model legible.

## 4. Contactability is a gate, not a score input

A perfect-fit, high-intent account with no working phone number and an unverifiable domain is not this quarter's opportunity, it is a data-enrichment task. `quality.py` produces the contactability evidence, `scoring.py` turns it into its own axis, and `territory.py` treats the configured minimum contactability score (`quality_gates.min_contactability_to_call`) as a hard gate on who ever appears on a call list, independent of how good the account otherwise looks.

Two heuristics inside `quality.py` are worth calling out specifically because they generalize well beyond this toolkit:

**Shared-phone detection.** Count how many distinct company records share the exact same phone number across your whole universe. A number that recurs across dozens of unrelated companies is not a company's direct line, it is almost always an accountant's office, a registered-office or company-formation agent, or an outsourced call centre. No per-row format check can catch this; it is a population-level comparison by construction (`quality.detect_shared_phones`).

**Verify, don't trust, domain-verification flags.** Any upstream enrichment source that claims a domain is "verified" should be treated as a hypothesis, not a fact. Recompute it yourself from the cheapest available evidence (does the homepage text actually contain the company's name) and use your own result (`quality.verify_domain_name_present`). The synthetic data in this repository deliberately includes both directions of enrichment error: domains marked verified that are actually generic template pages, and domains marked unverified whose homepage clearly does contain the company name.

## 5. Turn the ranking into a workable list

A ranked universe is not a call list. `territory.py` builds daily lists that respect a per-rep daily cap, mix tiers deliberately (never 100% top-tier, which burns your best accounts and gives reps no plan for the no's), and cluster by region so a rep is not context-switching between unrelated markets every other call.

## 6. Measure honestly, including your own blind spots

`evaluate.py` reports two different things and never conflates them:

- **Coverage**: how much of the universe is actually actionable (has a phone, a verified domain, a plausible email), and how the universe splits across tiers.
- **Backtest**: whether historical closed-won outcomes correlate with the tiers the model would have assigned, reported alongside the historical CALL COVERAGE per tier.

The second point matters because historical calling was never a random sample of the universe. Reps historically called bigger, easier accounts more often. A tier that was rarely called will show a noisy win rate built on very few data points; a tier that was called constantly will look artificially well-validated. Reporting win rate without reporting the coverage it was computed from is how a scoring model quietly lies to the person relying on it. `evaluate.survivorship_bias_check` exists specifically to surface that gap instead of hiding it.
