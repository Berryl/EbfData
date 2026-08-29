"""SQLite implementation of the trading account repository."""

from contextlib import closing
from uuid import UUID

from ebf_data.sqlite.database import DatabasePath, connect_database, transaction
from ebf_domain.money.currency import get_currency
from ebf_domain.money.money import Money
from ebf_trading.domain.entities.account import Account


class SQLiteAccountRepository:
    """Load accounts needed by the trade-campaign creation operation."""

    def __init__(self, database: DatabasePath) -> None:
        self._database = database

    def ensure_exists(self, acct: Account) -> None:
        """Insert the account when its UUID is not already present."""
        with closing(connect_database(self._database)) as connection, transaction(connection):
            connection.execute(
                """
                INSERT INTO accounts (id, owner, balance_minor_units, balance_currency)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (id) DO NOTHING
                """,
                (
                    str(acct.id),
                    acct.owner,
                    acct.balance.amount_cents,
                    acct.balance.currency.iso_code,
                ),
            )

    def get(self, acct_id: UUID) -> Account | None:
        """Return the account with the supplied UUID, if it exists."""
        with closing(connect_database(self._database)) as connection:
            row = connection.execute(
                """
                SELECT id, owner, balance_minor_units, balance_currency
                FROM accounts
                WHERE id = ?
                """,
                (str(acct_id),),
            ).fetchone()

        if row is None:
            return None

        currency = get_currency(str(row["balance_currency"]))
        return Account(
            owner=str(row["owner"]),
            balance=Money.from_cents(int(row["balance_minor_units"]), currency),
            id_value=UUID(str(row["id"])),
        )
