"""
Run the monitoring pipeline end to end:
  1. load the synthetic bank into DuckDB
  2. run every SQL rule in rules/
  3. pull the evidence transactions behind each hit
  4. score accounts, measure precision and recall against the planted labels, sweep thresholds
  5. draft a SAR narrative for each alert and fact-check it
  6. write reports/ and web/data.json for the case console

Run: python3 run_monitoring.py
"""
import duckdb, glob, json, os, csv
from collections import defaultdict
from sar_drafter import draft, check_figures, infer_typology, usd, day

HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)
os.makedirs("reports/sar_drafts", exist_ok=True)

RULES = {
    "R1": ("Structuring", 40, "3+ cash deposits of $7,500–$9,999 in 7 days, over $10,000 total"),
    "R2": ("Rapid movement", 25, "$5,000+ in within 3 days, 80%+ out within 5"),
    "R3": ("Fan-in", 30, "8+ different individuals send $5,000+ in 14 days"),
    "R4": ("New account velocity", 10, "Account ≤60 days old receives $10,000+ in first 30 days"),
    "R5": ("High-risk outflow", 30, "$5,000+ to crypto or foreign wires in 7 days, 70%+ of recent inflow"),
    "R6": ("Multi-state cash", 30, "Cash deposited in 3+ states within 14 days"),
    "R7": ("Profile deviation", 20, "30-day inflow over 3x stated monthly volume and $10,000"),
}
DEFAULT_THRESHOLD = 50

con = duckdb.connect()
con.execute("CREATE TABLE customers AS SELECT * FROM read_csv_auto('data/customers.csv')")
con.execute("""CREATE TABLE txn AS SELECT * EXCLUDE(ts, memo, location_state, branch_id), CAST(ts AS TIMESTAMP) ts,
               coalesce(memo,'') memo, coalesce(location_state,'') location_state, coalesce(branch_id,'') branch_id
               FROM read_csv_auto('data/transactions.csv')""")
cust = {r[0]: dict(zip([d[0] for d in con.description], r)) for r in con.execute("SELECT * FROM customers").fetchall()}
cust = {v["account_id"]: v for v in cust.values()}

EVIDENCE_SQL = {
    "R1": "channel='CASH' AND direction='IN' AND amount>=7500 AND amount<10000 AND ts BETWEEN ? AND ?",
    "R2": "((direction='IN' AND memo<>'PAYROLL' AND channel<>'CARD_SETTLEMENT') OR (direction='OUT' AND (channel IN ('WIRE','P2P','CASH_WITHDRAWAL') OR counterparty_type='crypto_exchange'))) AND ts BETWEEN ? AND ?",
    "R3": "direction='IN' AND counterparty_type='individual' AND channel IN ('P2P','ACH') AND ts BETWEEN ? AND ?",
    "R4": "direction='IN' AND memo<>'PAYROLL' AND ts BETWEEN ? AND ?",
    "R5": "direction='OUT' AND (counterparty_type='crypto_exchange' OR country<>'US') AND ts BETWEEN ? AND ?",
    "R6": "channel='CASH' AND direction='IN' AND ts BETWEEN ? AND ?",
    "R7": "direction='IN' AND ts BETWEEN ? AND ? ORDER BY amount DESC LIMIT 12",
}

# ---- 1-3. run rules and collect evidence -------------------------------------------------------
hits = defaultdict(dict)       # account -> rule -> {metrics, start, end, txn_ids}
for f in sorted(glob.glob("rules/R*.sql")):
    rid = os.path.basename(f).split("_")[0]
    cur = con.execute(open(f).read())
    cols = [d[0] for d in cur.description]
    for row in cur.fetchall():
        r = dict(zip(cols, row))
        acct = r.pop("account_id")
        ws, we = r.pop("win_start"), r.pop("win_end")
        q = f"SELECT txn_id, ts, direction, amount, channel, counterparty, counterparty_type, country, location_state, branch_id FROM txn WHERE account_id=? AND {EVIDENCE_SQL[rid]}"
        if rid == "R2":  # inflows counted over 3 days, outflows over 5, matching the rule
            q = ("SELECT txn_id, ts, direction, amount, channel, counterparty, counterparty_type, country, location_state, branch_id FROM txn WHERE account_id=? AND "
                 "((direction='IN' AND memo<>'PAYROLL' AND channel<>'CARD_SETTLEMENT' AND ts >= ? AND ts < ? + INTERVAL 3 DAY) OR "
                 "(direction='OUT' AND (channel IN ('WIRE','P2P','CASH_WITHDRAWAL') OR counterparty_type='crypto_exchange') AND ts >= ? AND ts < ? + INTERVAL 5 DAY))")
            rows = con.execute(q, [acct, ws, ws, ws, ws]).fetchall()
        else:
            rows = con.execute(q, [acct, ws, we]).fetchall()
        hits[acct][rid] = {"metrics": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in r.items()},
                           "start": str(ws), "end": str(we), "rows": rows}

