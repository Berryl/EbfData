"""SQLite connection and schema setup for the trade journal."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from os import PathLike

DatabasePath = str | PathLike[str]

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL,
    balance_minor_units INTEGER NOT NULL,
    balance_currency TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS campaign_reference_sequences (
    ticker TEXT PRIMARY KEY,
    last_sequence INTEGER NOT NULL CHECK (last_sequence > 0)
);

CREATE TABLE IF NOT EXISTS trade_campaigns (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    ticker TEXT NOT NULL,
    reference_number INTEGER NOT NULL,
    reference_id TEXT NOT NULL UNIQUE,
    UNIQUE (ticker, reference_number)
);

CREATE TABLE IF NOT EXISTS trade_legs (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES trade_campaigns(id),
    option_type TEXT NOT NULL,
    strike_minor_units INTEGER NOT NULL,
    strike_currency TEXT NOT NULL,
    expiration_at TEXT NOT NULL,
    position_side TEXT NOT NULL,
    contract_quantity INTEGER NOT NULL,
    exit_at TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES trade_campaigns(id),
    leg_id TEXT NOT NULL REFERENCES trade_legs(id),
    submission_at TEXT NOT NULL,
    order_spec_type TEXT NOT NULL,
    fill_at TEXT NOT NULL,
    fill_price_minor_units INTEGER NOT NULL,
    fill_price_currency TEXT NOT NULL,
    fees_minor_units INTEGER NOT NULL,
    fees_currency TEXT NOT NULL,
    contract_quantity INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS transaction_events (
    id TEXT PRIMARY KEY,
    campaign_id TEXT NOT NULL REFERENCES trade_campaigns(id),
    leg_id TEXT NOT NULL REFERENCES trade_legs(id),
    order_id INTEGER NOT NULL REFERENCES orders(id),
    event_type TEXT NOT NULL,
    notes TEXT
);
"""


def connect_database(database: DatabasePath) -> sqlite3.Connection:
    """Open a configured connection to the trade-journal database."""
    connection = sqlite3.connect(database, timeout=5.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def initialize_database(database: DatabasePath) -> None:
    """Create the initial schema when it does not exist."""
    connection = connect_database(database)
    try:
        connection.executescript(SCHEMA_SQL)
    finally:
        connection.close()


@contextmanager
def transaction(connection: sqlite3.Connection, *, immediate: bool = False) -> Iterator[None]:
    """Run statements in an explicit transaction, rolling back on failure."""
    connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        yield
    except BaseException:
        connection.rollback()
        raise
    else:
        connection.commit()
