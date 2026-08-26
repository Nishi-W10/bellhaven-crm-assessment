import csv
from collections import defaultdict


FILE = "data/processed/match_candidates.csv"
BELLHAVEN_PARENT_ID = "0015QAPLGS3FVYEEEM"


with open(FILE, encoding="utf-8") as f:
    rows = list(csv.DictReader(f))


groups = defaultdict(list)

for row in rows:
    groups[row["website_name"]].append(row)


print("\n=== UNCERTAIN MATCHES: MEDIUM / LOW ===\n")

for website_name, candidates in groups.items():

    candidates.sort(key=lambda x: int(x["candidate_rank"]))
    best = candidates[0]

    if best["match_strength"] == "HIGH":
        continue

    print("=" * 100)
    print(
        f"WEBSITE: {website_name} | "
        f"{best['website_address']}, "
        f"{best['website_city']}, "
        f"{best['website_state']} "
        f"{best['website_zip']}"
    )

    for candidate in candidates:

        print(
            f"\n  Candidate {candidate['candidate_rank']}"
            f" | Score {candidate['score']}"
            f" | {candidate['match_strength']}"
        )

        print(
            f"  CRM: {candidate['crm_name']}"
        )

        print(
            f"  Address: {candidate['crm_address']}, "
            f"{candidate['crm_city']}, "
            f"{candidate['crm_state']} "
            f"{candidate['crm_zip']}"
        )

        print(
            f"  Parent: {candidate['crm_parent_name']}"
        )

        print(
            f"  Revenue: {candidate['lifetime_revenue']}"
            f" | Outstanding AR: {candidate['outstanding_ar']}"
        )


print("\n\n=== HIGH MATCHES WITH NON-BELLHAVEN PARENT ===\n")

for website_name, candidates in groups.items():

    best = sorted(
        candidates,
        key=lambda x: int(x["candidate_rank"])
    )[0]

    if (
        best["match_strength"] == "HIGH"
        and best["crm_parent_id"] != BELLHAVEN_PARENT_ID
    ):

        print("=" * 100)

        print(
            f"{website_name}"
            f" => {best['crm_name']}"
        )

        print(
            f"Parent: {best['crm_parent_name']}"
        )

        print(
            f"Revenue: {best['lifetime_revenue']}"
            f" | Outstanding AR: {best['outstanding_ar']}"
        )

        print(
            f"Website address: "
            f"{best['website_address']}, "
            f"{best['website_city']}, "
            f"{best['website_state']} "
            f"{best['website_zip']}"
        )

        print(
            f"CRM address: "
            f"{best['crm_address']}, "
            f"{best['crm_city']}, "
            f"{best['crm_state']} "
            f"{best['crm_zip']}"
        )