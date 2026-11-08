"""
Generate a synthetic retail bank: customers, KYC profiles and 90 days of transactions.

Planted suspicious behavior (ground truth labels):
  mule          money mule: many unrelated senders in, fast outflow to crypto / foreign wire / one payee
  structuring   cash deposits kept just under the $10,000 CTR threshold
  funnel        cash deposited in several states, pulled out quickly in another
  pass_through  shell-like business: wires in and out of near-equal amounts, little else

Legitimate look-alikes (label "none") built to trip the same rules:
  seller        marketplace seller: many small P2P payments from strangers
  smallbiz      cash-heavy small business, sometimes deposits $8-10k
  crypto_buyer  buys crypto from paychecks
  new_mover     new account funded with savings from another bank
  homebuyer     large transfer in, wire to a title company days later
  traveler      sales rep depositing small amounts in several states

Everything is fictional. Run: python3 generate_data.py  (seeded, reproducible)
"""
import csv, random, datetime as dt, os

R = random.Random(20260601)
START = dt.datetime(2026, 6, 1)
DAYS = 90
END = START + dt.timedelta(days=DAYS)
OUT = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(OUT, exist_ok=True)

FIRST = "James Mary Robert Patricia John Jennifer Michael Linda David Elizabeth William Barbara Richard Susan Joseph Jessica Thomas Sarah Charles Karen Christopher Lisa Daniel Nancy Matthew Betty Anthony Sandra Mark Ashley Donald Kimberly Steven Emily Andrew Donna Paul Michelle Joshua Carol Kenneth Amanda Kevin Melissa Brian Deborah Timothy Stephanie Ronald Rebecca Jason Laura George Sharon Edward Cynthia Jeffrey Kathleen Ryan Amy Jacob Angela Gary Shirley Nicholas Brenda Eric Emma Jonathan Anna Stephen Pamela Larry Nicole Justin Samantha Scott Katherine Brandon Christine Benjamin Debra Samuel Rachel Gregory Carolyn Alexander Janet Patrick Maria Frank Olivia Raymond Heather Jack Helen Dennis Catherine Jerry Diane Tyler Julie Aaron Victoria Jose Joyce Adam Lauren Nathan Kelly Henry Christina Zachary Ruth Douglas Joan Peter Virginia Kyle Judith Noah Evelyn Ethan Hannah Jeremy Andrea Walter Megan Christian Cheryl Keith Jacqueline Roger Martha Terry Madison Austin Teresa Sean Gloria Gerald Sara Carl Janice Harold Ann Dylan Kathryn Arthur Abigail Lawrence Sophia Jordan Frances Jesse Jean Bryan Alice Billy Judy Bruce Isabella Gabriel Julia Joe Grace Logan Amber Alan Denise Juan Danielle Albert Marilyn Willie Beverly Elijah Charlotte Wayne Natalie Randy Theresa Vincent Diana Mason Brittany Roy Doris Ralph Kayla Bobby Alexis Russell Lori Bradley Marie Philip Tiffany Eugene Ruby".split()
LAST = "Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez Hernandez Lopez Gonzalez Wilson Anderson Thomas Taylor Moore Jackson Martin Lee Perez Thompson White Harris Sanchez Clark Ramirez Lewis Robinson Walker Young Allen King Wright Scott Torres Nguyen Hill Flores Green Adams Nelson Baker Hall Rivera Campbell Mitchell Carter Roberts Gomez Phillips Evans Turner Diaz Parker Cruz Edwards Collins Reyes Stewart Morris Morales Murphy Cook Rogers Gutierrez Ortiz Morgan Cooper Peterson Bailey Reed Kelly Howard Ramos Kim Cox Ward Richardson Watson Brooks Chavez Wood James Bennett Gray Mendoza Ruiz Hughes Price Alvarez Castillo Sanders Patel Myers Long Ross Foster Jimenez Powell Jenkins Perry Russell Sullivan Bell Coleman Butler Henderson Barnes Gonzales Fisher Vasquez Simmons Romero Jordan Patterson Alexander Hamilton Graham Reynolds Griffin Wallace Moreno West Cole Hayes Bryant Herrera Gibson Ellis Tran Medina Aguilar Stevens Murray Ford Castro Marshall Owens Harrison Fernandez McDonald Woods Washington Kennedy Wells Vargas Henry Chen Freeman Webb Tucker Guzman Burns Crawford Olson Simpson Porter Hunter Gordon Mendez Silva Shaw Snyder Mason Dixon Munoz Hunt Hicks Holmes Palmer Wagner Black Robertson Boyd Rose Stone Salazar Fox Warren Mills Meyer Rice Schmidt Garza Daniels Ferguson Nichols Stephens Soto Weaver Ryan Gardner Payne Grant Dunn Kelley Spencer Hawkins Arnold Pierce Hansen Peters Santos Hart Bradley Knight Elliott Cunningham Duncan Armstrong Hudson Carroll Lane Riley Andrews Ruiz".split()
STATES = ["NC", "SC", "GA", "VA", "TN", "FL", "TX", "NY", "PA", "OH", "IL", "CA", "AZ", "NJ", "MD"]
HOME = ["NC", "NC", "NC", "SC", "SC", "VA"]  # the bank's footprint
EMPLOYERS = ["Piedmont Health System", "Carolina Logistics Inc", "Queen City Schools", "Atlantic Retail Group", "Summit Manufacturing", "Harbor Insurance Co", "Blue Ridge Utilities", "Metro Transit Authority", "Crescent Software LLC", "Southeast Distribution"]
MERCHANTS = ["Harris Grocery", "QuickFuel", "Mega Mart", "Corner Pharmacy", "StreamFlix", "City Power & Light", "CellNet Wireless", "Burger Barn", "Home Supply Depot", "RideShare", "Coffee Collective", "Book Nook"]
EXCHANGES = ["CoinVault Exchange", "BitHarbor", "NovaCrypto"]
TITLE_COS = ["Carolina Title & Escrow", "Southern Closing Services"]
FOREIGN = [("HK", "Golden Bridge Trading Ltd"), ("AE", "Meridian General Trading FZE"), ("CY", "Aster Holdings Ltd"), ("MX", "Comercializadora Delta SA"), ("SG", "Pacific Rim Ventures Pte")]
OCC = {"retail": ["Nurse", "Teacher", "Warehouse associate", "Retail manager", "Software developer", "Office administrator", "Electrician", "Accountant", "Driver", "Customer service rep"],
       "seller": ["Reseller (online marketplace)", "Craft seller", "Sneaker reseller"],
       "smallbiz": ["Restaurant", "Convenience store", "Laundromat", "Auto repair shop", "Food truck", "Barbershop"],
       "crypto_buyer": ["Software developer", "Engineer", "Sales associate", "Analyst"],
       "new_mover": ["Nurse", "Engineer", "Teacher", "Consultant"],
       "homebuyer": ["Physician", "Engineer", "Manager", "Attorney"],
       "traveler": ["Field sales representative", "Traveling nurse", "Equipment technician"],
       "new_crypto": ["Software engineer", "Day trader", "Consultant"],
       "promoter": ["Event promoter", "Concert organizer", "Youth sports league treasurer"],
       "mule": ["Student", "Unemployed", "Part-time retail", "Student"],
       "structuring": ["Contractor", "Landscaper", "Self-employed", "Mechanic"],
       "funnel": ["Self-employed", "Unemployed", "Delivery driver"],
       "pass_through": ["Consulting LLC", "Import/export LLC", "General trading LLC"]}