# ---- 4. score + evaluate ------------------------------------------------------------------------
def score(rules):
    s = sum(RULES[r][1] for r in rules)
    return min(100, s)

labels = {a: c["label"] for a, c in cust.items()}
positives = {a for a, l in labels.items() if l != "none"}
scored = {a: score(h.keys()) for a, h in hits.items()}

def prf(flagged):
    tp = len(flagged & positives); fp = len(flagged) - tp; fn = len(positives - flagged)
    p = tp / len(flagged) if flagged else 0; r = tp / len(positives)
    return {"alerts": len(flagged), "tp": tp, "fp": fp, "fn": fn, "precision": round(p, 3), "recall": round(r, 3),
            "f1": round(2 * p * r / (p + r), 3) if p + r else 0}

per_rule = []
for rid, (name, w, desc) in RULES.items():
    flagged = {a for a, h in hits.items() if rid in h}
    per_rule.append({"rule": rid, "name": name, "weight": w, "logic": desc, **prf(flagged),
                     "fp_cohorts": dict(sorted(((c, n) for c, n in __import__("collections").Counter(cust[a]["cohort"] for a in flagged if a not in positives).items()), key=lambda x: -x[1]))})

sweep = [{"threshold": t, **prf({a for a, s in scored.items() if s >= t})} for t in range(10, 101, 5)]
any_rule = prf(set(hits))
default = prf({a for a, s in scored.items() if s >= DEFAULT_THRESHOLD})

# R3 parameter sweep: how the fan-in sender threshold trades precision for recall
r3_sql = open("rules/R3_fan_in.sql").read()
r3_sweep = []
for n in range(4, 15):
    flagged = {r[0] for r in con.execute(r3_sql.replace("senders >= 8", f"senders >= {n}")).fetchall()}
    r3_sweep.append({"senders": n, **prf(flagged)})

by_typology = {}
flagged_default = {a for a, s in scored.items() if s >= DEFAULT_THRESHOLD}
for typ in ["mule", "structuring", "funnel", "pass_through"]:
    group = {a for a in positives if labels[a] == typ}
    by_typology[typ] = {"planted": len(group), "caught": len(group & flagged_default)}

