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

@pytest.fixture
def sam_account() -> Account:
    return Account(
        owner="Sam",
        balance=Money.mint("100"),
        id_value=UUID("12345678-1234-5678-1234-567812345678"),
    )

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


def test_can_rehydrate_account_from_persisted_id(database: Path, sam_account: Account) -> None:
    insert_account(database, sam_account)

    loaded = SQLiteAccountRepository(database).get(sam_account.id)

    assert loaded is not None
    assert loaded.id == sam_account.id
    assert loaded.owner == sam_account.owner
    assert loaded.balance == sam_account.balance


def test_ensure_exists_is_idempotent(database: Path, sam_account: Account) -> None:
    repository = SQLiteAccountRepository(database)

    repository.ensure_exists(sam_account)
    repository.ensure_exists(sam_account)

    with closing(connect_database(database)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]

    loaded = repository.get(sam_account.id)
    assert count == 1
    assert loaded is not None
    assert loaded.id == sam_account.id
    assert loaded.owner == sam_account.owner
    assert loaded.balance == sam_account.balance


def test_ensure_exists_does_not_modify_an_existing_account(database: Path, sam_account: Account) -> None:
    julie_account = Account(
        owner="Julie",
        balance=Money.from_cents(5, USD),
        id_value=sam_account.id,
    )
    insert_account(database, sam_account)

    repository = SQLiteAccountRepository(database)
    repository.ensure_exists(julie_account)

    loaded = repository.get(sam_account.id)
    assert loaded is not None
    assert loaded.owner == sam_account.owner
    assert loaded.balance == sam_account.balance


def test_get_returns_none_for_unknown_account(database: Path) -> None:
    assert SQLiteAccountRepository(database).get(uuid4()) is None


def test_connections_enable_foreign_keys(database: Path) -> None:
    with closing(connect_database(database)) as connection:
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert enabled == 1
