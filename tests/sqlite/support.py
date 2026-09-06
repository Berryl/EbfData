"""Explicit SQLite seed data for repository and selector tests."""

from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from ebf_data.sqlite import connect_database
from ebf_data.sqlite.database import transaction
from ebf_trading.domain.entities.account import Account


def insert_account(database: Path, account: Account) -> None:
    """Seed an account independently of the repository behavior under test."""
    with closing(connect_database(database)) as conn, transaction(conn):
        conn.execute(
            """
            INSERT INTO accounts (id, owner, balance_minor_units, balance_currency)
            VALUES (?, ?, ?, ?)
            """,
            (str(account.id), account.owner, account.balance.amount_cents, account.balance.currency.iso_code),
        )


def insert_query_campaign(
    db: Path,
    *,
    acct_id: UUID,
    ticker: str,
    ref_number: int,
    leg_states: Sequence[Literal["open", "closed"]],
) -> None:
    """Seed selector rows only, without orders, events, or reference allocation.

    Each state creates one leg; open legs have no exit time, and closed legs
    share a fixed exit time. These rows are not a rehydratable trade aggregate.
    """
    exit_times = {"open": None, "closed": "2026-08-22T15:00:00-04:00"}
    campaign_id = str(uuid4())
    with closing(connect_database(db)) as conn, transaction(conn):
        conn.execute(
            """
            INSERT INTO trade_campaigns (id, account_id, ticker, reference_number, reference_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (campaign_id, str(acct_id), ticker, ref_number, f"{ticker}{ref_number}"),
        )
        for state in leg_states:
            conn.execute(
                """
                INSERT INTO trade_legs (
                    id, campaign_id, option_type, strike_minor_units, strike_currency,
                    expiration_at, position_side, contract_quantity, exit_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    campaign_id,
                    "call",
                    5_000,
                    "USD",
                    "2026-09-18T16:00:00-04:00",
                    "long",
                    1,
                    exit_times[state],
                ),
            )
