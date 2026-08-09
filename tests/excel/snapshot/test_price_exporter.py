import json
from unittest.mock import MagicMock

import pytest
from ebf_core.fileutil.project_file_locator import ProjectFileLocator

from ebf_data.excel.pricing.pricing_helpers import (
    PriceUpdateResult,
    SymbolPriceOutcome,
)
from ebf_data.excel.snapshot.option_price_updater import OptionType
from ebf_data.excel.snapshot.price_exporter import (
    PriceExporter,
    EQUITY,
)


# region helpers
def _outcome(symbol: str, price: float | None, success: bool) -> SymbolPriceOutcome:
    return SymbolPriceOutcome(symbol=symbol, price=price, success=success)


def _equity_fetch(outcomes: list[SymbolPriceOutcome]) -> tuple[PriceUpdateResult, list[SymbolPriceOutcome]]:
    result = PriceUpdateResult(
        total_symbols=len({o.symbol for o in outcomes}),
        failed=[o.symbol for o in outcomes if not o.success],
    )
    return result, outcomes


def _option_fetch(
        sc: list[SymbolPriceOutcome] | None = None,
        sp: list[SymbolPriceOutcome] | None = None,
        lc: list[SymbolPriceOutcome] | None = None,
        lp: list[SymbolPriceOutcome] | None = None,
) -> dict:
    def _pair(outs: list[SymbolPriceOutcome] | None):
        outs = outs or []
        result = PriceUpdateResult(
            total_symbols=len({o.symbol for o in outs}),
            failed=[o.symbol for o in outs if not o.success],
        )
        return result, outs

    return {
        OptionType.SHORT_CALL: _pair(sc),
        OptionType.SHORT_PUT: _pair(sp),
        OptionType.LONG_CALL: _pair(lc),
        OptionType.LONG_PUT: _pair(lp),
    }


# endregion



class TestPriceExporter:

    @pytest.fixture
    def mock_snapshot(self):
        snap = MagicMock()
        snap.book.name = "TestPricing.xlsx"
        snap.sheet.name = "Snapshot"
        snap.name = "tblSnapshot"
        return snap

    @pytest.fixture
    def tmp_locator(self, tmp_path):
        """ProjectFileLocator stand-in that resolves everything under tmp_path."""
        locator = MagicMock()

        def _get(relpath, must_exist=False):  # noqa param is necessary
            return tmp_path / relpath

        locator.get_project_file.side_effect = _get
        return locator

    @pytest.fixture
    def sut(self, mock_snapshot, tmp_locator):
        return PriceExporter(snapshot=mock_snapshot, locator=tmp_locator)

    def test_json_has_correct_structure(self, sut, tmp_path):
        equity = _equity_fetch([
            _outcome("AAPL", 200.0, True),
            _outcome("ZZZZ", None, False),
        ])
        options = _option_fetch(
            sc=[_outcome("AAPL260918C00200000", 1.25, True)],
            sp=[_outcome("AAPL260918P00180000", 0.95, True)],
            lc=[_outcome("MSFT260918C00400000", 2.40, True)],
            lp=[_outcome("MSFT260918P00350000", None, False)],
        )

        path = sut.export(equity, options)

        assert path.exists()
        assert path.name == "TestPricing.json"
        data = json.loads(path.read_text(encoding="utf-8"))

        # Identity
        assert data["identity"]["wkb"] == "TestPricing.xlsx"
        assert data["identity"]["wks"] == "Snapshot"
        assert data["identity"]["tbl"] == "tblSnapshot"
        assert "created" in data["identity"]

        # Equity section – failure dropped from prices list
        eq = data["equity"]
        assert eq["symbol_column"] == EQUITY.symbol_column
        assert eq["target_column"] == EQUITY.target_column
        assert eq["prices"] == [{"symbol": "AAPL", "price": 200.0}]
        assert eq["summary"] == {
            "total": 2,
            "succeeded": 1,
            "failed": 1,
            "failed_symbols": ["ZZZZ"],
        }

        # Option sections present and correctly keyed
        for key in ("short_calls", "short_puts", "long_calls", "long_puts"):
            assert key in data

        assert data["short_calls"]["prices"] == [
            {"symbol": "AAPL260918C00200000", "price": 1.25}
        ]
        assert data["long_puts"]["prices"] == []  # only failure
        assert data["long_puts"]["summary"]["failed_symbols"] == ["MSFT260918P00350000"]

    def test_empty_outcomes_produce_empty_price_lists(self, sut):
        equity = _equity_fetch([])
        options = _option_fetch()  # all empty

        path = sut.export(equity, options)
        data = json.loads(path.read_text(encoding="utf-8"))

        for section in ("equity", "short_calls", "short_puts", "long_calls", "long_puts"):
            assert data[section]["prices"] == []
            assert data[section]["summary"]["total"] == 0
            assert data[section]["summary"]["succeeded"] == 0
            assert data[section]["summary"]["failed"] == 0

    def test_duplicate_symbols_appear_in_prices(self, sut):
        """Exporter must preserve one entry per outcome row (duplicates kept)."""
        equity = _equity_fetch([
            _outcome("PLTR", 12.34, True),
            _outcome("PLTR", 12.34, True),
        ])
        options = _option_fetch()

        path = sut.export(equity, options)
        data = json.loads(path.read_text(encoding="utf-8"))

        assert len(data["equity"]["prices"]) == 2
        assert data["equity"]["summary"]["total"] == 2
        assert data["equity"]["summary"]["succeeded"] == 2

    def test_write_is_atomic(self, sut, tmp_path):
        """The final file appears only after the replacement; no partial .tmp left behind."""
        equity = _equity_fetch([_outcome("AAPL", 150.0, True)])
        options = _option_fetch()

        path = sut.export(equity, options)

        assert path.exists()
        assert path.suffix == ".json"
        # No leftover temporary file
        assert not list(path.parent.glob("*.tmp"))

    def test_second_export_overwrites_the_first(self, mock_snapshot, tmp_path):
        (tmp_path / ".git").mkdir()
        locator = ProjectFileLocator().with_project_root(tmp_path)
        sut = PriceExporter(snapshot=mock_snapshot, locator=locator)

        sut.export(_equity_fetch([_outcome("AAPL", 100.0, True)]), _option_fetch())
        path = sut.export(_equity_fetch([_outcome("MSFT", 300.0, True)]), _option_fetch())

        matches = list(path.parent.glob("TestPricing.json"))
        assert len(matches) == 1  # not duplicated

        data = json.loads(path.read_text())
        assert data["equity"]["prices"] == [{"symbol": "MSFT", "price": 300.0}]

    def test_missing_option_type_key_raises(self, mock_snapshot):
        locator = MagicMock()
        locator.get_project_file.side_effect = lambda relpath, must_exist=False: relpath

        sut = PriceExporter(snapshot=mock_snapshot, locator=locator)

        incomplete_options = {
            OptionType.SHORT_CALL: (PriceUpdateResult(), []),
            OptionType.SHORT_PUT: (PriceUpdateResult(), []),
            OptionType.LONG_CALL: (PriceUpdateResult(), []),
            # LONG_PUT missing
        }

        with pytest.raises(KeyError):
            sut.export(_equity_fetch([]), incomplete_options)

    def test_pending_folder_not_found_raises_runtime_error(self, mock_snapshot):
        locator = MagicMock()
        locator.get_project_file.return_value = None

        sut = PriceExporter(snapshot=mock_snapshot, locator=locator)

        with pytest.raises(RuntimeError, match="Could not resolve pending path"):
            sut.export(_equity_fetch([]), _option_fetch())



