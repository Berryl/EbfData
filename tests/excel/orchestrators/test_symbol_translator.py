import pytest

from ebf_data.excel.cagr.cagr_table import CagrTable
from ebf_data.excel.orchestrators.symbol_translator import SymbolTranslator


class TestSymbolTranslator:
    @pytest.fixture
    def sut(self) -> SymbolTranslator:
        return SymbolTranslator(CagrTable())

    class TestToCagrValues:

        class TestWhenSymbolHasNoSuffix:
            def test_trade_id_is_max_id_found(self, sut: SymbolTranslator) -> None:
                result = sut.to_cagr_values("YUM")
                symbol = result[0]
                id_val = result[1]
                has_tranches = result[2]

                assert symbol == "YUM" and id_val == 1 and not has_tranches

        class TestWhenSymbolHasSuffixWithoutTranches:
            def test_trade_id_is_as_expected(self, sut: SymbolTranslator) -> None:
                result = sut.to_cagr_values("FCX_20")
                symbol = result[0]
                id_val = result[1]
                has_tranches = result[2]

                assert symbol == "FCX" and id_val == 20 and not has_tranches

        class TestWhenSymbolHasSuffixAndTranches:
            def test_trade_id_is_as_expected(self, sut: SymbolTranslator) -> None:
                result = sut.to_cagr_values("MARA_4.2")
                symbol = result[0]
                id_val = result[1]
                has_tranches = result[2]

                assert symbol == "MARA" and id_val == 4 and has_tranches
