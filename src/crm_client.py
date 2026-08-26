import csv
import json
import os

import requests


BASE_URL = "https://analyst-assessment-production.up.railway.app/api/v1"
OUTPUT_JSON = "data/raw/crm_accounts.json"
OUTPUT_CSV = "data/raw/crm_accounts.csv"

PAGE_SIZE = 50


def get_token():
    token = os.getenv("CRM_API_TOKEN")

    if not token:
        raise RuntimeError(
            "CRM_API_TOKEN environment variable is not set."
        )

    return token


def get_headers():
    return {
        "Authorization": f"Bearer {get_token()}"
    }


def get_accounts_page(page):
    response = requests.get(
        f"{BASE_URL}/accounts",
        headers=get_headers(),
        params={
            "page": page,
            "page_size": PAGE_SIZE,
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def extract_accounts(response_data):
    """
    API responses may wrap account records in a 'data' field.
    Return the account list safely.
    """

    if isinstance(response_data, list):
        return response_data

    if isinstance(response_data, dict):
        if isinstance(response_data.get("data"), list):
            return response_data["data"]

    raise ValueError(
        f"Unexpected API response structure: {type(response_data)}"
    )


def get_all_accounts():
    all_accounts = []
    page = 1

    while True:
        response_data = get_accounts_page(page)
        accounts = extract_accounts(response_data)

        print(f"Page {page}: {len(accounts)} accounts")

        all_accounts.extend(accounts)

        if len(accounts) < PAGE_SIZE:
            break

        page += 1

    return all_accounts


def save_json(accounts):
    os.makedirs("data/raw", exist_ok=True)

    with open(
        OUTPUT_JSON,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            accounts,
            file,
            indent=2,
            ensure_ascii=False,
        )


def save_csv(accounts):
    if not accounts:
        return

    # Collect every field appearing in any account.
    fieldnames = []

    for account in accounts:
        for key in account.keys():
            if key not in fieldnames:
                fieldnames.append(key)

    with open(
        OUTPUT_CSV,
        "w",
        newline="",
        encoding="utf-8",
    ) as file:

        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
            extrasaction="ignore",
        )

        writer.writeheader()
        writer.writerows(accounts)


def main():
    accounts = get_all_accounts()

    print()
    print(f"Total CRM accounts: {len(accounts)}")

    save_json(accounts)
    save_csv(accounts)

    print(f"Saved: {OUTPUT_JSON}")
    print(f"Saved: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()