import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st


PROPOSALS_FILE = Path("data/processed/proposals.csv")
DB_FILE = Path("data/review_decisions.db")


# ------------------------------------------------------------
# DATABASE
# ------------------------------------------------------------

def get_connection():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_FILE)


def initialize_database():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                proposal_id TEXT PRIMARY KEY,
                decision TEXT NOT NULL,
                decided_at TEXT NOT NULL,
                reviewer_note TEXT
            )
            """
        )


def get_decisions():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT
                proposal_id,
                decision,
                decided_at,
                reviewer_note
            FROM decisions
            """
        ).fetchall()

    return {
        row[0]: {
            "decision": row[1],
            "decided_at": row[2],
            "reviewer_note": row[3],
        }
        for row in rows
    }


def save_decision(proposal_id, decision, reviewer_note):
    decided_at = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO decisions (
                proposal_id,
                decision,
                decided_at,
                reviewer_note
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(proposal_id)
            DO UPDATE SET
                decision = excluded.decision,
                decided_at = excluded.decided_at,
                reviewer_note = excluded.reviewer_note
            """,
            (
                proposal_id,
                decision,
                decided_at,
                reviewer_note,
            ),
        )


# ------------------------------------------------------------
# DATA
# ------------------------------------------------------------

@st.cache_data
def load_proposals():
    return pd.read_csv(
        PROPOSALS_FILE,
        dtype=str,
    ).fillna("")


def parse_json(value):
    if not value:
        return {}

    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return {"raw_value": value}


def pretty_label(value):
    return value.replace("_", " ").title()


# ------------------------------------------------------------
# PAGE SETUP
# ------------------------------------------------------------

st.set_page_config(
    page_title="Bellhaven CRM Review",
    page_icon="🏢",
    layout="wide",
)

initialize_database()

proposals = load_proposals()
decisions = get_decisions()


# ------------------------------------------------------------
# HEADER
# ------------------------------------------------------------

st.title("Bellhaven CRM Reconciliation Review")

st.caption(
    "Review proposed CRM corrections before any changes "
    "are written to the CRM."
)


# ------------------------------------------------------------
# STATUS
# ------------------------------------------------------------

def decision_for(proposal_id):
    if proposal_id not in decisions:
        return "PENDING"

    return decisions[proposal_id]["decision"]


proposals["decision"] = proposals[
    "proposal_id"
].apply(decision_for)


total = len(proposals)

approved = (
    proposals["decision"] == "APPROVED"
).sum()

rejected = (
    proposals["decision"] == "REJECTED"
).sum()

pending = (
    proposals["decision"] == "PENDING"
).sum()


col1, col2, col3, col4 = st.columns(4)

col1.metric("Total Proposals", total)
col2.metric("Pending", pending)
col3.metric("Approved", approved)
col4.metric("Rejected", rejected)


progress = (approved + rejected) / total if total else 0

st.progress(
    progress,
    text=f"{approved + rejected} of {total} proposals reviewed"
)


# ------------------------------------------------------------
# FILTERS
# ------------------------------------------------------------

st.divider()

filter_col1, filter_col2 = st.columns(2)

status_filter = filter_col1.selectbox(
    "Review Status",
    [
        "Pending",
        "All",
        "Approved",
        "Rejected",
    ],
)

actions = sorted(
    proposals["action"].unique()
)

action_filter = filter_col2.selectbox(
    "Action Type",
    ["All"] + actions,
)


filtered = proposals.copy()

if status_filter != "All":
    filtered = filtered[
        filtered["decision"]
        == status_filter.upper()
    ]

if action_filter != "All":
    filtered = filtered[
        filtered["action"]
        == action_filter
    ]


# ------------------------------------------------------------
# REVIEW QUEUE
# ------------------------------------------------------------

st.divider()

st.subheader("Review Queue")

if filtered.empty:
    st.success(
        "No proposals match the selected filters."
    )


for _, row in filtered.iterrows():

    proposal_id = row["proposal_id"]
    action = row["action"]

    current_values = parse_json(
        row["current_values"]
    )

    proposed_values = parse_json(
        row["proposed_values"]
    )

    current_decision = decision_for(
        proposal_id
    )

    title = (
        f"{row['website_name']}  |  "
        f"{pretty_label(action)}"
    )

    with st.expander(
        title,
        expanded=current_decision == "PENDING",
    ):

        info1, info2, info3, info4 = st.columns(4)

        info1.write("**Confidence**")
        info1.write(row["confidence"])

        info2.write("**CRM Account**")
        info2.write(
            row["target_account_id"]
            or "New Account"
        )

        info3.write("**Lifetime Revenue**")
        info3.write(
            row["lifetime_revenue"]
            or "0"
        )

        info4.write("**Outstanding AR**")
        info4.write(
            row["outstanding_ar"]
            or "0"
        )

        if action == "CHOW_REQUIRED":
            st.warning(
                "CHOW REQUIRED. Do not re-parent the old "
                "account. Preserve it, create a new Bellhaven "
                "account, and link the old account to the new "
                "account using chow_current_account."
            )

        elif action == "MARK_NEEDS_REVIEW":
            st.warning(
                "This proposal contains uncertainty and "
                "requires careful manual review."
            )

        elif action == "MARK_DUPLICATE_INACTIVE":
            st.info(
                "This CRM account appears to be a duplicate "
                "of another account representing the same "
                "physical facility."
            )

        st.markdown("### Evidence")

        st.write(row["evidence"])

        if row["website_source_url"]:
            st.write(
                f"Website evidence: "
                f"{row['website_source_url']}"
            )

        left, right = st.columns(2)

        with left:
            st.markdown("### Current CRM")

            if current_values:
                for key, value in current_values.items():
                    st.write(
                        f"**{pretty_label(key)}:** "
                        f"{value}"
                    )
            else:
                st.write(
                    "No existing CRM account."
                )

        with right:
            st.markdown("### Proposed Change")

            if proposed_values:
                st.json(proposed_values)
            else:
                st.write(
                    "No proposed field changes."
                )

        st.markdown("### Review")

        st.write(
            f"Current decision: **{current_decision}**"
        )

        existing_note = ""

        if proposal_id in decisions:
            existing_note = (
                decisions[proposal_id][
                    "reviewer_note"
                ]
                or ""
            )

        reviewer_note = st.text_area(
            "Reviewer note",
            value=existing_note,
            key=f"note_{proposal_id}",
            placeholder=(
                "Optional explanation for your decision"
            ),
        )

        button1, button2 = st.columns(2)

        approve = button1.button(
            "✅ Approve",
            key=f"approve_{proposal_id}",
            use_container_width=True,
            type="primary",
        )

        reject = button2.button(
            "❌ Reject",
            key=f"reject_{proposal_id}",
            use_container_width=True,
        )

        if approve:
            save_decision(
                proposal_id,
                "APPROVED",
                reviewer_note,
            )

            st.success(
                "Proposal approved."
            )

            st.rerun()

        if reject:
            save_decision(
                proposal_id,
                "REJECTED",
                reviewer_note,
            )

            st.error(
                "Proposal rejected. No CRM change will be made."
            )

            st.rerun()


# ------------------------------------------------------------
# DECISION HISTORY
# ------------------------------------------------------------

st.divider()
st.subheader("Decision History")

history = proposals[
    proposals["decision"] != "PENDING"
][
    [
        "website_name",
        "action",
        "decision",
        "proposal_id",
    ]
]

if history.empty:
    st.write(
        "No proposals have been reviewed yet."
    )
else:
    st.dataframe(
        history,
        use_container_width=True,
        hide_index=True,
    )