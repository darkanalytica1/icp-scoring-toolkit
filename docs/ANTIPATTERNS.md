# Antipatterns

Common mistakes seen in homegrown ICP scoring models, and how this toolkit avoids each one.

## Scoring on data you cannot act on

It is easy to build a model that scores every field you happen to have, including fields with no connection to whether a rep can actually reach or convert the account (an internal record ID, a vanity metric, a field that is 90% null). If a field cannot plausibly change what a rep does next, it should not be in the model. Every input in `config/icp_example.json` maps to either fit, intent, or contactability, and each of those maps to a concrete action (nurture, call now, or fix the data first).

## A single blended score

Averaging fit and intent (or fit, intent, and contactability) into one number is the most common mistake in ICP scoring, and the most damaging. The moment you blend them, you can no longer tell a rep what to do: a "72/100" could be a perfect-fit account with no timing, or a mediocre-fit account with urgent timing, and those require completely different approaches. Keep fit and intent on two axes and let a rep read the quadrant tier directly (see `scoring.py` and the README's worked example).

## Ignoring contactability entirely

A model that ranks accounts purely on fit and intent will happily put an unreachable account at the top of the list. Contactability has to be modeled and gated, not assumed. This toolkit treats it as a hard floor (`quality_gates.min_contactability_to_call`) enforced in `territory.py`, not as a fourth number folded into the score.

## Over-fitting to your best customer

It is tempting to derive an ICP purely by profiling your five best current accounts and building a model that scores anything similar to them highly. Two problems: your best five accounts are a tiny, non-random sample (you did not systematically test whether other segments would have converted just as well), and this approach silently encodes whatever channel or luck produced those specific wins. Calibrate band boundaries and weights against your full addressable universe and your full historical outcome set, not a handful of favorites.

## Trusting a declared verification flag

If a data source (yours or a vendor's) marks a field "verified," that is a claim, not a fact. `quality.py` recomputes domain verification from the cheapest available evidence rather than trusting the incoming flag, specifically because "verified" fields drift out of date and get rubber-stamped by upstream processes with their own incentives to over-report coverage.

## Confusing a shared phone number for a working one

A phone number that resolves and rings is not the same as a phone number that reaches the company you are calling about. Numbers shared across dozens of unrelated companies are almost always an accountant, a registered-office agent, or a call centre. Any format-only phone validation will pass these with a green checkmark. Catching them requires a population-level comparison (`quality.detect_shared_phones`), not a per-row check.

## Backtesting without checking who was actually called

Computing "win rate by tier" from historical outcomes and presenting it as validation, without also reporting what fraction of each tier was ever called, launders a biased sample into an apparently objective number. If your reps historically called big, easy accounts far more often than small or hard-to-reach ones (they almost always did), a tier's win rate is only as trustworthy as its call coverage. Report both, always (`evaluate.backtest_report`, `evaluate.survivorship_bias_check`).

## Static weights, never revisited

Fit weights can reasonably stay stable for months. Intent weights should not: what counts as a meaningful signal (a hiring spike, a funding round, a new tech adoption) changes with the market and with your own product's maturity. The recency-decay parameters and signal weights live in `config/icp_example.json` specifically so they can be revisited on a cadence, not buried in code that nobody reopens.

## Building a list that cannot be worked

A "top 500 accounts" export sorted by score is not a call list. Without a daily cap, a deliberate tier mix, and some geographic or contextual clustering, a rep either burns out the best accounts in a week with no plan for the rest, or spends the day mentally switching between unrelated markets on every call. `territory.py` exists to turn a ranked universe into something a rep can actually pick up and work.
