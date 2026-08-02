"""
Unit tests for PriceUpdater.fetch_prices().

"""
import pandas as pd

from ebf_data.excel.pricing.price_fetcher import PriceFetcher
from ebf_data.excel.snapshot.price_updater import (
    PriceUpdater,
    PriceUpdateScope,
    SymbolPriceOutcome,
    _extract_base_symbol,
)


# region helpers
class FakeFetcher(PriceFetcher):
    """Returns a fixed price map and records each call's ticker list,
    so tests can assert on fetch deduplication without hitting yfinance."""

    def __init__(self, prices: dict[str, float | None]) -> None:
        self._prices = prices
        self.calls: list[list[str]] = []

    def fetch_prices(self, tickers: list[str]) -> dict[str, float | None]:
        self.calls.append(list(tickers))
        return {t: self._prices.get(t) for t in tickers}


class FakeSnapshot:
    """Minimal SnapshotTable stand-in. Only .refresh() and .df are touched
    for ALL-scope fetching, so that's all this fake needs to provide."""

    def __init__(self, df: pd.DataFrame) -> None:
        self.df = df
        self.refresh_called = False

    def refresh(self) -> None:
        self.refresh_called = True


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)
# endregion


class TestPriceUpdater:
    class TestExtractBaseSymbol:

        def test_when_symbol_is_unadorned_it_is_unchanged(self):
            assert _extract_base_symbol("AAPL") == "AAPL"

        def test_when_symbol_has_a_simple_suffix_it_is_stripped(self):
            assert _extract_base_symbol("CCJ_17") == "CCJ"

        def test_when_suffix_has_complex_suffix_all_parts_are_stripped(self):
            assert _extract_base_symbol("MARA_4.1") == "MARA"

    class TestFetchPricesWhenAllScope:
        def test_when_no_rows_have_a_position_returns_empty_result_and_outcomes(self):
            snapshot = FakeSnapshot(_df([
                {"Symbol": "AAPL", "Position": ""},
                {"Symbol": "MSFT", "Position": None},
            ]))
            fetcher = FakeFetcher({})
            sut = PriceUpdater(snapshot, fetcher)

            result, outcomes = sut.fetch_prices(PriceUpdateScope.ALL)

            assert result.total_symbols == 0
            assert outcomes == []
            assert snapshot.refresh_called
            assert fetcher.calls == []

        def test_suffixed_symbols_sharing_a_base_ticker_are_fetched_once(self):
            snapshot = FakeSnapshot(_df([
                {"Symbol": "CCJ_17", "Position": 10},
                {"Symbol": "CCJ_4.1", "Position": 5},
            ]))
            fetcher = FakeFetcher({"CCJ": 55.5})
            updater = PriceUpdater(snapshot, fetcher)

            result, outcomes = updater.fetch_prices(PriceUpdateScope.ALL)

            assert fetcher.calls == [["CCJ"]]
            assert result.total_symbols == 1
            assert {o.symbol for o in outcomes} == {"CCJ_17", "CCJ_4.1"}
            assert all(o.price == 55.5 and o.success for o in outcomes)

        def test_duplicate_identical_symbol_rows_each_get_their_own_outcome(self):
            snapshot = FakeSnapshot(_df([
                {"Symbol": "PLTR", "Position": 100},
                {"Symbol": "PLTR", "Position": 50},
            ]))
            fetcher = FakeFetcher({"PLTR": 12.34})
            updater = PriceUpdater(snapshot, fetcher)

            result, outcomes = updater.fetch_prices(PriceUpdateScope.ALL)

            assert fetcher.calls == [["PLTR"]]
            assert len(outcomes) == 2
            assert all(o.symbol == "PLTR" and o.price == 12.34 and o.success for o in outcomes)

        def test_failed_ticker_produces_an_unsuccessful_outcome_and_is_recorded(self):
            snapshot = FakeSnapshot(_df([{"Symbol": "ZZZZ", "Position": 1}]))
            fetcher = FakeFetcher({"ZZZZ": None})
            updater = PriceUpdater(snapshot, fetcher)

            result, outcomes = updater.fetch_prices(PriceUpdateScope.ALL)

            assert result.failed == ["ZZZZ"]
            assert outcomes == [SymbolPriceOutcome(symbol="ZZZZ", price=None, success=False)]
            assert result.updated_symbols == 0
            assert result.success_rate == 0.0

        def test_mixed_success_and_failure_aggregate_counts(self):
            snapshot = FakeSnapshot(_df([
                {"Symbol": "AAPL", "Position": 10},
                {"Symbol": "ZZZZ", "Position": 1},
            ]))
            fetcher = FakeFetcher({"AAPL": 200.0, "ZZZZ": None})
            updater = PriceUpdater(snapshot, fetcher)

            result, outcomes = updater.fetch_prices(PriceUpdateScope.ALL)

            assert result.total_symbols == 2
            assert result.failed == ["ZZZZ"]
            assert result.updated_symbols == 1
            assert result.success_rate == 0.5
            assert len(outcomes) == 2

        def test_blank_and_none_positions_are_excluded_nonblank_is_included(self):
            snapshot = FakeSnapshot(_df([
                {"Symbol": "AAPL", "Position": 10},
                {"Symbol": "MSFT", "Position": ""},
                {"Symbol": "GOOG", "Position": None},
            ]))
            fetcher = FakeFetcher({"AAPL": 200.0})
            updater = PriceUpdater(snapshot, fetcher)

            result, outcomes = updater.fetch_prices(PriceUpdateScope.ALL)

            assert result.total_symbols == 1
            assert [o.symbol for o in outcomes] == ["AAPL"]
