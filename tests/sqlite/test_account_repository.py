from contextlib import closing
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from ebf_data.sqlite import SQLiteAccountRepository, connect_database, initialize_database
from ebf_data.sqlite.database import transaction
from ebf_domain.money.currency import USD
from ebf_domain.money.money import Money
from ebf_trading.domain.entities.account import Account


@pytest.fixture
def database(tmp_path: Path) -> Path:
    path = tmp_path / "journal.sqlite3"
    initialize_database(path)
    return path


def insert_account(database: Path, account: Account) -> None:
    with closing(connect_database(database)) as connection, transaction(connection):
        connection.execute(
            """
            INSERT INTO accounts (id, owner, balance_minor_units, balance_currency)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(account.id),
                account.owner,
                account.balance.amount_cents,
                account.balance.currency.iso_code,
            ),
        )


def test_get_rehydrates_account_with_its_persisted_identity(database: Path) -> None:
    account_id = UUID("12345678-1234-5678-1234-567812345678")
    stored = Account(
        owner="Trade Owner",
        balance=Money.from_cents(1_000_025, USD),
        id_value=account_id,
    )
    insert_account(database, stored)

    loaded = SQLiteAccountRepository(database).get(account_id)

    assert loaded is not None
    assert loaded.id == account_id
    assert loaded.owner == "Trade Owner"
    assert loaded.balance.amount_cents == 1_000_025
    assert loaded.balance.currency == USD


def test_get_returns_none_for_unknown_account(database: Path) -> None:
    assert SQLiteAccountRepository(database).get(uuid4()) is None


def test_connections_enable_foreign_keys(database: Path) -> None:
    with closing(connect_database(database)) as connection:
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert enabled == 1
