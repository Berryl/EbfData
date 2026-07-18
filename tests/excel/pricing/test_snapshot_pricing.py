"""
Tests for PriceUpdater against the SnapshotScenarioTable.

TestRealPriceUpdate: hits real yFinance - proves the full pipeline
end to end against a real workbook. Slow by nature; requires network.

TestMockedPriceUpdate: mocks _fetch_prices to test write mechanics
in isolation, without network dependency. (placeholder for now)
"""
import pytest

from ebf_data.excel.snapshot.price_updater import PriceUpdater, PriceUpdateResult, PriceUpdateScope
from tests.excel.pricing.pricing_tester import SnapshotScenarioTable

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

    class TestPriceUpdater:
        """
        Hits real yFinance. Slow, requires network. This is the test
        that actually proves the full pipeline works.
        """

        @pytest.fixture(scope="class")
        def updated_sut(self, sut: SnapshotScenarioTable) -> tuple[SnapshotScenarioTable, PriceUpdateResult]:
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

        def test_prices_differ_from_initial_scenario_static_values(self, updated_sut):
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

        def test_summary_run_info_message_was_written(self, updated_sut):
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

            MAX_SECONDS_PER_SYMBOL = 3.0  # generous - tighten after base-lining

            print(f"\n--- Price Update Benchmark ---")
            print(f"  Symbols fetched : {result.total_symbols}")
            print(f"  Updated         : {result.updated_rows}")
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

        # 11 visible SC rows but only 10 unique base tickers -
        # PLTR appears twice (PLTR_16 and PLTR_17), both mapping to PLTR
        VISIBLE_ROW_COUNT = 11
        VISIBLE_SYMBOL_COUNT = 10

        @pytest.fixture(scope="class")
        def visible_result(self, sut: SnapshotScenarioTable):
            result: PriceUpdateResult = PriceUpdater(sut).update_prices(
                scope=PriceUpdateScope.VISIBLE
            )
            sut.refresh()
            return sut, result

        def test_only_visible_rows_were_updated(self, visible_result):
            """
            The scenario workbook is filtered to 11 SC rows with 10 unique
            base tickers (PLTR appears as both PLTR_16 and PLTR_17).
            total_symbols proves VISIBLE scope saw only the filtered rows.
            updated == 11 because PLTR's price is written to both rows.
            """
            _, result = visible_result
            assert result.total_symbols == self.VISIBLE_SYMBOL_COUNT, (
                f"Expected {self.VISIBLE_SYMBOL_COUNT} unique tickers, "
                f"got {result.total_symbols} - VISIBLE scope may be falling back to ALL"
            )
            assert result.updated_rows == self.VISIBLE_ROW_COUNT, (
                f"Expected {self.VISIBLE_ROW_COUNT} rows updated, got {result.updated_rows}"
            )
            assert result.failed == [], (
                f"Expected no failures, got {result.failed}"
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
            Fetching 11 symbols should complete faster than the ALL baseline
            of ~65s. yFinance has a fixed per-batch overhead, so the per-symbol rate
            may not improve proportionally, but we should expect a lower total elapsed time.
            """
            _, result = visible_result

            ALL_BASELINE_SECONDS = 70.0  # established from prior ALL runs

            print(f"\n--- Visible Scope Benchmark ---")
            print(f"  Symbols fetched : {result.total_symbols}")
            print(f"  Updated         : {result.updated_rows}")
            print(f"  Elapsed         : {result.elapsed_seconds:.2f}s")
            if result.total_symbols:
                print(f"  Per symbol      : {result.elapsed_seconds / result.total_symbols:.2f}s")

            assert result.elapsed_seconds < ALL_BASELINE_SECONDS, (
                f"VISIBLE update took {result.elapsed_seconds:.1f}s - "
                f"expected under ALL baseline of {ALL_BASELINE_SECONDS}s"
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

    class TestSelectedPriceUpdate:
        """
        Tests update_prices(scope=SELECTED) against the scenario workbook.

        The fixture programmatically selects known Symbol cells before
        invoking update_prices(), simulating the trader selecting one or
        more rows in Excel before triggering a price update.

        The scenario workbook is filtered (11 visible rows), so non-contiguous
        selections produce multi-area ranges - exercising the Areas loop in
        _rows_in_selection.
        """

        # Worksheet constants derived from the scenario workbook layout.
        # Symbol is column B (col 2); row numbers are worksheet rows.
        SYMBOL_WS_COL = 2
        BA_WS_ROW = 161
        CCJ_WS_ROW = 166

        def _select_ws_rows(self, sut: SnapshotScenarioTable, ws_rows: list[int]) -> None:
            sheet = sut.sheet.activate()
            first = sheet.range((ws_rows[0], self.SYMBOL_WS_COL))
            if len(ws_rows) == 1:
                first.select()
                return
            union = first.api
            for r in ws_rows[1:]:
                union = sheet.api.Application.Union(union, sheet.range((r, self.SYMBOL_WS_COL)).api)
            union.Select()

        @pytest.fixture(scope="class")
        def single_row_result(self, sut: SnapshotScenarioTable) -> tuple[SnapshotScenarioTable, PriceUpdateResult]:
            """Select BA only, run the SELECTED scope."""
            self._select_ws_rows(sut, [self.BA_WS_ROW])
            result: PriceUpdateResult = PriceUpdater(sut).update_prices(scope=PriceUpdateScope.SELECTED)
            sut.refresh()
            return sut, result

        @pytest.fixture(scope="class")
        def two_row_result(self, sut: SnapshotScenarioTable) -> tuple[SnapshotScenarioTable, PriceUpdateResult]:
            """Select BA + CCJ_17 (non-contiguous in worksheet), run SELECTED scope."""
            self._select_ws_rows(sut, [self.BA_WS_ROW, self.CCJ_WS_ROW])
            result: PriceUpdateResult = PriceUpdater(sut).update_prices(scope=PriceUpdateScope.SELECTED)
            sut.refresh()
            return sut, result

        class TestWhenSingleSymbolSelected:

            def test_symbol_count_is_1(self, single_row_result):
                """Only BA selected - exactly one unique ticker fetched."""
                _, result = single_row_result
                assert result.total_symbols == 1, f"Expected 1 symbol, got {result.total_symbols}"

            def test_row_is_updated(self, single_row_result):
                """BA maps to one row - exactly one row written."""
                _, result = single_row_result
                assert result.updated_rows == 1, f"Expected 1 row updated, got {result.updated_rows}"

            def test_no_failures(self, single_row_result):
                _, result = single_row_result
                assert result.failed == []

            def test_updated_price_is_positive(self, single_row_result):
                sut, _ = single_row_result
                df = sut.df
                ba_rows = df[df["Symbol"] == "BA"]
                assert not ba_rows.empty
                price = float(ba_rows.iloc[0]["Last Price"])
                assert price > 0, f"BA Last Price is not positive: {price}"

        class TestWhenTwoConsecutiveSymbolsSelected:

            def test_symbol_count_is_2(self, two_row_result):
                """BA + CCJ_17 selected - two unique tickers (BA, CCJ)."""
                _, result = two_row_result
                assert result.total_symbols == 2, (
                    f"Expected 2 symbols, got {result.total_symbols}"
                )

            def test_rows_are_updated(self, two_row_result):
                """BA and CCJ_17 each map to one row - two rows written."""
                _, result = two_row_result
                assert result.updated_rows == 2, f"Expected 2 rows updated, got {result.updated_rows}"

            def test_no_failures(self, two_row_result):
                _, result = two_row_result
                assert result.failed == []

            def test_updated_prices_are_positive(self, two_row_result):
                sut, _ = two_row_result
                df = sut.df
                for symbol in ("BA", "CCJ_17"):
                    rows = df[df["Symbol"] == symbol]
                    assert not rows.empty, f"{symbol} not found in df"
                    price = float(rows.iloc[0]["Last Price"])
                    assert price > 0, f"{symbol} Last Price is not positive: {price}"

            def test_run_info_scope_label_states_selected(self, two_row_result):
                """DV summary message should record that the SELECTED scope was used."""
                sut, _ = two_row_result
                try:
                    run_info = sut.book.names["LastPriceRunInfo"].refers_to_range
                    message = run_info.api.Validation.InputMessage or ""
                    assert "selected" in message.lower(), f"Expected 'selected' in run summary message, got: {message!r}"
                except Exception as e:
                    pytest.fail(f"Could not read LastPriceRunInfo DV message: {e}")


    class TestMockedPriceUpdate:
        """
        Mocks _fetch_prices to test write mechanics without the network.
        Placeholder - to be expanded when fast CI coverage is needed.
        """
        pass