COHORTS = [("retail", 2300, "none"), ("seller", 120, "none"), ("smallbiz", 170, "none"), ("crypto_buyer", 140, "none"),
           ("new_mover", 80, "none"), ("homebuyer", 40, "none"), ("traveler", 60, "none"), ("new_crypto", 12, "none"), ("promoter", 12, "none"),
           ("mule", 30, "mule"), ("structuring", 20, "structuring"), ("funnel", 15, "funnel"), ("pass_through", 15, "pass_through")]

txns, customers = [], []
tid = [0]
cp_pool = [f"{R.choice(FIRST)} {R.choice(LAST)}" for _ in range(6000)]


def money(x):
    return round(x, 2)


def add(acct, ts, direction, amount, channel, cp_name, cp_type, state=None, country="US", branch=None, memo=""):
    if ts < START or ts >= END or amount <= 0:
        return None
    tid[0] += 1
    t = {"txn_id": f"T{tid[0]:07d}", "account_id": acct["account_id"], "ts": ts.strftime("%Y-%m-%d %H:%M:%S"),
         "direction": direction, "amount": money(amount), "channel": channel, "counterparty": cp_name,
         "counterparty_type": cp_type, "location_state": state or "", "country": country,
         "branch_id": branch or "", "memo": memo}
    txns.append(t)
    return t


