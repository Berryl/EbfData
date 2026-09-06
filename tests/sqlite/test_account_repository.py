from contextlib import closing
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from ebf_data.sqlite import SQLiteAccountRepository, connect_database, initialize_database
from ebf_domain.money.currency import USD
from ebf_domain.money.money import Money
from ebf_trading.domain.entities.account import Account
from tests.sqlite.support import insert_account


@pytest.fixture
def db(tmp_path: Path) -> Path:
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


def test_can_rehydrate_account_from_persisted_id(db: Path, sam_account: Account) -> None:
    insert_account(db, sam_account)

    sams_id = sam_account.id
    fetched = SQLiteAccountRepository(db).get(sams_id)

    assert fetched is not None
    assert fetched.id == sams_id and fetched.owner == sam_account.owner and fetched.balance == sam_account.balance


def test_ensure_exists_is_idempotent(db: Path, sam_account: Account) -> None:
    repo = SQLiteAccountRepository(db)

    repo.ensure_exists(sam_account)
    repo.ensure_exists(sam_account)

    with closing(connect_database(db)) as connection:
        count = connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
    assert count == 1

    sams_id = sam_account.id
    fetched = repo.get(sams_id)

    assert fetched is not None
    assert fetched.id == sams_id and fetched.owner == sam_account.owner and fetched.balance == sam_account.balance


def test_ensure_exists_does_not_modify_an_existing_account(db: Path, sam_account: Account) -> None:
    julie_account = Account(
        owner="Julie",
        balance=Money.from_cents(5, USD),
        id_value=sam_account.id,
    )
    insert_account(db, sam_account)

    repo = SQLiteAccountRepository(db)
    repo.ensure_exists(julie_account)

    fetched = repo.get(sam_account.id)
    assert fetched is not None
    assert fetched.owner == sam_account.owner and fetched.balance == sam_account.balance


def test_get_returns_none_for_unknown_account(db: Path) -> None:
    unknown_user = uuid4()
    assert SQLiteAccountRepository(db).get(unknown_user) is None


def test_connections_enable_foreign_keys(db: Path) -> None:
    with closing(connect_database(db)) as connection:
        enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]

    assert enabled == 1