# ---- 5. facts + SAR drafts ----------------------------------------------------------------------
def build_facts(acct):
    c = cust[acct]; h = hits[acct]
    ev, all_rows = {}, {}
    for rid in sorted(h):
        e = h[rid]; rows = e["rows"]
        for r in rows: all_rows[r[0]] = r
        m = dict(e["metrics"])
        ins = [r for r in rows if r[2] == "IN"]; outs = [r for r in rows if r[2] == "OUT"]
        if rid == "R1":
            m.update(min_amt=min(r[3] for r in rows), max_amt=max(r[3] for r in rows), total=round(sum(r[3] for r in rows), 2),
                     n_deposits=len(rows), branches=len({r[9] for r in rows}))
        if rid == "R3":
            m.update(n=len(rows), total=round(sum(r[3] for r in rows), 2), senders=len({r[5] for r in rows}))
        if rid == "R6":
            st = sorted({r[8] for r in rows}); m.update(states=len(st), state_list=", ".join(st), total=round(sum(r[3] for r in rows), 2))
        if rid == "R2":
            i, o = round(sum(r[3] for r in ins), 2), round(sum(r[3] for r in outs), 2)
            assert abs(i - m["inflow"]) < 1 and abs(o - m["outflow"]) < 1, (acct, i, m["inflow"], o, m["outflow"])
            m.update(inflow=i, outflow=o, pct=round(100 * o / i) if i else 0)
        if rid == "R5":
            hr = round(sum(r[3] for r in outs), 2)
            dests = sorted({(r[5] + (f" ({r[7]})" if r[7] != "US" else "")) for r in outs})
            prior = m.get("prior_in") or 0
            m.update(hr_out=hr, dest=(dests[0] if len(dests) == 1 else ", ".join(dests[:-1]) + " and " + dests[-1]), pct=round(100 * hr / prior) if prior else 100)
        if rid == "R4":
            m.update(total=round(sum(r[3] for r in rows), 2))
        if rid == "R7":
            m.update(in_30d=round(m["in_30d"], 2))
        ts = [str(r[1]) for r in rows]
        ev[rid] = {"metrics": m, "txn_ids": [r[0] for r in sorted(rows, key=lambda r: r[1])], "start": min(ts), "end": max(ts)}
    rows = list(all_rows.values())
    total_in = round(sum(r[3] for r in rows if r[2] == "IN"), 2)
    total_out = round(sum(r[3] for r in rows if r[2] == "OUT"), 2)
    outs = [r for r in rows if r[2] == "OUT" and r[4] in ("WIRE", "P2P", "ACH", "CASH_WITHDRAWAL")]
    by_dest = defaultdict(float)
    for r in outs:
        key = r[5] if r[6] != "individual" else f"one individual ({r[5]})"
        if r[4] == "CASH_WITHDRAWAL": key = "cash withdrawals"
        by_dest[key + (f" ({r[7]})" if r[7] != "US" else "")] += r[3]
    top = sorted(by_dest.items(), key=lambda x: -x[1])[:3]
    names = [k for k, v in top]
    exit_summary = (names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]) if names else ""
    typ = infer_typology(h.keys(), c["customer_type"])
    profile_line = (f"Nothing in the customer's profile ({c['occupation']}, expected monthly deposits of {usd(c['expected_monthly_in'])}) "
                    f"explains activity of this size or pattern.")
    facts = {"customer": {k: c[k] for k in ["customer_id", "account_id", "name", "customer_type", "occupation", "state", "open_date", "expected_monthly_in"]},
             "typology": typ, "period": {"start": min(str(r[1]) for r in rows), "end": max(str(r[1]) for r in rows)},
             "total_in": total_in, "total_out": total_out, "evidence": ev, "exit_summary": exit_summary, "profile_line": profile_line}
    money = {usd(total_in), usd(total_out), usd(c["expected_monthly_in"])} | {usd(r[3]) for r in rows}
    for e in ev.values():
        for k, v in e["metrics"].items():
            if isinstance(v, (int, float)) and k not in ("n", "n_deposits", "senders", "states", "branches", "pct", "multiple", "n_windows"):
                money.add(usd(v))
    dates = {day(facts["period"]["start"]), day(facts["period"]["end"]), day(c["open_date"])} | {day(e["start"]) for e in ev.values()} | {day(e["end"]) for e in ev.values()}
    facts["allowed_money"], facts["allowed_dates"] = sorted(money), sorted(dates)
    return facts, rows

