import argparse
import csv
import json
import os
import sqlite3

import requests


BASE_URL = "https://analyst-assessment-production.up.railway.app/api/v1"
PROPOSALS_FILE = "data/processed/proposals.csv"
DB_FILE = "data/review_decisions.db"


def get_token():
    token = os.getenv("CRM_API_TOKEN")

    if not token:
        raise RuntimeError(
            "CRM_API_TOKEN is not set."
        )

    return token


def headers():
    return {
        "Authorization": f"Bearer {get_token()}",
        "Content-Type": "application/json",
    }


def load_proposals():
    with open(
        PROPOSALS_FILE,
        encoding="utf-8",
    ) as file:
        return list(csv.DictReader(file))


def get_connection():
    return sqlite3.connect(DB_FILE)



def initialize_application_log():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                proposal_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                applied_at TEXT,
                api_response TEXT,
                error_message TEXT,
                created_account_id TEXT
            )
            """
        )

        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(applications)"
            ).fetchall()
        }

        if "created_account_id" not in columns:
            conn.execute(
                """
                ALTER TABLE applications
                ADD COLUMN created_account_id TEXT
                """
            )

def get_approved_ids():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT proposal_id
            FROM decisions
            WHERE decision = 'APPROVED'
            """
        ).fetchall()

    return {row[0] for row in rows}


def get_applied_ids():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT proposal_id
            FROM applications
            WHERE status = 'APPLIED'
            """
        ).fetchall()

    return {row[0] for row in rows}


def record_result(
    proposal_id,
    status,
    response="",
    error="",
):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO applications (
                proposal_id,
                status,
                applied_at,
                api_response,
                error_message
            )
            VALUES (
                ?,
                ?,
                CASE
                    WHEN ? = 'APPLIED'
                    THEN datetime('now')
                    ELSE NULL
                END,
                ?,
                ?
            )
            ON CONFLICT(proposal_id)
            DO UPDATE SET
                status = excluded.status,
                applied_at = excluded.applied_at,
                api_response = excluded.api_response,
                error_message = excluded.error_message
            """,
            (
                proposal_id,
                status,
                status,
                response,
                error,
            ),
        )


def patch_account(account_id, payload):
    response = requests.patch(
        f"{BASE_URL}/accounts/{account_id}",
        headers=headers(),
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def create_account(payload):
    response = requests.post(
        f"{BASE_URL}/accounts",
        headers=headers(),
        json=payload,
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def extract_account_id(response):
    if isinstance(response, dict):

        if response.get("account_id"):
            return response["account_id"]

        data = response.get("data")

        if isinstance(data, dict):
            if data.get("account_id"):
                return data["account_id"]

    raise ValueError(
        "Could not find account_id in POST response."
    )


def normal_patch(proposal):
    payload = json.loads(
        proposal["proposed_values"]
    )

    return patch_account(
        proposal["target_account_id"],
        payload,
    )


def create_new(proposal):
    payload = json.loads(
        proposal["proposed_values"]
    )

    return create_account(payload)

def get_created_account_id(proposal_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT created_account_id
            FROM applications
            WHERE proposal_id = ?
            """,
            (proposal_id,),
        ).fetchone()

    if row:
        return row[0]

    return None


def save_created_account_id(proposal_id, account_id):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO applications (
                proposal_id,
                status,
                created_account_id
            )
            VALUES (?, 'CHOW_IN_PROGRESS', ?)
            ON CONFLICT(proposal_id)
            DO UPDATE SET
                status = 'CHOW_IN_PROGRESS',
                created_account_id = excluded.created_account_id
            """,
            (
                proposal_id,
                account_id,
            ),
        )


def apply_chow(proposal):
    values = json.loads(
        proposal["proposed_values"]
    )

    proposal_id = proposal["proposal_id"]

    old_account_id = proposal[
        "target_account_id"
    ]

    # Check whether a previous attempt already created
    # the new Bellhaven account.
    new_account_id = get_created_account_id(
        proposal_id
    )

    if not new_account_id:

        # Step 1. Create the new Bellhaven account.
        new_response = create_account(
            values["create_new_account"]
        )

        new_account_id = extract_account_id(
            new_response
        )

        # Immediately remember the ID BEFORE patching
        # the old account.
        save_created_account_id(
            proposal_id,
            new_account_id,
        )

    else:
        new_response = {
            "message":
                "Reusing previously created CHOW account",
            "account_id":
                new_account_id,
        }

    # Step 2. Preserve the old account and parent.
    # Only add the CHOW link.
    old_response = patch_account(
        old_account_id,
        {
            "chow_current_account":
                new_account_id
        },
    )

    return {
        "new_account_id": new_account_id,
        "new_account_response":
            new_response,
        "old_account_response":
            old_response,
    }


def apply_proposal(proposal):
    action = proposal["action"]

    if action == "CREATE_NEW":
        return create_new(proposal)

    if action == "CHOW_REQUIRED":
        return apply_chow(proposal)

    if action in {
        "UPDATE_NAME",
        "UPDATE_ADDRESS",
        "UPDATE_ZIP",
        "REPARENT",
        "UPDATE_NAME_AND_REPARENT",
        "MARK_DUPLICATE_INACTIVE",
        "INACTIVATE_STALE",
        "MARK_NEEDS_REVIEW",
    }:
        return normal_patch(proposal)

    raise ValueError(
        f"Unsupported action: {action}"
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    initialize_application_log()

    proposals = load_proposals()
    approved_ids = get_approved_ids()
    applied_ids = get_applied_ids()

    queue = [
        proposal
        for proposal in proposals
        if proposal["proposal_id"]
        in approved_ids
        and proposal["proposal_id"]
        not in applied_ids
    ]

    if args.limit:
        queue = queue[:args.limit]

    print(
        f"Approved and not yet applied: "
        f"{len(queue)}"
    )

    if not queue:
        print("Nothing to apply.")
        return

    for proposal in queue:

        print()
        print("=" * 70)
        print(
            proposal["website_name"]
        )
        print(
            "Action:",
            proposal["action"],
        )
        print(
            "Proposal:",
            proposal["proposal_id"],
        )
        print(
            "CRM Account:",
            proposal["target_account_id"]
            or "NEW ACCOUNT",
        )

        print(
            "Proposed:",
            proposal["proposed_values"],
        )

        if args.dry_run:
            print("DRY RUN. No CRM write performed.")
            continue

        try:
            result = apply_proposal(
                proposal
            )

            result_text = json.dumps(
                result,
                ensure_ascii=False,
                default=str,
            )

            record_result(
                proposal["proposal_id"],
                "APPLIED",
                response=result_text,
            )

            print("RESULT: APPLIED")
            print(result_text)

        except Exception as error:

            record_result(
                proposal["proposal_id"],
                "FAILED",
                error=str(error),
            )

            print("RESULT: FAILED")
            print(error)

            # Stop immediately so we never blindly
            # continue after an unexpected API error.
            break


if __name__ == "__main__":
    main()
