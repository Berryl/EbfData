import pytest

from ebf_data.excel.pricing.pricing_helpers import PriceUpdateResult


class TestPriceUpdateResult:
    class TestSuccessRate:
        @pytest.mark.parametrize("total, failed, expectation", [
            (10, [], 1.0),
            (10, ["symbol1", "symbol2"], 0.8),
        ])
        def test_when_set_as_initializer_args(self, total, failed, expectation):
            sut = PriceUpdateResult(total_symbols=total, failed=failed)
            assert sut.success_rate == expectation

        @pytest.mark.parametrize("total, failed, expectation", [
            (10, [], 1.0),
            (10, ["symbol1", "symbol2"], 0.8),
        ])
        def test_when_set_post_initialization(self, total, failed, expectation):
            sut = PriceUpdateResult()
            sut.total_symbols = total
            sut.failed = failed
            assert sut.success_rate == expectation

    class TestUpdatedSymbols:
        @pytest.fixture
        def sut(self) -> PriceUpdateResult:
            return PriceUpdateResult(total_symbols=10)

        @pytest.mark.parametrize("failures, updated", [([], 10), (["symbol1", "symbol2"], 8)])
        def test_property_computes_updated_symbols(self, sut: PriceUpdateResult, failures, updated):
            sut.failed = failures
            assert sut.updated_symbols == updated
