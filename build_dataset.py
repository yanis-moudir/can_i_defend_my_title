import os, json, time
import pandas as pd

BASE = "https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main"

def load(filename):
    if os.path.exists(filename):
        return pd.read_csv(filename)
    df = pd.read_csv(f"{BASE}/{filename}")
    df.to_csv(filename, index=False)
    return df

# ---------------- helpers ----------------
def era_of(year):
    if year <= 2010:   return "2006-2010"
    elif year <= 2015: return "2011-2015"
    elif year <= 2020: return "2016-2020"
    else:              return "2021-present"

DIVISIONS = ["Women's Strawweight","Women's Flyweight","Women's Bantamweight",
             "Women's Featherweight","Light Heavyweight","Heavyweight","Welterweight",
             "Middleweight","Lightweight","Featherweight","Bantamweight","Flyweight",
             "Strawweight","Catch Weight"]
def division_of(weightclass):
    wc = str(weightclass).lower()
    for d in DIVISIONS:
        if d.lower() in wc:
            return d.lower()
    return wc

def x_of_y(series):
    parts = series.str.split(" of ", expand=True)
    landed    = pd.to_numeric(parts[0], errors="coerce")
    attempted = pd.to_numeric(parts[1], errors="coerce")
    return int(landed.sum()), int(attempted.sum())

def bout_minutes(round_num, time_str):
    try:
        m, s = str(time_str).split(":")
        return (int(round_num) - 1) * 5 + int(m) + int(s) / 60
    except Exception:
        return None

def slug(name):
    return name.lower().replace(" ", "_").replace("'", "").replace(".", "").replace("-", "_")

def get_reach(name):
    row = tott.loc[tott["FIGHTER"] == name, "REACH"]
    if row.empty: return None
    val = row.values[0]
    if pd.isna(val) or str(val) in ("--", ""): return None
    try:    return int(str(val).replace('"', "").strip())
    except: return None

# ---------------- load ----------------
stats   = load("ufc_fight_stats.csv")
results = load("ufc_fight_results.csv")
tott    = load("ufc_fighter_tott.csv")
events  = load("ufc_event_details.csv")
for d in (stats, results, events):
    d["EVENT"] = d["EVENT"].str.strip()

# league per-round averages, used to regress small-sample rate stats toward the mean
PRIOR_KD  = stats["KD"].sum() / len(stats)
PRIOR_SUB = stats["SUB.ATT"].sum() / len(stats)
# leg priors (parse "X of Y" league-wide)
_lp = stats["LEG"].str.split(" of ", expand=True)
_ll = pd.to_numeric(_lp[0], errors="coerce")
_la = pd.to_numeric(_lp[1], errors="coerce")
PRIOR_LEG_ACC  = float(_ll.sum() / _la.sum())                # league leg-strike accuracy
PRIOR_LEG_RATE = float(_ll.sum() / len(stats))               # league leg lands per round
C_SHRINK  = 8     # pseudo-rounds of "prior" mixed in; tames freak small-sample rates
C_LEG_ACC = 30    # leg-accuracy shrinkage = same as the eligibility gate

# ---------------- per-bout metadata ----------------
meta = pd.merge(results, events, on="EVENT")
meta["DATE_P"] = pd.to_datetime(meta["DATE"], errors="coerce")
meta = meta.dropna(subset=["DATE_P"])
meta["YEAR"] = meta["DATE_P"].dt.year.astype(int)
meta = meta[meta["YEAR"] >= 2006]                      # stats reliable from 2006 on
meta["ERA"]      = meta["YEAR"].apply(era_of)
meta["DIVISION"] = meta["WEIGHTCLASS"].apply(division_of)
meta["MINUTES"]  = meta.apply(lambda r: bout_minutes(r["ROUND"], r["TIME"]), axis=1)
# exact fighter names (split the bout) so substring names can't cause mismatches
namep = meta["BOUT"].str.split(" vs. ", expand=True)
meta["F1"] = namep[0].str.strip()
meta["F2"] = namep[1].str.strip()