QUEUE_MIN = 25
web_accounts, alert_rows = [], []
for acct, s in sorted(scored.items(), key=lambda x: -x[1]):
    c = cust[acct]
    entry = {"id": acct, "score": s, "rules": sorted(hits[acct]), "label": labels[acct], "cohort": c["cohort"]}
    if s >= QUEUE_MIN:
        facts, rows = build_facts(acct)
        text = draft(facts)
        n_checked, unsupported = check_figures(text, facts)
        assert not unsupported, (acct, unsupported)
        ps, pe = facts["period"]["start"][:10], facts["period"]["end"][:10]
        allt = con.execute("SELECT txn_id, strftime(ts, '%m-%d %H:%M'), direction, amount, channel, counterparty, counterparty_type, country, location_state FROM txn WHERE account_id=? AND ts BETWEEN CAST(? AS TIMESTAMP) - INTERVAL 3 DAY AND CAST(? AS TIMESTAMP) + INTERVAL 4 DAY AND channel NOT IN ('CARD','ATM','CARD_SETTLEMENT') ORDER BY ts", [acct, ps, pe]).fetchall()
        daily = con.execute("SELECT datediff('day', DATE '2026-06-01', CAST(ts AS DATE)) d, round(sum(CASE WHEN direction='IN' THEN amount ELSE 0 END)), round(sum(CASE WHEN direction='OUT' THEN amount ELSE 0 END)) FROM txn WHERE account_id=? GROUP BY 1 ORDER BY 1", [acct]).fetchall()
        entry.update(customer=facts["customer"], typology=facts["typology"], period=facts["period"], total_in=facts["total_in"], total_out=facts["total_out"],
                     evidence={k: {"metrics": v["metrics"], "txn_ids": v["txn_ids"], "start": v["start"][:16], "end": v["end"][:16]} for k, v in facts["evidence"].items()},
                     narrative=text, figures_checked=n_checked,
                     txns=[[r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8]] for r in allt], daily=[list(d) for d in daily])
        with open(f"reports/sar_drafts/{acct}.md", "w") as fh:
            fh.write(f"# SAR narrative draft: {c['name']} ({acct})\n\nRisk score {s} · rules {', '.join(sorted(hits[acct]))} · typology {facts['typology']}\n\n"
                     f"Figures checked against transaction data: {n_checked}, unsupported: 0\n\n---\n\n{text}\n")
        with open(f"reports/sar_drafts/{acct}.facts.json", "w") as fh:
            json.dump({k: v for k, v in facts.items() if not k.startswith("allowed")}, fh, indent=2, default=str)
    web_accounts.append(entry)
    alert_rows.append({"account_id": acct, "name": c["name"], "score": s, "rules": " ".join(sorted(hits[acct])), "ground_truth": labels[acct], "cohort": c["cohort"]})

# ---- 6. outputs ---------------------------------------------------------------------------------
stats = con.execute("SELECT count(*), count(DISTINCT account_id), min(ts), max(ts), sum(amount) FROM txn").fetchone()
summary = {"bank": "Riverbend Community Bank (synthetic)", "customers": len(cust), "transactions": stats[0], "period": [str(stats[2])[:10], str(stats[3])[:10]],
           "volume": round(stats[4], 2), "planted": len(positives), "planted_by_type": by_typology, "rules": per_rule, "sweep": sweep,
           "r3_sweep": r3_sweep, "default_threshold": DEFAULT_THRESHOLD, "default": default, "any_rule": any_rule,
           "rule_meta": {k: {"name": v[0], "weight": v[1], "logic": v[2]} for k, v in RULES.items()}, "queue_min": QUEUE_MIN}
json.dump({"summary": summary, "accounts": web_accounts}, open("web/data.json", "w"), separators=(",", ":"), default=str)
with open("reports/alerts.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(alert_rows[0])); w.writeheader(); w.writerows(alert_rows)
with open("reports/metrics.json", "w") as fh:
    json.dump({k: summary[k] for k in ["rules", "sweep", "r3_sweep", "default", "any_rule", "planted_by_type"]}, fh, indent=2)

print(f"accounts with any hit: {len(hits)}  |  any-rule: P={any_rule['precision']} R={any_rule['recall']}")
for r in per_rule:
    print(f"  {r['rule']} {r['name']:22} alerts={r['alerts']:4} P={r['precision']:.2f} R={r['recall']:.2f}  FP from {r['fp_cohorts']}")
print(f"threshold {DEFAULT_THRESHOLD}: {default}")
for row in sweep: print(f"  t={row['threshold']:3} alerts={row['alerts']:4} P={row['precision']:.2f} R={row['recall']:.2f} F1={row['f1']:.2f}")
print("by typology:", by_typology)
print("queue cases with drafts:", sum(1 for a in web_accounts if "narrative" in a), " web/data.json KB:", os.path.getsize("web/data.json") // 1024)
