"""
Tests for PriceUpdater against the SnapshotScenarioTable.

TestRealPriceUpdate: hits real yFinance - proves the full pipeline
end to end against a real workbook. Slow by nature; requires network.

TestMockedPriceUpdate: mocks _fetch_prices to test write mechanics
in isolation, without network dependency. (placeholder for now)
"""
import pytest
from unittest.mock import patch

from tests.excel.pricing.pricing_tester import SnapshotScenarioTable
from ebf_data.excel.snapshot.price_updater import PriceUpdater, PriceUpdateResult, PriceUpdateScope

# Symbols present in the scenario workbook's active rows.
ACTIVE_SYMBOLS = ["BA", "CCJ", "DRAM", "MARA", "PLTR", "AMZN", "PL", "INFQ", "B", "SOFI"]

# Static prices saved in the scenario workbook - used to confirm
# that update_prices() actually wrote new values.
SCENARIO_PRICES = {
    "BA": 227.70,
    "CCJ": 94.40,
    "DRAM": 65.00,
    "MARA": 13.00,
    "PLTR": 132.50,
    "AMZN": 244.00,
    "PL": 30.85,
    "INFQ": 13.40,
    "B": 38.00,
    "SOFI": 18.60,
}


class TestSnapshotPricingTable:
    @pytest.fixture(scope="module")
    def sut(self) -> SnapshotScenarioTable:
        return SnapshotScenarioTable()

    class TestReadStructure:
        def test_size(self, sut):
            assert len(sut.df) > 450
            assert len(sut.df.columns) > 200

        def test_headers_are_correct(self, sut):
            headers = sut.df.columns.tolist()
            assert "Symbol" in headers
            assert "SC DTE" in headers
            assert "SC Intrinsic Value" in headers
            assert "GUID Lookup" in headers

    class TestRealPriceUpdate:
        """
        Hits real yFinance. Slow, requires network. This is the test
        that actually proves the full pipeline works.
        """

        @pytest.fixture(scope="class")
        def updated_sut(self, sut: SnapshotScenarioTable):
            """
            Run update_prices() once for the whole class. Returns a tuple of
            (table, result) so benchmark and correctness tests share the same run.
            """
            result: PriceUpdateResult = PriceUpdater(sut).update_prices()
            sut.refresh()
            return sut, result

        def test_all_active_rows_have_a_price(self, updated_sut):
            sut, _ = updated_sut
            df = sut.df
            active = df[df["Position"].notna() & (df["Position"] != "")]
            assert not active.empty, "No active rows found in scenario workbook"

            for idx, row in active.iterrows():
                price = row["Last Price"]
                symbol = row["Symbol"]
                assert price is not None, f"{symbol}: Last Price is None after update"
                assert float(price) > 0, f"{symbol}: Last Price {price} is not positive"

        def test_prices_differ_from_scenario_static_values(self, updated_sut):
            """
            Prices should differ from the static values saved in the scenario
            workbook - confirms update_prices() actually wrote new values
            rather than leaving the static ones in place.

            Allows for a small tolerance since in rare cases a live price
            could coincidentally match the static value exactly.
            """
            sut, _ = updated_sut
            df = sut.df
            active = df[df["Position"].notna() & (df["Position"] != "")]

            changed = 0
            for idx, row in active.iterrows():
                base = row["Symbol"].split("_")[0]
                static = SCENARIO_PRICES.get(base)
                if static is None:
                    continue
                live = float(row["Last Price"])
                if abs(live - static) > 0.01:
                    changed += 1

            assert changed >= len(SCENARIO_PRICES) // 2, (
                f"Only {changed} prices changed from static values - "
                f"update_prices() may not have written correctly"
            )

        def test_run_info_dv_message_was_written(self, updated_sut):
            """Confirm the LastPriceRunInfo named range has a DV message after the run."""
            sut, _ = updated_sut
            try:
                run_info = sut.book.names["LastPriceRunInfo"].refers_to_range
                dv = run_info.api.Validation
                assert dv.ShowInput is True
                assert "YFinance Pricing" in (dv.InputTitle or "")
                assert "updated" in (dv.InputMessage or "").lower()
            except Exception as e:
                pytest.fail(f"Could not read LastPriceRunInfo DV message: {e}")

        def test_performance_benchmark(self, updated_sut):
            """
            Performance benchmark for update_prices(). Records elapsed time,
            symbol count, and per-symbol rate. Fails if the run took longer
            than a generous ceiling - meant to catch pathological regressions
            (e.g., falling back to the download path for every symbol) rather
            than enforce strict SLAs.

            Update MAX_SECONDS_PER_SYMBOL after a few real runs to reflect
            your actual baseline.
            """
            _, result = updated_sut

            MAX_SECONDS_PER_SYMBOL = 3.0  # generous - tighten after baselining

            print(f"\n--- Price Update Benchmark ---")
            print(f"  Symbols fetched : {result.total_symbols}")
            print(f"  Updated         : {result.updated}")
            print(f"  Failed          : {len(result.failed)} {result.failed or ''}")
            print(f"  Elapsed         : {result.elapsed_seconds:.2f}s")
            if result.total_symbols:
                print(f"  Per symbol      : {result.elapsed_seconds / result.total_symbols:.2f}s")
            print(f"  Success rate    : {result.success_rate:.0%}")

            assert result.total_symbols > 0, "No symbols were processed"
            assert result.elapsed_seconds < result.total_symbols * MAX_SECONDS_PER_SYMBOL, (
                f"update_prices() took {result.elapsed_seconds:.1f}s for "
                f"{result.total_symbols} symbols "
                f"({result.elapsed_seconds / result.total_symbols:.1f}s/symbol) - "
                f"expected under {MAX_SECONDS_PER_SYMBOL}s/symbol. "
                f"Is the fallback download path firing?"
            )

    class TestVisiblePriceUpdate:
        """
        Tests update_prices(scope=VISIBLE) against the scenario workbook,
        which is pre-filtered to 11 active SC rows. No filter manipulation is
        needed - the saved file already has the right filter applied.

        Key assertions:
        - Only the 11 visible rows are updated, not all 50 active rows
        - Performance is proportionally faster than ALL (fewer symbols)
        """

        # The scenario workbook is filtered to these 11 SC symbols
        VISIBLE_SYMBOL_COUNT = 11

        @pytest.fixture(scope="class")
        def visible_result(self, sut: SnapshotScenarioTable):
            result: PriceUpdateResult = PriceUpdater(sut).update_prices(
                scope=PriceUpdateScope.VISIBLE
            )
            sut.refresh()
            return sut, result

        def test_only_visible_rows_were_updated(self, visible_result):
            """
            With the filter applied to 11 SC rows, the updated count should be
            11 (one row per visible symbol), not 50 (all active rows).
            """
            _, result = visible_result
            assert result.updated == self.VISIBLE_SYMBOL_COUNT, (
                f"Expected {self.VISIBLE_SYMBOL_COUNT} updated rows (visible only), "
                f"got {result.updated} - VISIBLE scope may be falling back to ALL"
            )

        def test_visible_symbols_fetched_is_less_than_all(self, visible_result):
            """
            Symbol count should reflect only unique tickers in the visible
            rows, not all 38 symbols across all active positions.
            """
            _, result = visible_result
            assert 0 < result.total_symbols < 38, (
                f"Expected fewer than 38 symbols for VISIBLE scope, "
                f"got {result.total_symbols}"
            )

        def test_visible_scope_faster_than_all(self, visible_result):
            """
            Fetching ~11 symbols should be proportionally faster than
            fetching 38. Uses the established ALL baseline of ~1.75s/symbol.
            """
            _, result = visible_result

            MAX_SECONDS_PER_SYMBOL = 2.5

            print(f"\n--- Visible Scope Benchmark ---")
            print(f"  Symbols fetched : {result.total_symbols}")
            print(f"  Updated         : {result.updated}")
            print(f"  Elapsed         : {result.elapsed_seconds:.2f}s")
            if result.total_symbols:
                print(f"  Per symbol      : {result.elapsed_seconds / result.total_symbols:.2f}s")

            assert result.elapsed_seconds < result.total_symbols * MAX_SECONDS_PER_SYMBOL, (
                f"VISIBLE update took {result.elapsed_seconds:.1f}s for "
                f"{result.total_symbols} symbols - expected under "
                f"{MAX_SECONDS_PER_SYMBOL}s/symbol"
            )

        def test_run_info_scope_label_says_visible(self, visible_result):
            """DV summary message should record that VISIBLE scope was used."""
            sut, _ = visible_result
            try:
                run_info = sut.book.names["LastPriceRunInfo"].refers_to_range
                message = run_info.api.Validation.InputMessage or ""
                assert "visible" in message.lower(), (
                    f"Expected 'visible' in run summary message, got: {message!r}"
                )
            except Exception as e:
                pytest.fail(f"Could not read LastPriceRunInfo DV message: {e}")

    class TestMockedPriceUpdate:
        """
        Mocks _fetch_prices to test write mechanics without the network.
        Placeholder - to be expanded when fast CI coverage is needed.
        """
        pass