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


def insert_account(database: Path, acct: Account) -> None:
    with closing(connect_database(database)) as connection, transaction(connection):
        connection.execute(
            """
            INSERT INTO accounts (id, owner, balance_minor_units, balance_currency)
            VALUES (?, ?, ?, ?)
            """,
            (
                str(acct.id),
                acct.owner,
                acct.balance.amount_cents,
                acct.balance.currency.iso_code,
            ),
        )


def test_can_rehydrate_account_from_persisted_id(database: Path) -> None:
    acct_id = UUID("12345678-1234-5678-1234-567812345678")
    stored = Account(
        owner="Trade Owner",
        balance=Money.from_cents(1_000_025, USD),
        id_value=acct_id,
    )
    insert_account(database, stored)

    loaded = SQLiteAccountRepository(database).get(acct_id)

    assert loaded is not None
    assert loaded.id == acct_id
    assert loaded.owner == stored.owner
    assert loaded.balance == stored.balance


def test_ensure_exists_is_idempotent(database: Path) -> None:
    account_id = UUID("12345678-1234-5678-1234-567812345678")
    account = Account(
        owner="Trade Owner",
        balance=Money.from_cents(1_000_025, USD),
        id_value=account_id,
    )
    repository = SQLiteAccountRepository(database)

    repository.ensure_exists(account)
    repository.ensure_exists(account)

    with closing(connect_database(database)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]

    loaded = repository.get(account_id)
    assert count == 1
    assert loaded is not None
    assert loaded.id == account_id
    assert loaded.owner == account.owner
    assert loaded.balance == account.balance


def test_ensure_exists_does_not_modify_an_existing_account(database: Path) -> None:
    account_id = UUID("12345678-1234-5678-1234-567812345678")
    stored = Account(
        owner="Original Owner",
        balance=Money.from_cents(1_000_025, USD),
        id_value=account_id,
    )
    conflicting = Account(
        owner="Different Owner",
        balance=Money.from_cents(5, USD),
        id_value=account_id,
    )
    insert_account(database, stored)

    repository = SQLiteAccountRepository(database)
    repository.ensure_exists(conflicting)

    loaded = repository.get(account_id)
    assert loaded is not None
    assert loaded.owner == stored.owner
    assert loaded.balance == stored.balance


def test_get_returns_none_for_unknown_account(database: Path) -> None:
    assert SQLiteAccountRepository(database).get(uuid4()) is None


def test_connections_enable_foreign_keys(database: Path) -> None:
    with closing(connect_database(database)) as connection:
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert enabled == 1
