"""SQLite read model for journal campaign selectors."""

from contextlib import closing
from uuid import UUID

from ebf_data.sqlite.database import DatabasePath, connect_database
from ebf_trading.application.queries import (
    CampaignStatusFilter,
    JournalCampaignChoice,
    JournalCampaignChoices,
)
from ebf_trading.domain.value_objects.symbol import Symbol

_ACTIVE_CLAUSE = """
EXISTS (
    SELECT 1
    FROM trade_legs AS leg
    WHERE leg.campaign_id = campaign.id
      AND leg.exit_at IS NULL
)
"""

_HAS_LEGS_CLAUSE = """
EXISTS (
    SELECT 1
    FROM trade_legs AS leg
    WHERE leg.campaign_id = campaign.id
)
"""

_CLOSED_CLAUSE = f"""
{_HAS_LEGS_CLAUSE}
AND NOT {_ACTIVE_CLAUSE}
"""

_STATUS_CLAUSES = {
    CampaignStatusFilter.ACTIVE: _ACTIVE_CLAUSE,
    CampaignStatusFilter.CLOSED: _CLOSED_CLAUSE,
    CampaignStatusFilter.ALL: _HAS_LEGS_CLAUSE,
}


class SQLiteJournalCampaignQuery:
    """Populate journal selectors without rehydrating full campaign aggregates."""

    def __init__(self, database: DatabasePath) -> None:
        self._database = database

    def list_symbols(
        self,
        status: CampaignStatusFilter = CampaignStatusFilter.ACTIVE,
    ) -> tuple[str, ...]:
        """Return matching symbols in alphabetical order."""
        status_clause = _STATUS_CLAUSES[status]
        with closing(connect_database(self._database)) as connection:
            rows = connection.execute(
                f"""
                SELECT DISTINCT campaign.ticker
                FROM trade_campaigns AS campaign
                WHERE {status_clause}
                ORDER BY campaign.ticker COLLATE NOCASE ASC
                """
            ).fetchall()
        return tuple(str(row["ticker"]) for row in rows)

    def list_campaigns(
        self,
        symbol: str,
        status: CampaignStatusFilter = CampaignStatusFilter.ACTIVE,
    ) -> JournalCampaignChoices:
        """Return matching campaigns in numeric reference order."""
        normalized_symbol = Symbol(symbol).value
        status_clause = _STATUS_CLAUSES[status]
        with closing(connect_database(self._database)) as connection:
            rows = connection.execute(
                f"""
                SELECT campaign.id, campaign.reference_id
                FROM trade_campaigns AS campaign
                WHERE campaign.ticker = ?
                  AND {status_clause}
                ORDER BY campaign.reference_number ASC
                """,
                (normalized_symbol,),
            ).fetchall()
        return JournalCampaignChoices(
            tuple(
                JournalCampaignChoice(
                    campaign_id=UUID(str(row["id"])),
                    reference_id=str(row["reference_id"]),
                )
                for row in rows
            )
        )
