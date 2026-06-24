import pandas as pd
BASE = "https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main"

results = pd.read_csv(f"{BASE}/ufc_fight_results.csv")
events  = pd.read_csv(f"{BASE}/ufc_event_details.csv")

# ----- YOU WRITE THIS PART (copy the shapes from the example) -----
# 1) strip whitespace from the "EVENT" column in results
results["EVENT"]=results["EVENT"].str.strip()
# 2) strip whitespace from the "EVENT" column in events
events["EVENT"]=events["EVENT"].str.strip()
# 3) merge events onto results, matching on "EVENT"
results=pd.merge(results,events,on="EVENT" )
# ------------------------------------------------------------------


prates = results[results["BOUT"].str.contains("Carlos Prates", na=False)]
print(prates[["BOUT", "DATE"]])   # should print his fights, each with a date
prates = prates.copy()                                  # avoids a harmless pink warning
prates["YEAR"] = pd.to_datetime(prates["DATE"]).dt.year   # fill the column name
def era(year):
    if year <= 2010:
        return "2006-2010"
    elif year <= 2015 and year>2010:
        return "2011-2015"
    elif year <= 2020 and year >2015:
        return "2016-2020"
    else:
        return "2021-present"

prates["ERA"]=prates["YEAR"].apply(era)
print(prates[["BOUT","ERA"]])