def rand_time(day, h0=8, h1=21):
    return START + dt.timedelta(days=day, hours=R.randint(h0, h1 - 1), minutes=R.randint(0, 59), seconds=R.randint(0, 59))


def branch(state):
    return f"BR-{state}-{R.randint(1, 12):02d}"


def baseline(a, pay=None, spend=1.0, friends=None):
    """Ordinary consumer activity: payroll, rent, card spend, ATM, a little P2P."""
    pay = pay or R.uniform(1400, 3800)
    emp = R.choice(EMPLOYERS)
    first_pay = R.randint(0, 13)
    rent = money(pay * R.uniform(0.55, 0.9))
    friends = friends or R.sample(cp_pool, 4)
    for d in range(DAYS):
        if (d - first_pay) % 14 == 0 and d >= first_pay:
            add(a, rand_time(d, 6, 8), "IN", pay * R.uniform(0.97, 1.03), "ACH", emp, "employer", memo="PAYROLL")
        if d % 30 == R.randint(0, 2):
            add(a, rand_time(d), "OUT", rent, "ACH", "Oakwood Property Mgmt", "landlord", memo="RENT")
        for _ in range(R.choices([0, 1, 2, 3], [0.2, 0.4, 0.3, 0.1])[0]):
            if R.random() < spend:
                add(a, rand_time(d), "OUT", R.uniform(4, 140), "CARD", R.choice(MERCHANTS), "merchant", state=a["state"])
        if R.random() < 0.04:
            add(a, rand_time(d), "OUT", R.choice([40, 60, 80, 100, 200]), "ATM", "ATM withdrawal", "self", state=a["state"], branch=branch(a["state"]))
        if R.random() < 0.03:
            add(a, rand_time(d), "IN", R.uniform(15, 250), "P2P", R.choice(friends), "individual")
        if R.random() < 0.04:
            add(a, rand_time(d), "OUT", R.uniform(15, 250), "P2P", R.choice(friends), "individual")
    return pay


def make_customer(cohort, label, i):
    is_biz = cohort in ("smallbiz", "pass_through")
    state = R.choice(HOME)
    first, last = R.choice(FIRST), R.choice(LAST)
    if is_biz:
        suffix = {"smallbiz": R.choice(["Grill", "Market", "Wash & Fold", "Auto", "Eats", "Cuts"]), "pass_through": R.choice(["Global Consulting LLC", "Trade Partners LLC", "Ventures LLC"])}[cohort]
        name = f"{last} {suffix}"
    else:
        name = f"{first} {last}"
    if cohort in ("mule", "new_mover"):
        open_date = START + dt.timedelta(days=R.randint(-50, 25))
    elif cohort == "pass_through":
        open_date = START - dt.timedelta(days=R.randint(60, 300))
    else:
        open_date = START - dt.timedelta(days=R.randint(200, 4000))
    n = len(customers) + 1
    c = {"customer_id": f"C{n:05d}", "account_id": f"A{100000 + n}", "name": name, "customer_type": "business" if is_biz else "individual",
         "occupation": R.choice(OCC[cohort]), "state": state, "open_date": open_date.strftime("%Y-%m-%d"),
         "expected_monthly_in": 0, "cohort": cohort, "label": label}
    customers.append(c)
    return c


