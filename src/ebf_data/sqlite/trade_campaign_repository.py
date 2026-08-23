"""SQLite implementation of the trade-campaign repository."""

import sqlite3
from contextlib import closing

from ebf_data.sqlite.database import DatabasePath, connect_database, transaction
from ebf_data.sqlite.mapping import map_campaign
from ebf_trading.domain.entities.trade_campaign import TradeCampaign
from ebf_trading.domain.value_objects.symbol import Symbol


class SQLiteTradeCampaignRepository:
    """Allocate references and persist the initial trade-journal aggregate."""

    def __init__(self, database: DatabasePath) -> None:
        self._database = database

    def allocate_reference_id(self, ticker: str) -> str:
        """Atomically reserve and return the next per-symbol reference ID."""
        normalized_ticker = Symbol(ticker).value
        with closing(connect_database(self._database)) as connection, transaction(
            connection, immediate=True
        ):
            row = connection.execute(
                """
                INSERT INTO campaign_reference_sequences (ticker, last_sequence)
                VALUES (?, 1)
                ON CONFLICT (ticker) DO UPDATE
                SET last_sequence = last_sequence + 1
                RETURNING last_sequence
                """,
                (normalized_ticker,),
            ).fetchone()

        if row is None:
            raise RuntimeError("SQLite did not return an allocated campaign sequence")
        return f"{normalized_ticker}{int(row['last_sequence'])}"

    def add(self, campaign: TradeCampaign) -> None:
        """Persist the current one-leg creation aggregate in one transaction."""
        rows = map_campaign(campaign)
        with closing(connect_database(self._database)) as connection, transaction(connection):
            connection.execute(
                """
                INSERT INTO trade_campaigns (
                    id, account_id, ticker, reference_number, reference_id
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    rows.campaign.id,
                    rows.campaign.account_id,
                    rows.campaign.ticker,
                    rows.campaign.reference_number,
                    rows.campaign.reference_id,
                ),
            )
            connection.execute(
                """
                INSERT INTO trade_legs (
                    id, campaign_id, option_type, strike_minor_units,
                    strike_currency, expiration_at, position_side, contract_quantity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rows.leg.id,
                    rows.leg.campaign_id,
                    rows.leg.option_type,
                    rows.leg.strike_minor_units,
                    rows.leg.strike_currency,
                    rows.leg.expiration_at,
                    rows.leg.position_side,
                    rows.leg.contract_quantity,
                ),
            )
            order_cursor = connection.execute(
                """
                INSERT INTO orders (
                    campaign_id, leg_id, submission_at, order_spec_type, fill_at,
                    fill_price_minor_units, fill_price_currency, fees_minor_units,
                    fees_currency, contract_quantity
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rows.order.campaign_id,
                    rows.order.leg_id,
                    rows.order.submission_at,
                    rows.order.order_spec_type,
                    rows.order.fill_at,
                    rows.order.fill_price_minor_units,
                    rows.order.fill_price_currency,
                    rows.order.fees_minor_units,
                    rows.order.fees_currency,
                    rows.order.contract_quantity,
                ),
            )
            order_id = order_cursor.lastrowid
            if order_id is None:
                raise sqlite3.DatabaseError("SQLite did not assign an order row ID")
            connection.execute(
                """
                INSERT INTO transaction_events (
                    id, campaign_id, leg_id, order_id, event_type, notes
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    rows.event.id,
                    rows.event.campaign_id,
                    rows.event.leg_id,
                    order_id,
                    rows.event.event_type,
                    rows.event.notes,
                ),
            )
