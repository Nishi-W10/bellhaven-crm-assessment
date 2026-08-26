import csv
import re
from rapidfuzz import fuzz

BELLHAVEN_PARENT_ID = "0015QAPLGS3FVYEEEM"

WEBSITE_FILE = "data/raw/website_locations.csv"
CRM_FILE = "data/raw/crm_accounts.csv"
OUTPUT_FILE = "data/processed/match_candidates.csv"


def normalize_text(value):
    """Normalize names and addresses for matching."""
    if not value:
        return ""

    value = value.lower().strip()

    replacements = {
        "northwest": "nw",
        "northeast": "ne",
        "southwest": "sw",
        "southeast": "se",
        "north": "n",
        "south": "s",
        "east": "e",
        "west": "w",
        "street": "st",
        "road": "rd",
        "avenue": "ave",
        "boulevard": "blvd",
        "drive": "dr",
        "lane": "ln",
        "court": "ct",
        "highway": "hwy",
        "parkway": "pkwy",
    }

    for old, new in replacements.items():
        value = re.sub(rf"\b{old}\b", new, value)

    value = re.sub(r"[^a-z0-9]", "", value)

    return value


def load_csv(path):
    with open(path, encoding="utf-8") as file:
        return list(csv.DictReader(file))


def score_candidate(website, crm):
    website_name = normalize_text(website["name"])
    crm_name = normalize_text(crm["name"])

    website_address = normalize_text(website["address"])
    crm_address = normalize_text(crm["billing_street"])

    name_score = fuzz.ratio(website_name, crm_name)

    address_exact = (
        website_address != ""
        and website_address == crm_address
    )

    city_exact = normalize_text(website["city"]) == normalize_text(
        crm["billing_city"]
    )

    state_exact = website["state"].strip().upper() == (
        crm["billing_state"].strip().upper()
    )

    zip_exact = website["zip"].strip() == crm["billing_zip"].strip()

    # Address is intentionally the strongest signal.
    score = 0

    if address_exact:
        score += 55

    if zip_exact:
        score += 20

    if city_exact:
        score += 10

    if state_exact:
        score += 5

    score += name_score * 0.10

    return {
        "score": round(score, 2),
        "name_score": round(name_score, 2),
        "address_exact": address_exact,
        "city_exact": city_exact,
        "state_exact": state_exact,
        "zip_exact": zip_exact,
    }


def get_match_strength(result):
    if (
        result["address_exact"]
        and result["zip_exact"]
        and result["score"] >= 90
    ):
        return "HIGH"

    if result["score"] >= 70:
        return "MEDIUM"

    return "LOW"


def main():
    website_rows = load_csv(WEBSITE_FILE)
    crm_rows = load_csv(CRM_FILE)

    output = []

    for website in website_rows:
        candidates = []

        for crm in crm_rows:
            result = score_candidate(website, crm)

            candidates.append(
                {
                    "crm": crm,
                    **result,
                }
            )

        candidates.sort(
            key=lambda x: (
                x["score"],

                # If two accounts represent the same facility,
                # prefer the current Bellhaven-owned account.
                x["crm"]["parent_id"]
                == BELLHAVEN_PARENT_ID,

                # Prefer an active record.
                x["crm"]["status"]
                == "Active",

                # Prefer a non-duplicate record.
                not bool(
                    x["crm"].get(
                        "duplicate_of_account"
                    )
                ),
            ),
            reverse=True,
        )

        # Keep top 3 candidates for manual review.
        for rank, candidate in enumerate(candidates[:3], start=1):
            crm = candidate["crm"]

            output.append(
                {
                    "website_name": website["name"],
                    "website_address": website["address"],
                    "website_city": website["city"],
                    "website_state": website["state"],
                    "website_zip": website["zip"],

                    "candidate_rank": rank,

                    "crm_account_id": crm["account_id"],
                    "crm_name": crm["name"],
                    "crm_parent_id": crm["parent_id"],
                    "crm_parent_name": crm["parent_name"],
                    "crm_address": crm["billing_street"],
                    "crm_city": crm["billing_city"],
                    "crm_state": crm["billing_state"],
                    "crm_zip": crm["billing_zip"],
                    "crm_status": crm["status"],

                    "lifetime_revenue": crm["lifetime_revenue"],
                    "outstanding_ar": crm["outstanding_ar"],

                    "score": candidate["score"],
                    "match_strength": get_match_strength(candidate),
                    "name_score": candidate["name_score"],
                    "address_exact": candidate["address_exact"],
                    "city_exact": candidate["city_exact"],
                    "state_exact": candidate["state_exact"],
                    "zip_exact": candidate["zip_exact"],
                }
            )

    fieldnames = list(output[0].keys())

    with open(
        OUTPUT_FILE,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()
        writer.writerows(output)

    top_matches = [
        row for row in output
        if row["candidate_rank"] == 1
    ]

    high = sum(
        1 for row in top_matches
        if row["match_strength"] == "HIGH"
    )

    medium = sum(
        1 for row in top_matches
        if row["match_strength"] == "MEDIUM"
    )

    low = sum(
        1 for row in top_matches
        if row["match_strength"] == "LOW"
    )

    exact_address = sum(
        1 for row in top_matches
        if row["address_exact"]
    )

    print("=== INITIAL MATCHING RESULTS ===")
    print(f"Website facilities: {len(website_rows)}")
    print(f"CRM accounts searched: {len(crm_rows)}")
    print(f"Exact-address top matches: {exact_address}")
    print(f"HIGH confidence: {high}")
    print(f"MEDIUM confidence: {medium}")
    print(f"LOW confidence: {low}")
    print()
    print(f"Saved: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()