for cohort, n, label in COHORTS:
    for i in range(n):
        a = make_customer(cohort, label, i)
        od = dt.datetime.strptime(a["open_date"], "%Y-%m-%d")
        active_from = max(0, (od - START).days)

        if cohort == "retail":
            pay = baseline(a)
            a["expected_monthly_in"] = round(pay * 2.2, -2)
            if R.random() < 0.02:  # inheritance, legal settlement, tax refund: legit one-off
                add(a, rand_time(R.randint(5, 85), 9, 15), "IN", R.uniform(15000, 60000), R.choice(["WIRE", "CHECK"]), R.choice(["Estate of a relative", "Settlement administrator", "Law office trust account"]), "business", memo="one-time deposit")

        elif cohort == "seller":
            pay = baseline(a, pay=R.uniform(800, 2200))
            for d in range(DAYS):
                for _ in range(R.choices([0, 1, 2, 3, 4], [0.38, 0.3, 0.18, 0.09, 0.05])[0]):
                    add(a, rand_time(d), "IN", R.uniform(20, 320), "P2P", R.choice(cp_pool), "individual", memo="item sale")
                if R.random() < 0.15:
                    add(a, rand_time(d), "OUT", R.uniform(50, 600), "CARD", R.choice(["ShipFast", "Supply Wholesale", "PackRite"]), "merchant", state=a["state"])
            a["expected_monthly_in"] = round(pay * 2.2 + 4500, -2)

        elif cohort == "smallbiz":
            heavy = R.random() < 0.3
            for d in range(DAYS):
                if d % 7 in (0, 3) or R.random() < 0.15:
                    amt = R.uniform(8000, 9900) if (heavy and R.random() < 0.2) else R.uniform(600, 6500)
                    add(a, rand_time(d, 9, 17), "IN", amt, "CASH", "Cash deposit", "self", state=a["state"], branch=branch(a["state"]))
                add(a, rand_time(d, 1, 3), "IN", R.uniform(300, 2500), "CARD_SETTLEMENT", "Merchant Services", "processor")
                if d % 7 == 4:
                    add(a, rand_time(d), "OUT", R.uniform(2000, 9000), "ACH", R.choice(["Sysco Foods", "Restaurant Depot", "Metro Supply Co", "AutoParts Wholesale"]), "business")
                if d % 14 == 6:
                    add(a, rand_time(d), "OUT", R.uniform(5000, 15000), "ACH", "Gusto Payroll", "business", memo="PAYROLL")
                if d % 30 == 2:
                    add(a, rand_time(d), "OUT", R.uniform(2500, 6000), "ACH", "Commercial Realty LLC", "landlord")
            a["expected_monthly_in"] = 90000 if heavy else 70000

        elif cohort == "crypto_buyer":
            pay = baseline(a, pay=R.uniform(2500, 4500))
            ex = R.choice(EXCHANGES)
            for d in range(DAYS):
                if R.random() < 0.06:
                    add(a, rand_time(d), "OUT", R.uniform(300, pay * 0.9), "ACH", ex, "crypto_exchange")
            a["expected_monthly_in"] = round(pay * 2.2, -2)

        elif cohort == "new_mover":
            pay = R.uniform(2500, 4500)
            d0 = active_from
            add(a, rand_time(d0, 9, 12), "IN", R.uniform(9000, 42000), "ACH", f"{a['name']} (ext. account)", "self", memo="transfer from savings")
            baseline(a, pay=pay)
            a["expected_monthly_in"] = round(pay * 2.2 + 15000, -2)

        elif cohort == "homebuyer":
            pay = baseline(a, pay=R.uniform(3500, 7000))
            d0 = R.randint(10, 75)
            amt = R.uniform(45000, 160000)
            add(a, rand_time(d0, 9, 15), "IN", amt, "WIRE", f"{a['name']} (brokerage)", "self", memo="down payment funds")
            add(a, rand_time(d0 + R.randint(1, 5), 9, 15), "OUT", amt * R.uniform(0.92, 1.0), "WIRE", R.choice(TITLE_COS), "title_company", memo="closing")
            a["expected_monthly_in"] = round(pay * 2.2, -2)

        elif cohort == "traveler":
            pay = baseline(a, pay=R.uniform(2200, 4000))
            for d in range(DAYS):
                if R.random() < 0.05:
                    s = R.choice(STATES)
                    add(a, rand_time(d, 9, 17), "IN", R.uniform(150, 1400), "CASH", "Cash deposit", "self", state=s, branch=branch(s), memo="expense reimbursement")
            a["expected_monthly_in"] = round(pay * 2.2 + 1500, -2)

        elif cohort == "new_crypto":
            # legit: new customer moves savings in, then buys crypto with most of it
            pay = R.uniform(3500, 6000)
            d0 = active_from
            amt = R.uniform(15000, 45000)
            add(a, rand_time(d0, 9, 12), "IN", amt, "ACH", f"{a['name']} (ext. account)", "self", memo="transfer from savings")
            for k in range(R.randint(1, 3)):
                add(a, rand_time(d0 + R.randint(1, 5)), "OUT", amt * R.uniform(0.6, 0.9) / 2, "ACH", R.choice(EXCHANGES), "crypto_exchange")
            baseline(a, pay=pay)
            a["expected_monthly_in"] = round(pay * 2.2, -2)

        elif cohort == "promoter":
            # legit: collects ticket or league fees from many people, then pays the venue by wire
            pay = baseline(a, pay=R.uniform(1800, 3500))
            a["expected_monthly_in"] = round(pay * 2.2 + 3000, -2)
            for _ in range(R.randint(1, 3)):
                d0 = R.randint(0, DAYS - 8)
                tot = 0
                for k in range(R.randint(14, 40)):
                    t = add(a, rand_time(d0 + R.randint(0, 3)), "IN", R.uniform(40, 450), "P2P", R.choice(cp_pool), "individual", memo="tickets")
                    tot += t["amount"] if t else 0
                add(a, rand_time(d0 + R.randint(4, 6), 9, 15), "OUT", tot * R.uniform(0.8, 0.95), "WIRE", R.choice(["Riverside Amphitheater", "Metro Event Center", "Parks & Rec Dept"]), "business", memo="venue deposit")

        elif cohort == "mule":
            baseline(a, pay=R.uniform(400, 900), spend=0.5)
            a["expected_monthly_in"] = 1500 if R.random() < 0.6 else R.choice([8000, 12000, 15000])  # some lie at onboarding
            slow = R.random() < 0.3   # careful mule: few senders, pays one person by P2P
            exit_kind = "p2p" if slow else R.choice(["crypto", "crypto", "wire", "p2p"])
            beneficiary = R.choice(cp_pool)
            for _ in range(R.randint(2, 4)):
                d0 = R.randint(max(active_from, 2), DAYS - 6)
                total = 0
                for k in range(R.randint(3, 6) if slow else R.randint(5, 14)):
                    t = add(a, rand_time(d0 + R.randint(0, 2)), "IN", R.uniform(350, 3800), R.choice(["P2P", "P2P", "ACH"]), R.choice(cp_pool), "individual")
                    total += t["amount"] if t else 0
                out_day = d0 + R.randint(2, 4)
                left = total * R.uniform(0.85, 0.97)
                pieces = R.randint(1, 3)
                for p in range(pieces):
                    amt = left / pieces
                    if exit_kind == "crypto":
                        add(a, rand_time(out_day), "OUT", amt, "ACH", R.choice(EXCHANGES), "crypto_exchange")
                    elif exit_kind == "wire":
                        cc, nm = R.choice(FOREIGN)
                        add(a, rand_time(out_day, 9, 15), "OUT", amt, "WIRE", nm, "business", country=cc)
                    else:
                        add(a, rand_time(out_day), "OUT", amt, "P2P", beneficiary, "individual")

        elif cohort == "structuring":
            pay = baseline(a, pay=R.uniform(1500, 3000))
            a["expected_monthly_in"] = round(pay * 2.2, -2) if R.random() < 0.6 else 30000  # some claim a cash business
            careful = R.random() < 0.3  # spreads deposits so no 7-day window has 3
            for _ in range(R.randint(2, 4)):
                d0 = R.randint(0, DAYS - 16)
                for k in range(R.randint(3, 5)):
                    if careful:
                        add(a, rand_time(d0 + 4 * k + R.randint(0, 1), 9, 17), "IN", R.uniform(7600, 9950), "CASH", "Cash deposit", "self", state=a["state"], branch=branch(a["state"]))
                        continue
                    s = a["state"]
                    add(a, rand_time(d0 + R.randint(0, 6), 9, 17), "IN", R.uniform(7600, 9950), "CASH", "Cash deposit", "self", state=s, branch=branch(s))
                if R.random() < 0.6:
                    cc, nm = R.choice(FOREIGN)
                    add(a, rand_time(d0 + R.randint(7, 10), 9, 15), "OUT", R.uniform(15000, 30000), "WIRE", nm, "business", country=cc)

        elif cohort == "funnel":
            baseline(a, pay=R.uniform(600, 1500), spend=0.6)
            a["expected_monthly_in"] = 2500
            for _ in range(R.randint(2, 4)):
                d0 = R.randint(0, DAYS - 12)
                total = 0
                for s in R.sample([x for x in STATES if x != a["state"]], R.randint(3, 6)):
                    for k in range(R.randint(1, 2)):
                        t = add(a, rand_time(d0 + R.randint(0, 6), 9, 17), "IN", R.uniform(900, 6800), "CASH", "Cash deposit", "self", state=s, branch=branch(s))
                        total += t["amount"] if t else 0
                od2 = d0 + R.randint(6, 9)
                if R.random() < 0.5:
                    for k in range(R.randint(2, 4)):
                        add(a, rand_time(od2, 9, 17), "OUT", total * 0.9 / 3, "CASH_WITHDRAWAL", "Cash withdrawal", "self", state=a["state"], branch=branch(a["state"]))
                else:
                    cc, nm = R.choice(FOREIGN)
                    add(a, rand_time(od2, 9, 15), "OUT", total * R.uniform(0.85, 0.95), "WIRE", nm, "business", country=cc)

        elif cohort == "pass_through":
            a["expected_monthly_in"] = R.choice([40000, 150000, 250000])
            for d in range(DAYS):
                if R.random() < 0.05:
                    add(a, rand_time(d), "OUT", R.uniform(20, 400), "CARD", R.choice(["Office Depot", "CloudHost", "Telecom Co"]), "merchant", state=a["state"])
            for _ in range(R.randint(3, 7)):
                d0 = R.randint(0, DAYS - 5)
                cc, nm = R.choice(FOREIGN)
                amt = R.uniform(18000, 240000)
                add(a, rand_time(d0, 9, 15), "IN", amt, "WIRE", nm, "business", country=cc, memo="consulting services")
                cc2, nm2 = R.choice([f for f in FOREIGN if f[1] != nm])
                add(a, rand_time(d0 + R.randint(1, 3), 9, 15), "OUT", amt * R.uniform(0.95, 0.995), "WIRE", nm2, "business", country=cc2, memo="invoice payment")

txns.sort(key=lambda t: (t["account_id"], t["ts"]))
with open(os.path.join(OUT, "customers.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(customers[0].keys())); w.writeheader(); w.writerows(customers)
with open(os.path.join(OUT, "transactions.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(txns[0].keys())); w.writeheader(); w.writerows(txns)
bad = sum(1 for c in customers if c["label"] != "none")
print(f"{len(customers)} customers ({bad} planted suspicious), {len(txns)} transactions, {START.date()} to {(END - dt.timedelta(days=1)).date()}")