# ---------------- build cards for one fighter ----------------
def build_cards(name):
    cards = []
    fm = meta[(meta["F1"] == name) | (meta["F2"] == name)]
    for (era, division), group in fm.groupby(["ERA", "DIVISION"]):
        if len(group) < 4:
            continue
        group_bouts   = group["BOUT"].unique()
        total_minutes = group["MINUTES"].sum()
        if not total_minutes or total_minutes <= 0:
            continue

        sub = stats[stats["BOUT"].isin(group_bouts)]
        his = sub[sub["FIGHTER"] == name]
        opp = sub[sub["FIGHTER"] != name]
        rounds = len(his)
        if rounds == 0:
            continue

        s_landed, s_thrown        = x_of_y(his["SIG.STR."])
        td_landed, td_att         = x_of_y(his["TD"])
        opp_landed, _             = x_of_y(opp["SIG.STR."])
        opp_td_landed, opp_td_att = x_of_y(opp["TD"])
        if s_thrown == 0:
            continue

        wins = losses = 0
        won_title = False
        for _, row in group.iterrows():
            idx = 0 if row["F1"] == name else 1
            res = str(row["OUTCOME"]).split("/")[idx].strip() if "/" in str(row["OUTCOME"]) else ""
            is_title = "title" in str(row["WEIGHTCLASS"]).lower()
            if res == "W":
                wins += 1
                if is_title:                       # a title bout you WON = you held the belt
                    won_title = True
            elif res == "L":
                losses += 1

        # leg-kick specialist score: shrunken accuracy * shrunken landed-per-round volume
        leg_landed, leg_att = x_of_y(his["LEG"])
        if leg_att >= 30:
            leg_acc_adj  = (leg_landed + C_LEG_ACC * PRIOR_LEG_ACC) / (leg_att + C_LEG_ACC)
            leg_rate_adj = (leg_landed + C_SHRINK  * PRIOR_LEG_RATE) / (rounds  + C_SHRINK)
            leg_kicks    = leg_acc_adj * leg_rate_adj            # stored value; bigger = better at both
        else:
            leg_kicks = None

        cards.append({
            "fighter_id": slug(name),
            "name": name,
            "era": era,
            "division": division,
            "champion": won_title,
            "fights": len(group),
            "record": {"wins": wins, "losses": losses, "draws": 0},
            "stats": {
                "strike_accuracy":          round(s_landed / s_thrown, 3),
                "strikes_absorbed_per_min": round(opp_landed / total_minutes, 3),
                "td_defence":               (round(1 - opp_td_landed / opp_td_att, 3) if opp_td_att >= 10 else None),
                "td_accuracy":              (round(td_landed / td_att, 3) if td_att >= 10 else None),
                "knockdown_ratio":          round((his["KD"].sum() + C_SHRINK*PRIOR_KD) / (rounds + C_SHRINK), 3),
                "leg_kicks":                (round(leg_kicks, 4) if leg_kicks is not None else None),
                "sub_threat":               round((his["SUB.ATT"].sum() + C_SHRINK*PRIOR_SUB) / (rounds + C_SHRINK), 3),
                "reach_inches":             get_reach(name),
            },
            "samples": {
                "td_attempts_for": td_att, "td_attempts_against": opp_td_att,
                "sig_strikes_thrown": s_thrown, "minutes": round(float(total_minutes), 1),
            },
        })
    return cards

# ---------------- build EVERYONE ----------------
t0 = time.time()
names = sorted(stats["FIGHTER"].dropna().unique())
all_cards, skipped = [], 0
for name in names:
    try:
        all_cards.extend(build_cards(name))
    except Exception:
        skipped += 1

with open("fighters.json", "w") as f:
    json.dump(all_cards, f, indent=2)

fighters = len({c["fighter_id"] for c in all_cards})
print(f"fighters with >=1 card: {fighters}")
print(f"total cards: {len(all_cards)}")
print(f"skipped (errors): {skipped}")
print(f"time: {time.time()-t0:.1f}s")
print("\nby era:")
print(pd.Series([c['era'] for c in all_cards]).value_counts().to_string())