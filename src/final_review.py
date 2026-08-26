import csv


WEBSITE_FILE = "data/raw/website_locations.csv"
CRM_FILE = "data/raw/crm_accounts.csv"


def load_csv(path):
    with open(path, encoding="utf-8") as file:
        return list(csv.DictReader(file))


website = load_csv(WEBSITE_FILE)
crm = load_csv(CRM_FILE)


TARGET_NAMES = [
    "Union Square Senior Living",
    "Bellhaven of Owosso",
    "Bellhaven Care Center of Alliance",
    "Bellhaven of Coldwater",
    "Bellhaven of Sandusky",
]


def print_crm_account(account):
    print("-" * 95)
    print(f"Account ID:       {account['account_id']}")
    print(f"Name:             {account['name']}")
    print(f"Parent:           {account['parent_name']}")
    print(
        f"Address:          "
        f"{account['billing_street']}, "
        f"{account['billing_city']}, "
        f"{account['billing_state']} "
        f"{account['billing_zip']}"
    )
    print(f"Care Type:        {account['care_type']}")
    print(f"Status:           {account['status']}")
    print(f"Lifetime Revenue: {account['lifetime_revenue']}")
    print(f"Outstanding AR:   {account['outstanding_ar']}")
    print(f"Duplicate Of:     {account['duplicate_of_account']}")
    print(f"CHOW Current:     {account['chow_current_account']}")
    print(f"Note:             {account['note']}")
    print(f"Created:          {account['created_by_candidate']}")
    print(f"Updated:          {account['updated_at']}")

    same_city = [
        row
        for row in website
        if row["city"].strip().lower()
        == account["billing_city"].strip().lower()
        and row["state"].strip().upper()
        == account["billing_state"].strip().upper()
    ]

    print("\nCurrent website facilities in same city/state:")

    if not same_city:
        print("  NONE")
    else:
        for row in same_city:
            print(
                f"  {row['name']} | "
                f"{row['address']}, "
                f"{row['city']}, "
                f"{row['state']} "
                f"{row['zip']} | "
                f"{row['care_offerings']}"
            )

    print()


print("\n=== FINAL TARGETED CRM REVIEW ===\n")

for target in TARGET_NAMES:

    accounts = [
        row for row in crm
        if row["name"] == target
    ]

    print("\n" + "=" * 95)
    print(f"TARGET: {target}")
    print(f"CRM records found: {len(accounts)}")
    print("=" * 95)

    for account in accounts:
        print_crm_account(account)


print("\n=== UNION SQUARE WEBSITE RECORD ===\n")

for row in website:
    if row["name"] == "Bellhaven at Union Square":
        print(f"Name:          {row['name']}")
        print(f"Address:       {row['address']}")
        print(f"City:          {row['city']}")
        print(f"State:         {row['state']}")
        print(f"ZIP:           {row['zip']}")
        print(f"Care offerings:{row['care_offerings']}")
        print(f"Source:        {row['source_url']}")