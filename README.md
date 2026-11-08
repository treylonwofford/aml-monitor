# Countercheck AML: transaction monitoring + SAR narrative assistant

A complete anti-money-laundering (AML) monitoring pipeline on a synthetic bank. It runs detection rules written in SQL, measures them against planted ground truth, scores and queues alerts, and drafts Suspicious Activity Report (SAR) narratives that are fact-checked against the transactions they cite.

**Open `web/index.html` in a browser for the analyst console.** It's one self-contained file.

## The data
`generate_data.py` builds **Riverbend Community Bank**: 3,014 customers and 425,814 transactions over 90 days (June 1 to August 29, 2026), seeded so it's reproducible.

80 accounts are planted as suspicious:

| Typology | Planted | Behavior |
|---|---|---|
| Money mule | 30 | Many unrelated senders, then fast exit to crypto, foreign wire or one P2P payee. 30% are "careful" mules with few senders |
| Structuring | 20 | Cash deposits of $7,600–$9,950 to stay under the $10,000 CTR threshold. 30% spread deposits out to dodge 7-day windows |
| Funnel account | 15 | Cash deposited in 3–6 states, withdrawn or wired out from home |
| Pass-through / shell | 15 | Foreign wires in, near-equal foreign wires out within days |

The legitimate population includes **look-alikes built to trip the rules**: cash-heavy restaurants, homebuyers wiring down payments to title companies, marketplace sellers, event promoters collecting ticket money, crypto hobbyists, traveling sales reps, and new customers moving their savings in. Some bad actors also lie about expected volume at onboarding.

## Detection rules (`rules/*.sql`, DuckDB)
| Rule | Logic | Weight | Alerts | Precision | Recall | Main false positives |
|---|---|---|---|---|---|---|
| R1 Structuring | 3+ cash deposits of $7,500–$9,999 in 7 days, total > $10k | 40 | 30 | 67% | 25% | cash-heavy small businesses |
| R2 Rapid movement | $5k+ in within 3 days, 80%+ out within 5 | 25 | 115 | 66% | 95% | homebuyers, event promoters |
| R3 Fan-in | 8+ different individuals send $5k+ in 14 days | 30 | 49 | 55% | 34% | promoters, marketplace sellers |
| R4 New account velocity | Account ≤ 60 days old receives $10k+ in first 30 days | 10 | 64 | 19% | 15% | new customers moving savings |
| R5 High-risk outflow | $5k+ to crypto or foreign wires in 7 days, ≥ 70% of recent inflow | 30 | 86 | 59% | 64% | crypto hobbyists |
| R6 Multi-state cash | Cash deposited in 3+ states within 14 days | 30 | 34 | 44% | 19% | traveling sales reps |
| R7 Profile deviation | 30-day inflow > 3× stated monthly volume and > $10k | 20 | 159 | 38% | 76% | windfalls, homebuyers |

Recall here is the share of all 80 planted cases. A structuring rule isn't meant to catch mules.

**Scoring:** the risk score adds the weights of every rule that fires, capped at 100.

| Threshold | Alerts | Precision | Recall |
|---|---|---|---|
| Any rule | 312 | 26% | 100% |
| 35 | 128 | 62% | 99% |
| **50 (default)** | **85** | **89%** | **95%** |
| 60 | 71 | 94% | 84% |
| 80 | 43 | 100% | 54% |

At 50, the queue catches 27/30 mules, 19/20 structurers, 15/15 funnels and 15/15 shells. It misses 3 careful mules and 1 careful structurer, and flags 9 legitimate customers.

## SAR narrative assistant
- **`sar_drafter.py`** writes a first draft from structured case facts, following FinCEN's who / what / when / where / why / how guidance, in date order. Every factual sentence cites transaction IDs.
- **`check_figures()`** extracts every dollar amount and date in a narrative and confirms each one exists in the case facts. All 196 drafts pass. An invented figure is caught, for example `$51,000.00` or `June 30, 2026`.
- **`llm_assist.py`** (optional, needs `ANTHROPIC_API_KEY`) asks Claude to polish a draft for flow. It **rejects** the rewrite if any figure isn't in the facts or if the analyst blanks were removed, and keeps the rule-based draft instead.
- Drafts never decide to file. They leave `[ANALYST TO COMPLETE: ...]` for account actions, law enforcement contact and prior SARs.

## Judgment calls
- **Recall over precision.** A missed case is unreported laundering, while a false positive costs analyst time. The default threshold keeps recall at 95%. The console's slider shows the trade-off live.
- **No rule decides alone.** Each rule has an obvious legitimate explanation, so the score requires two signals, or one strong signal plus a profile mismatch.
- **Exclusions are documented in the SQL.** For example, R2 ignores supplier ACH and payroll, so operating businesses don't flood the queue. That one change took R2 from 28% to 72% precision during tuning.
- **AI writes, data decides.** Language models are good at prose and bad at numbers, so figures come only from the data, and any AI rewrite must pass the fact check.
- **Honest about synthetic data.** Planted cases are cleaner than real life, where most alerts don't lead to a SAR. The point is the method: measurable rules, documented trade-offs, traceable narratives.

## Run it
```
pip install duckdb
python3 generate_data.py      # data/customers.csv, data/transactions.csv
python3 run_monitoring.py     # rules, scoring, evaluation, drafts -> reports/, web/data.json
python3 build_web.py          # web/index.html (self-contained console)
```

**Outputs:**
- `reports/metrics.json`: per-rule and threshold metrics, plus a fan-in parameter sweep
- `reports/alerts.csv`: every scored account
- `reports/sar_drafts/*.md`: one narrative per alert (`*.facts.json` holds the facts behind it)

All names, accounts and transactions are fictional.
