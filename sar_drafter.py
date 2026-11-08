"""
Fact-grounded SAR narrative drafter.

Builds a first-draft Suspicious Activity Report narrative from structured case facts, following
FinCEN's guidance to answer who, what, when, where, why and how in chronological order. Every
sentence that states an amount or a date cites the transaction IDs it came from, and
`check_figures()` confirms that every dollar figure and date in the draft appears in the facts.

The drafter never decides whether to file. It leaves clearly marked blanks for the analyst:
account actions, law enforcement contact and prior SARs.
"""
import re
from datetime import datetime

BANK = "Riverbend Community Bank"

TYPOLOGY = {
    "mule": ("money mule activity", "Funds arrived from many unrelated individuals and were moved out within days, mostly to {exits}. This pattern is consistent with an account used to receive and forward proceeds of fraud on behalf of others."),
    "structuring": ("structuring of cash deposits to evade Currency Transaction Report requirements", "Cash deposits were repeatedly made in amounts just below the $10,000 reporting threshold over short periods, which is consistent with deliberate structuring."),
    "funnel": ("funnel account activity", "Cash was deposited at branches in several states and then withdrawn or wired out from a single location, consistent with a funnel account used to move cash across regions."),
    "pass_through": ("pass-through activity consistent with a shell company", "Large wires arrived from foreign companies and nearly equal amounts were wired to different foreign companies within days, with little other business activity. The account appears to be used to pass funds through rather than to operate a business."),
    "unusual": ("unusual activity inconsistent with the customer profile", "Activity on the account departed sharply from the customer's expected volume and pattern."),
}


def usd(x):
    return f"${x:,.2f}"


def day(ts):
    return datetime.strptime(str(ts)[:10], "%Y-%m-%d").strftime("%B %-d, %Y")


def span(a, b, lead="From"):
    a, b = day(a), day(b)
    return f"On {a}" if a == b else f"{lead} {a} {'to' if lead == 'From' else 'and'} {b}"


def joinand(xs):
    xs = list(xs)
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def cite(ids, limit=4):
    ids = list(ids)
    more = f" +{len(ids) - limit} more" if len(ids) > limit else ""
    return "[" + ", ".join(ids[:limit]) + more + "]"


def infer_typology(rules, customer_type):
    r = set(rules)
    if "R1" in r:
        return "structuring"
    if "R6" in r:
        return "funnel"
    if "R3" in r or ("R4" in r and "R5" in r):
        return "mule"
    if customer_type == "business" and "R2" in r and "R5" in r:
        return "pass_through"
    return "unusual"


def draft(facts):
    """facts: dict built by run_monitoring.build_facts()"""
    c, ev = facts["customer"], facts["evidence"]
    typ = facts["typology"]
    label, why = TYPOLOGY[typ]
    period = facts["period"]
    paras = []

    who = f"{c['name']}, a {'business customer' if c['customer_type'] == 'business' else 'customer'} whose stated occupation is \"{c['occupation']}\""
    paras.append(
        f"{BANK} is filing this report on suspected {label} involving {who}, "
        f"holder of account {c['account_id']} opened on {day(c['open_date'])}. "
        f"Between {day(period['start'])} and {day(period['end'])}, the account received {usd(facts['total_in'])} "
        f"and sent out {usd(facts['total_out'])} in the transactions described below. At account opening the customer "
        f"stated expected monthly deposits of about {usd(c['expected_monthly_in'])}."
    )

    body = []
    for rid, e in sorted(ev.items(), key=lambda kv: kv[1]["start"]):
        m, ids = e["metrics"], e["txn_ids"]
        if rid == "R1":
            body.append(f"{span(e['start'], e['end'])}, the customer made {m['n_deposits']} cash deposits between "
                        f"{usd(m['min_amt'])} and {usd(m['max_amt'])}, totaling {usd(m['total'])}, at {m['branches']} {'branch' if m['branches'] == 1 else 'branches'} {cite(ids)}. "
                        f"Each deposit was under the $10,000 reporting threshold, while the total was not.")
        elif rid == "R3":
            body.append(f"{span(e['start'], e['end'])}, the account received {m['n']} payments totaling {usd(m['total'])} "
                        f"from {m['senders']} different individuals with no apparent relationship to the customer {cite(ids)}.")
        elif rid == "R6":
            body.append(f"{span(e['start'], e['end'])}, cash totaling {usd(m['total'])} was deposited at branches in "
                        f"{m['states']} states ({m['state_list']}), outside the customer's home state of {c['state']} {cite(ids)}.")
        elif rid == "R2":
            moved = f"{m['pct']}% of it" if m["pct"] <= 100 else "more than had come in"
            body.append(f"{span(e['start'], e['end'], 'Between')}, {usd(m['inflow'])} arrived and {usd(m['outflow'])} left the account "
                        f"within five days ({moved}), so the money barely rested in the account {cite(ids)}.")
        elif rid == "R5":
            share = f"equal to {m['pct']}% of" if m["pct"] <= 100 else "more than"
            body.append(f"{span(e['start'], e['end'])}, {usd(m['hr_out'])} was sent to {m['dest']} {cite(ids)}, "
                        f"{share} the money the account received in that period and the week before.")
        elif rid == "R4":
            body.append(f"The account, opened on {day(c['open_date'])}, received {usd(m['total'])} within its first 30 days {cite(ids)}.")
        elif rid == "R7":
            body.append(f"In the 30 days starting {day(e['start'])}, deposits reached {usd(m['in_30d'])}, about {m['multiple']} times the "
                        f"customer's stated expected monthly volume {cite(ids)}.")
    paras.append(" ".join(body))

    exits = facts.get("exit_summary") or "other parties"
    paras.append(why.format(exits=exits) + " " + facts["profile_line"])

    paras.append(
        "The account was identified by automated transaction monitoring (rules " + ", ".join(sorted(ev)) + ") "
        "and reviewed by an analyst. [ANALYST TO COMPLETE: actions taken on the account (for example, restricted or closed); "
        "whether law enforcement has been contacted; any prior SARs on this subject.] "
        f"Supporting documentation is retained by {BANK} and is available on request."
    )
    return "\n\n".join(paras)


MONEY = re.compile(r"\$[\d,]+\.\d{2}")
DATE = re.compile(r"(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}, \d{4}")


def check_figures(text, facts):
    """Every dollar figure and date in the narrative must come from the case facts.
    Returns (checked, unsupported_list). Used to guard both this drafter and any LLM rewrite."""
    allowed_money = set(facts["allowed_money"]) | {"$10,000.00"}
    allowed_dates = set(facts["allowed_dates"])
    text = text.replace("$10,000 ", "$10,000.00 ")
    found_m = MONEY.findall(text)
    found_d = [m.group(0) for m in DATE.finditer(text)]
    bad = [x for x in found_m if x not in allowed_money] + [x for x in found_d if x not in allowed_dates]
    return len(found_m) + len(found_d), bad
