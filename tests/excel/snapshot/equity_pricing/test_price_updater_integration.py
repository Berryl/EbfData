"""
Integration tests for PriceUpdater.fetch_prices() SELECTED and VISIBLE scope.

Unlike test_price_updater.py (fake snapshot and fake fetcher, no Excel),
these scopes depend on real Application.Selection / SpecialCells COM
behavior that a plain fake can't stand in for - so these open a live
disposable scenario workbook via xlTestScenario and manipulate real
selection/row-hidden state before calling fetch_prices().

Per project rule, this never touches a production workbook: xlTestScenario
only ever opens files under resources/ scenarios/ and closes without
 saving, so each test starts clean regardless of what it changed.

Expected outcomes are derived from whatever the fixture actually contains
at runtime (row count, symbols), not hardcoded - these tests only require
that SnapshotScenario_EquityPricing has at least two rows, not knowledge
of their exact contents.
"""
import pytest

from ebf_data.excel.infrastructure.table_helpers import get_data_body_column
from ebf_data.excel.pricing.price_fetcher import PriceFetcher
from ebf_data.excel.snapshot.price_updater import PriceUpdater, PriceUpdateScope
from tests.excel.pricing.pricing_scenarios import SnapshotScenario_EquityPricing


class FakeFetcher(PriceFetcher):
    """Deterministic price per base ticker, assigned from whatever
    tickers are actually requested - keeps these tests from needing to
    hardcode the fixture's real symbols."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def fetch_prices(self, tickers: list[str]) -> dict[str, float | None]:
        self.calls.append(list(tickers))
        return {t: 100.0 + i for i, t in enumerate(tickers)}


@pytest.fixture
def equity_scenario():
    with SnapshotScenario_EquityPricing() as scenario:
        yield scenario


class TestWhenScopeIsAll:
    """
    Sanity check that SnapshotTable.SYMBOL_COLUMN / POSITION_COLUMN
    actually line up with the real Excel headers in a production-shaped
    table - something the fake-snapshot unit tests can't expose, since
    they never touch a real worksheet.
    """

    def test_all_scope_matches_rows_with_nonblank_position(self, equity_scenario):
        df = equity_scenario.df
        expected = df[df[PriceUpdater.POSITION_COLUMN].notna() & (df[PriceUpdater.POSITION_COLUMN] != "")]
        expected_symbols = sorted(expected[PriceUpdater.SYMBOL_COLUMN].astype(str).tolist())

        sut = PriceUpdater(equity_scenario, FakeFetcher())
        result, outcomes = sut.fetch_prices(PriceUpdateScope.ALL)

        assert sorted(o.symbol for o in outcomes) == expected_symbols


class TestWhenScopeIsAllVisible:
    def test_hidden_row_is_excluded_from_outcomes(self, equity_scenario):
        df = equity_scenario.df
        assert len(df) >= 2, "fixture needs at least 2 rows for this test to be meaningful"

        data_body = equity_scenario.table.data_body_range
        first_row = data_body.row

        expected_symbols = sorted(df[PriceUpdater.SYMBOL_COLUMN].astype(str).tolist()[1:])

        # Hide just the first data row; everything else stays visible.
        equity_scenario.sheet.api.Rows(f"{first_row}:{first_row}").Hidden = True
        try:
            updater = PriceUpdater(equity_scenario, FakeFetcher())
            result, outcomes = updater.fetch_prices(PriceUpdateScope.VISIBLE)

            assert sorted(o.symbol for o in outcomes) == expected_symbols
        finally:
            equity_scenario.sheet.api.Rows(f"{first_row}:{first_row}").Hidden = False

    def test_no_visible_rows_returns_empty(self, equity_scenario):
        data_body = equity_scenario.table.data_body_range
        first_row = data_body.row
        last_row = first_row + data_body.shape[0] - 1

        # Hide every data row to trigger SpecialCells "nothing visible" exception path in _get_visible_rows.
        equity_scenario.sheet.api.Rows(f"{first_row}:{last_row}").Hidden = True
        try:
            updater = PriceUpdater(equity_scenario, FakeFetcher())
            result, outcomes = updater.fetch_prices(PriceUpdateScope.VISIBLE)

            assert outcomes == []
            assert result.total_symbols == 0
        finally:
            equity_scenario.sheet.api.Rows(f"{first_row}:{last_row}").Hidden = False


class TestWhenScopeIsAlSelected:
    def test_only_the_selected_row_is_included(self, equity_scenario):
        df = equity_scenario.df
        assert len(df) >= 2, "fixture needs at least 2 rows for this test to be meaningful"

        data_body = equity_scenario.table.data_body_range
        first_row = data_body.row
        symbol_ws_col = get_data_body_column(data_body, df, PriceUpdater.SYMBOL_COLUMN)

        expected_symbol = str(df[PriceUpdater.SYMBOL_COLUMN].iloc[0])
        equity_scenario.sheet.range((first_row, symbol_ws_col)).select()

        updater = PriceUpdater(equity_scenario, FakeFetcher())
        result, outcomes = updater.fetch_prices(PriceUpdateScope.SELECTED)

        assert [o.symbol for o in outcomes] == [expected_symbol]

    def test_selection_outside_symbol_column_returns_empty(self, equity_scenario):
        # Select a cell far outside the table entirely.
        equity_scenario.sheet.range("Z1").select()

        updater = PriceUpdater(equity_scenario, FakeFetcher())
        result, outcomes = updater.fetch_prices(PriceUpdateScope.SELECTED)

        assert outcomes == []
        assert result.total_symbols == 0