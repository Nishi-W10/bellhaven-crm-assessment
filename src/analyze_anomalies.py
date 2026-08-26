import csv
import re
from collections import defaultdict


WEBSITE_FILE = "data/raw/website_locations.csv"
CRM_FILE = "data/raw/crm_accounts.csv"
MATCH_FILE = "data/processed/match_candidates.csv"

BELLHAVEN_PARENT_ID = "0015QAPLGS3FVYEEEM"


def load_csv(path):
    with open(path, encoding="utf-8") as file:
        return list(csv.DictReader(file))


def normalize_text(value):
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

    return re.sub(r"[^a-z0-9]", "", value)


def money(value):
    try:
        return float(value or 0)
    except ValueError:
        return 0


website = load_csv(WEBSITE_FILE)
crm = load_csv(CRM_FILE)
matches = load_csv(MATCH_FILE)

top_matches = [
    row for row in matches
    if row["candidate_rank"] == "1"
]


def credible_match(row):
    """
    Determine whether Candidate #1 is credible enough
    to represent the same physical facility.
    """

    if row["match_strength"] == "HIGH":
        return True

    same_name = (
        normalize_text(row["website_name"])
        == normalize_text(row["crm_name"])
    )

    same_city = (
        normalize_text(row["website_city"])
        == normalize_text(row["crm_city"])
    )

    same_state = (
        row["website_state"].upper()
        == row["crm_state"].upper()
    )

    # Captures cases such as Ashtabula and Portsmouth.
    if same_name and same_city and same_state:
        return True

    return False


credible = [
    row for row in top_matches
    if credible_match(row)
]

unresolved = [
    row for row in top_matches
    if not credible_match(row)
]


print("\n=== 1. UNRESOLVED WEBSITE FACILITIES ===\n")

for row in unresolved:

    same_location = (
        row["website_city"] == row["crm_city"]
        and row["website_state"] == row["crm_state"]
        and row["website_zip"] == row["crm_zip"]
    )

    if same_location:
        suggested = "NEEDS_REVIEW"
    else:
        suggested = "LIKELY CREATE_NEW"

    print(
        f"{row['website_name']}\n"
        f"  Best CRM candidate: {row['crm_name']}\n"
        f"  Score: {row['score']}\n"
        f"  Suggested: {suggested}\n"
    )


print("\n=== 2. WRONG PARENT / CHOW CHECK ===\n")

for row in credible:

    if row["crm_parent_id"] != BELLHAVEN_PARENT_ID:

        revenue = money(row["lifetime_revenue"])
        ar = money(row["outstanding_ar"])

        if revenue > 0 and ar > 0:
            action = "CHOW_REQUIRED"
        else:
            action = "REPARENT"

        print(
            f"{row['website_name']}\n"
            f"  CRM: {row['crm_name']}\n"
            f"  Current parent: "
            f"{row['crm_parent_name'] or 'NONE'}\n"
            f"  Revenue: ${revenue:,.2f}\n"
            f"  Outstanding AR: ${ar:,.2f}\n"
            f"  Action: {action}\n"
        )


print("\n=== 3. POSSIBLE NAME UPDATES ===\n")

for row in credible:

    if (
        normalize_text(row["website_name"])
        != normalize_text(row["crm_name"])
    ):

        print(
            f"{row['crm_name']}"
            f"  -->  {row['website_name']}"
        )


print("\n=== 4. ADDRESS / ZIP DIFFERENCES ===\n")

for row in credible:

    website_address = normalize_text(
        row["website_address"]
    )

    crm_address = normalize_text(
        row["crm_address"]
    )

    if (
        website_address != crm_address
        or row["website_zip"] != row["crm_zip"]
    ):

        print(
            f"{row['website_name']}\n"
            f"  Website: {row['website_address']}, "
            f"{row['website_zip']}\n"
            f"  CRM:     {row['crm_address']}, "
            f"{row['crm_zip']}\n"
        )


# IDs representing credible website-to-CRM matches
matched_ids = {
    row["crm_account_id"]
    for row in credible
}


print("\n=== 5. BELLHAVEN CRM ACCOUNTS NOT MATCHED TO WEBSITE ===\n")

bellhaven_children = [
    row for row in crm
    if row["parent_id"] == BELLHAVEN_PARENT_ID
]

unmatched_bellhaven = [
    row for row in bellhaven_children
    if row["account_id"] not in matched_ids
]

for row in unmatched_bellhaven:

    print(
        f"{row['account_id']} | "
        f"{row['name']} | "
        f"{row['billing_city']}, "
        f"{row['billing_state']} | "
        f"Status: {row['status']} | "
        f"Revenue: {row['lifetime_revenue']} | "
        f"AR: {row['outstanding_ar']}"
    )


print("\n=== 6. POSSIBLE DUPLICATE BELLHAVEN ACCOUNTS ===\n")

groups = defaultdict(list)

for row in bellhaven_children:

    key = (
        normalize_text(row["billing_street"]),
        normalize_text(row["billing_city"]),
        row["billing_state"].upper(),
        row["billing_zip"],
    )

    if key[0]:
        groups[key].append(row)


duplicate_groups = [
    group
    for group in groups.values()
    if len(group) > 1
]

for group in duplicate_groups:

    print("-" * 90)

    for row in group:

        print(
            f"{row['account_id']} | "
            f"{row['name']} | "
            f"{row['billing_street']} | "
            f"Revenue: {row['lifetime_revenue']} | "
            f"AR: {row['outstanding_ar']} | "
            f"Status: {row['status']} | "
            f"Updated: {row['updated_at']}"
        )


print("\n=== SUMMARY ===")
print(f"Website facilities: {len(website)}")
print(f"Credible CRM matches: {len(credible)}")
print(f"Unresolved website facilities: {len(unresolved)}")
print(f"Current Bellhaven CRM children: {len(bellhaven_children)}")
print(
    f"Bellhaven children not represented by a "
    f"credible website match: {len(unmatched_bellhaven)}"
)
print(f"Possible duplicate groups: {len(duplicate_groups)}")