"""
Optional: ask Claude to polish a SAR draft, then refuse the result if it invents anything.

The rule-based draft in sar_drafter.py is always the source of truth. This step only rewrites
for flow and plain language. The output is accepted only if every dollar figure and date in it
appears in the case facts (check_figures), and all [ANALYST TO COMPLETE] blanks survive.

Usage:
  export ANTHROPIC_API_KEY=...
  python3 llm_assist.py reports/sar_drafts/A102935.facts.json
  python3 llm_assist.py reports/sar_drafts/A102935.facts.json --dry-run   # print the prompt only
"""
import json, os, sys, urllib.request
from sar_drafter import draft, check_figures, usd, day

MODEL = os.environ.get("SAR_MODEL", "claude-sonnet-5-5")

SYSTEM = """You edit Suspicious Activity Report (SAR) narratives for a bank's financial intelligence unit.
Rules you must follow:
- Use ONLY facts in the CASE FACTS and DRAFT. Do not add amounts, dates, names, motives or conclusions.
- Keep every dollar amount and date exactly as written, including cents.
- Keep every transaction citation in square brackets, e.g. [T0417911, T0417902].
- Keep the text "[ANALYST TO COMPLETE: ...]" exactly as written.
- Do not say a crime occurred. Say activity is "suspected" or "consistent with" a typology.
- Chronological order. Plain, factual language. No headings or bullet points. Under 450 words.
Return only the revised narrative."""


def build_prompt(facts, base):
    slim = {k: v for k, v in facts.items() if k not in ("allowed_money", "allowed_dates")}
    return f"CASE FACTS (JSON):\n{json.dumps(slim, indent=1, default=str)}\n\nDRAFT:\n{base}\n\nRevise the draft for clarity and flow."


def call_claude(prompt):
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", method="POST",
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
        data=json.dumps({"model": MODEL, "max_tokens": 1500, "system": SYSTEM, "messages": [{"role": "user", "content": prompt}]}).encode())
    with urllib.request.urlopen(req, timeout=120) as r:
        return "".join(b.get("text", "") for b in json.load(r)["content"])


def rebuild_allowed(facts):
    """Recompute the allowed figures from the saved facts file."""
    money, dates = {usd(facts["total_in"]), usd(facts["total_out"]), usd(facts["customer"]["expected_monthly_in"])}, set()
    for e in facts["evidence"].values():
        dates |= {day(e["start"]), day(e["end"])}
        for k, v in e["metrics"].items():
            if isinstance(v, (int, float)) and k not in ("n", "n_deposits", "senders", "states", "branches", "pct", "multiple", "n_windows"):
                money.add(usd(v))
    dates |= {day(facts["period"]["start"]), day(facts["period"]["end"]), day(facts["customer"]["open_date"])}
    facts["allowed_money"], facts["allowed_dates"] = sorted(money), sorted(dates)
    return facts


if __name__ == "__main__":
    facts = rebuild_allowed(json.load(open(sys.argv[1])))
    base = draft(facts)
    prompt = build_prompt(facts, base)
    if "--dry-run" in sys.argv or not os.environ.get("ANTHROPIC_API_KEY"):
        print(SYSTEM, "\n\n", prompt)
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("\n(no ANTHROPIC_API_KEY set: printed the prompt only)")
        sys.exit(0)
    out = call_claude(prompt)
    n, bad = check_figures(out, facts)
    if bad or "[ANALYST TO COMPLETE" not in out:
        print("REJECTED. The rewrite introduced figures not in the case facts or dropped the analyst blanks:", bad)
        print("Keeping the rule-based draft:\n\n" + base)
        sys.exit(1)
    print(f"ACCEPTED ({n} figures checked, all traced to case facts)\n\n{out}")
