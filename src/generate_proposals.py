import csv
import hashlib
import json
import re
from collections import Counter, defaultdict


WEBSITE_FILE = "data/raw/website_locations.csv"
CRM_FILE = "data/raw/crm_accounts.csv"
MATCH_FILE = "data/processed/match_candidates.csv"

PROPOSALS_FILE = "data/processed/proposals.csv"
SUMMARY_FILE = "data/processed/reconciliation_summary.csv"

BELLHAVEN_PARENT_ID = "0015QAPLGS3FVYEEEM"
BELLHAVEN_PARENT_NAME = "Bellhaven Senior Living (Parent Account)"


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
    except (ValueError, TypeError):
        return 0.0


def make_proposal_id(action, website_name, account_id):
    raw = f"{action}|{website_name}|{account_id}"

    return hashlib.sha256(
        raw.encode("utf-8")
    ).hexdigest()[:16]


def credible_match(row):
    """
    HIGH matches are credible.

    Also accept same-name + same-city + same-state matches
    such as Ashtabula and Portsmouth, where one address
    field is stale.
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

    return same_name and same_city and same_state


def add_proposal(
    proposals,
    action,
    website_name="",
    website_source_url="",
    target_account_id="",
    current_values=None,
    proposed_values=None,
    evidence="",
    confidence="HIGH",
    lifetime_revenue="",
    outstanding_ar="",
    write_strategy="PATCH",
):

    proposal_id = make_proposal_id(
        action,
        website_name,
        target_account_id,
    )

    proposals.append(
        {
            "proposal_id": proposal_id,
            "action": action,
            "website_name": website_name,
            "website_source_url": website_source_url,
            "target_account_id": target_account_id,
            "current_values": json.dumps(
                current_values or {},
                ensure_ascii=False,
            ),
            "proposed_values": json.dumps(
                proposed_values or {},
                ensure_ascii=False,
            ),
            "evidence": evidence,
            "confidence": confidence,
            "lifetime_revenue": lifetime_revenue,
            "outstanding_ar": outstanding_ar,
            "write_strategy": write_strategy,
            "review_status": "PENDING",
        }
    )


website = load_csv(WEBSITE_FILE)
crm = load_csv(CRM_FILE)
matches = load_csv(MATCH_FILE)

crm_by_id = {
    row["account_id"]: row
    for row in crm
}

website_by_name = {
    row["name"]: row
    for row in website
}

top_matches = [
    row
    for row in matches
    if row["candidate_rank"] == "1"
]

proposals = []
summary = []
credible_rows = []


# ============================================================
# 1. WEBSITE -> CRM RECONCILIATION
# ============================================================

for match in top_matches:

    website_row = website_by_name[
        match["website_name"]
    ]

    crm_row = crm_by_id[
        match["crm_account_id"]
    ]

    is_credible = credible_match(match)

    # --------------------------------------------------------
    # UNRESOLVED WEBSITE FACILITY
    # --------------------------------------------------------

    if not is_credible:

        same_city = (
            normalize_text(match["website_city"])
            == normalize_text(match["crm_city"])
        )

        same_state = (
            match["website_state"].upper()
            == match["crm_state"].upper()
        )

        same_zip = (
            match["website_zip"]
            == match["crm_zip"]
        )

        # Union Square type situation.
        # Similar geographic evidence exists, but we do not
        # have enough evidence to overwrite the CRM.
        if same_city and same_state and same_zip:

            # Already handled in a previous review.
            if crm_row["status"] == "Needs Review":

                action = "NO_ACTION"

                summary.append(
                    {
                        "website_name": website_row["name"],
                        "crm_account_id": crm_row["account_id"],
                        "crm_name": crm_row["name"],
                        "classification": action,
                        "match_score": match["score"],
                    }
                )

                continue

            action = "MARK_NEEDS_REVIEW"

            add_proposal(
                proposals,
                action=action,
                website_name=website_row["name"],
                website_source_url=website_row["source_url"],
                target_account_id=crm_row["account_id"],
                current_values={
                    "name": crm_row["name"],
                    "parent_id": crm_row["parent_id"],
                    "billing_street": crm_row["billing_street"],
                    "status": crm_row["status"],
                },
                proposed_values={
                    "status": "Needs Review",
                    "note": (
                        "Possible match to current Bellhaven "
                        f"website facility '{website_row['name']}'. "
                        "Name/location evidence exists but street "
                        "address differs. Manual ownership review "
                        "required."
                    ),
                },
                evidence=(
                    f"Website: {website_row['name']}, "
                    f"{website_row['address']}, "
                    f"{website_row['city']}, "
                    f"{website_row['state']} "
                    f"{website_row['zip']}. "
                    f"CRM candidate: {crm_row['name']}, "
                    f"{crm_row['billing_street']}. "
                    "Same city/state/ZIP but different street."
                ),
                confidence="LOW",
                lifetime_revenue=crm_row["lifetime_revenue"],
                outstanding_ar=crm_row["outstanding_ar"],
            )

        else:

            action = "CREATE_NEW"

            add_proposal(
                proposals,
                action=action,
                website_name=website_row["name"],
                website_source_url=website_row[
                    "source_url"
                ],
                current_values={},
                proposed_values={
                    "name": website_row["name"],
                    "parent_id": BELLHAVEN_PARENT_ID,
                    "billing_street": website_row[
                        "address"
                    ],
                    "billing_city": website_row["city"],
                    "billing_state": website_row[
                        "state"
                    ],
                    "billing_zip": website_row["zip"],
                    "status": "Active",
                },
                evidence=(
                    "No credible existing CRM account found. "
                    f"Best candidate score was "
                    f"{match['score']}."
                ),
                confidence="HIGH",
                lifetime_revenue="0",
                outstanding_ar="0",
                write_strategy="POST",
            )

        summary.append(
            {
                "website_name": website_row["name"],
                "crm_account_id": crm_row[
                    "account_id"
                ],
                "crm_name": crm_row["name"],
                "classification": action,
                "match_score": match["score"],
            }
        )

        continue

    credible_rows.append(match)

    # --------------------------------------------------------
    # CREDIBLE MATCH
    # --------------------------------------------------------

    name_diff = (
        normalize_text(website_row["name"])
        != normalize_text(crm_row["name"])
    )

    address_diff = (
        normalize_text(website_row["address"])
        != normalize_text(
            crm_row["billing_street"]
        )
    )

    zip_diff = (
        website_row["zip"]
        != crm_row["billing_zip"]
    )

    wrong_parent = (
        crm_row["parent_id"]
        != BELLHAVEN_PARENT_ID
    )

    chow_target_id = crm_row.get(
        "chow_current_account",
        ""
    )

    chow_target = crm_by_id.get(
        chow_target_id
    )

    chow_already_handled = (
        chow_target is not None
        and chow_target["parent_id"]
        == BELLHAVEN_PARENT_ID
    )

    revenue = money(
        crm_row["lifetime_revenue"]
    )

    ar = money(
        crm_row["outstanding_ar"]
    )

    proposed = {}
    current = {}

    # --------------------------------------------------------
    # CHOW
    # --------------------------------------------------------

    if (
        wrong_parent
        and revenue > 0
        and ar > 0
        and chow_already_handled
    ):
        action = "NO_ACTION"

    elif wrong_parent and revenue > 0 and ar > 0:

        action = "CHOW_REQUIRED"

        current = {
            "account_id": crm_row["account_id"],
            "name": crm_row["name"],
            "parent_id": crm_row["parent_id"],
            "parent_name": crm_row["parent_name"],
            "lifetime_revenue": revenue,
            "outstanding_ar": ar,
        }

        proposed = {
            "create_new_account": {
                "name": website_row["name"],
                "parent_id": BELLHAVEN_PARENT_ID,
                "billing_street": website_row[
                    "address"
                ],
                "billing_city": website_row["city"],
                "billing_state": website_row[
                    "state"
                ],
                "billing_zip": website_row["zip"],
                "status": "Active",
            },
            "old_account_update": {
                "chow_current_account":
                    "<NEW_ACCOUNT_ID>"
            },
        }

        add_proposal(
            proposals,
            action=action,
            website_name=website_row["name"],
            website_source_url=website_row[
                "source_url"
            ],
            target_account_id=crm_row[
                "account_id"
            ],
            current_values=current,
            proposed_values=proposed,
            evidence=(
                "Facility matches current website but belongs "
                f"to {crm_row['parent_name']}. "
                f"Lifetime revenue=${revenue:,.2f} and "
                f"outstanding AR=${ar:,.2f}. "
                "SOP requires preserving old account, creating "
                "a new Bellhaven account, and linking the old "
                "account through chow_current_account."
            ),
            confidence="HIGH",
            lifetime_revenue=revenue,
            outstanding_ar=ar,
            write_strategy="POST+PATCH",
        )

    # --------------------------------------------------------
    # NORMAL REPARENT
    # --------------------------------------------------------

    elif wrong_parent:

        if name_diff:
            action = "UPDATE_NAME_AND_REPARENT"

            current = {
                "name": crm_row["name"],
                "parent_id": crm_row["parent_id"],
            }

            proposed = {
                "name": website_row["name"],
                "parent_id": BELLHAVEN_PARENT_ID,
            }

        else:
            action = "REPARENT"

            current = {
                "parent_id": crm_row["parent_id"],
                "parent_name": crm_row["parent_name"],
            }

            proposed = {
                "parent_id": BELLHAVEN_PARENT_ID,
            }

        add_proposal(
            proposals,
            action=action,
            website_name=website_row["name"],
            website_source_url=website_row[
                "source_url"
            ],
            target_account_id=crm_row[
                "account_id"
            ],
            current_values=current,
            proposed_values=proposed,
            evidence=(
                "Website and CRM represent the same physical "
                "facility, but CRM ownership does not point to "
                "Bellhaven. Outstanding AR does not trigger "
                "the CHOW preservation rule."
            ),
            confidence="HIGH",
            lifetime_revenue=revenue,
            outstanding_ar=ar,
        )

    # --------------------------------------------------------
    # NAME UPDATE
    # --------------------------------------------------------

    elif name_diff:

        action = "UPDATE_NAME"

        add_proposal(
            proposals,
            action=action,
            website_name=website_row["name"],
            website_source_url=website_row[
                "source_url"
            ],
            target_account_id=crm_row[
                "account_id"
            ],
            current_values={
                "name": crm_row["name"],
            },
            proposed_values={
                "name": website_row["name"],
            },
            evidence=(
                "Physical facility match is strong, but the "
                "website shows a newer facility name."
            ),
            confidence="HIGH",
            lifetime_revenue=revenue,
            outstanding_ar=ar,
        )

    # --------------------------------------------------------
    # ADDRESS UPDATE
    # --------------------------------------------------------

    elif address_diff:

        action = "UPDATE_ADDRESS"

        add_proposal(
            proposals,
            action=action,
            website_name=website_row["name"],
            website_source_url=website_row[
                "source_url"
            ],
            target_account_id=crm_row[
                "account_id"
            ],
            current_values={
                "billing_street":
                    crm_row["billing_street"],
            },
            proposed_values={
                "billing_street":
                    website_row["address"],
            },
            evidence=(
                "Same facility name, city, state and ZIP, "
                "but the current Bellhaven website provides "
                "a different street address."
            ),
            confidence="HIGH",
            lifetime_revenue=revenue,
            outstanding_ar=ar,
        )

    # --------------------------------------------------------
    # ZIP UPDATE
    # --------------------------------------------------------

    elif zip_diff:

        action = "UPDATE_ZIP"

        add_proposal(
            proposals,
            action=action,
            website_name=website_row["name"],
            website_source_url=website_row[
                "source_url"
            ],
            target_account_id=crm_row[
                "account_id"
            ],
            current_values={
                "billing_zip":
                    crm_row["billing_zip"],
            },
            proposed_values={
                "billing_zip":
                    website_row["zip"],
            },
            evidence=(
                "Facility name and street address match, "
                "but website and CRM ZIP codes differ."
            ),
            confidence="HIGH",
            lifetime_revenue=revenue,
            outstanding_ar=ar,
        )

    else:

        action = "NO_ACTION"

    summary.append(
        {
            "website_name": website_row["name"],
            "crm_account_id": crm_row[
                "account_id"
            ],
            "crm_name": crm_row["name"],
            "classification": action,
            "match_score": match["score"],
        }
    )


# ============================================================
# 2. REVERSE CHECK: CRM -> WEBSITE
# ============================================================

credible_account_ids = {
    row["crm_account_id"]
    for row in credible_rows
}


bellhaven_children = [
    row
    for row in crm
    if row["parent_id"] == BELLHAVEN_PARENT_ID
]


# ------------------------------------------------------------
# Detect duplicates by normalized physical address
# ------------------------------------------------------------

address_groups = defaultdict(list)

for row in bellhaven_children:

    key = (
        normalize_text(row["billing_street"]),
        normalize_text(row["billing_city"]),
        row["billing_state"].upper(),
        row["billing_zip"],
    )

    if key[0]:
        address_groups[key].append(row)


duplicate_loser_ids = set()


for group in address_groups.values():

    if len(group) <= 1:
        continue

    # Find website record at same normalized address.
    matching_website = None

    for website_row in website:

        if (
            normalize_text(website_row["address"])
            == normalize_text(
                group[0]["billing_street"]
            )
            and normalize_text(website_row["city"])
            == normalize_text(
                group[0]["billing_city"]
            )
            and website_row["state"].upper()
            == group[0]["billing_state"].upper()
            and website_row["zip"]
            == group[0]["billing_zip"]
        ):
            matching_website = website_row
            break

    # Prefer the CRM record whose raw address exactly
    # matches the website representation.
    survivor = None

    if matching_website:

        exact_raw = [
            account
            for account in group
            if account["billing_street"].strip().lower()
            == matching_website[
                "address"
            ].strip().lower()
        ]

        if len(exact_raw) == 1:
            survivor = exact_raw[0]

    if survivor is None:
        survivor = sorted(
            group,
            key=lambda x: x["account_id"],
        )[0]

    for loser in group:

        # Never mark the surviving account as a duplicate.
        if loser["account_id"] == survivor["account_id"]:
            continue

        duplicate_loser_ids.add(
            loser["account_id"]
        )

        # Already handled on an earlier pipeline run.
        if (
            loser["status"] == "Inactive"
            and loser["duplicate_of_account"]
            == survivor["account_id"]
        ):
            continue

        
        add_proposal(
            proposals,
            action="MARK_DUPLICATE_INACTIVE",
            website_name=(
                matching_website["name"]
                if matching_website
                else loser["name"]
            ),
            website_source_url=(
                matching_website["source_url"]
                if matching_website
                else ""
            ),
            target_account_id=loser["account_id"],
            current_values={
                "status": loser["status"],
                "duplicate_of_account":
                    loser["duplicate_of_account"],
            },
            proposed_values={
                "duplicate_of_account":
                    survivor["account_id"],
                "status": "Inactive",
                "note": (
                    "Duplicate CRM account for the same "
                    "physical Bellhaven facility. "
                    f"Surviving account: "
                    f"{survivor['account_id']}."
                ),
            },
            evidence=(
                "Two Bellhaven CRM accounts share the same "
                "normalized facility address. The surviving "
                "record most closely matches the current "
                "website representation."
            ),
            confidence="HIGH",
            lifetime_revenue=loser[
                "lifetime_revenue"
            ],
            outstanding_ar=loser[
                "outstanding_ar"
            ],
        )


# ------------------------------------------------------------
# Bellhaven children not represented on current website
# ------------------------------------------------------------

for account in bellhaven_children:

    account_id = account["account_id"]

    if account_id in credible_account_ids:
        continue

    if account_id in duplicate_loser_ids:
        continue
    
    # Already handled stale account.
    if account["status"] == "Inactive":
        continue

    revenue = money(
        account["lifetime_revenue"]
    )

    ar = money(
        account["outstanding_ar"]
    )

    # Billing-sensitive stale account.
    # Preserve it and flag for review instead of blindly
    # inactivating.
    if revenue > 0 and ar > 0:
        
        if account["status"] == "Needs Review":
            continue

        add_proposal(
            proposals,
            action="MARK_NEEDS_REVIEW",
            website_name=account["name"],
            target_account_id=account_id,
            current_values={
                "status": account["status"],
                "parent_id": account["parent_id"],
                "lifetime_revenue": revenue,
                "outstanding_ar": ar,
            },
            proposed_values={
                "status": "Needs Review",
                "note": (
                    "Account remains under Bellhaven but is "
                    "not present on the current Bellhaven "
                    "website. Billing history and outstanding "
                    "AR exist, so automatic inactivation was "
                    "not performed."
                ),
            },
            evidence=(
                "CRM account is under Bellhaven but no current "
                "website facility matches it. Account has "
                f"${revenue:,.2f} lifetime revenue and "
                f"${ar:,.2f} outstanding AR."
            ),
            confidence="MEDIUM",
            lifetime_revenue=revenue,
            outstanding_ar=ar,
        )

    else:

        add_proposal(
            proposals,
            action="INACTIVATE_STALE",
            website_name=account["name"],
            target_account_id=account_id,
            current_values={
                "status": account["status"],
                "parent_id": account["parent_id"],
            },
            proposed_values={
                "status": "Inactive",
                "note": (
                    "Bellhaven CRM account is not represented "
                    "on the current Bellhaven website. "
                    "Marked inactive through ownership "
                    "reconciliation."
                ),
            },
            evidence=(
                "Account is currently under Bellhaven but no "
                "current Bellhaven website facility matches "
                "this city/location. No outstanding AR "
                "requires preservation."
            ),
            confidence="HIGH",
            lifetime_revenue=revenue,
            outstanding_ar=ar,
        )


# ============================================================
# 3. SAVE OUTPUTS
# ============================================================

proposal_fields = [
    "proposal_id",
    "action",
    "website_name",
    "website_source_url",
    "target_account_id",
    "current_values",
    "proposed_values",
    "evidence",
    "confidence",
    "lifetime_revenue",
    "outstanding_ar",
    "write_strategy",
    "review_status",
]


with open(
    PROPOSALS_FILE,
    "w",
    newline="",
    encoding="utf-8",
) as file:

    writer = csv.DictWriter(
        file,
        fieldnames=proposal_fields,
    )

    writer.writeheader()
    writer.writerows(proposals)


summary_fields = [
    "website_name",
    "crm_account_id",
    "crm_name",
    "classification",
    "match_score",
]


with open(
    SUMMARY_FILE,
    "w",
    newline="",
    encoding="utf-8",
) as file:

    writer = csv.DictWriter(
        file,
        fieldnames=summary_fields,
    )

    writer.writeheader()
    writer.writerows(summary)


# ============================================================
# 4. VALIDATION / REPORT
# ============================================================

counts = Counter(
    proposal["action"]
    for proposal in proposals
)


print("\n=== FINAL PROPOSAL GENERATION ===")
print(f"Website facilities accounted for: {len(summary)}")
print(f"Total proposals: {len(proposals)}")
print()

for action, count in sorted(counts.items()):
    print(f"{action}: {count}")

print()
print(
    "Website facilities with NO_ACTION:",
    sum(
        1
        for row in summary
        if row["classification"] == "NO_ACTION"
    ),
)

print()
print(f"Saved: {PROPOSALS_FILE}")
print(f"Saved: {SUMMARY_FILE}")

print()

if len(summary) == 35:
    print("WEBSITE RECONCILIATION COVERAGE: PASS")
else:
    print("WEBSITE RECONCILIATION COVERAGE: FAIL")

if len({p['proposal_id'] for p in proposals}) == len(proposals):
    print("UNIQUE PROPOSAL IDS: PASS")
else:
    print("UNIQUE PROPOSAL IDS: FAIL")