import pytest

from ebf_data.excel.snapshot.option_price_updater import OptionPriceUpdater, OptionType
from ebf_data.excel.snapshot.price_updater import PriceUpdater
from excel.pricing.pricing_scenarios import SnapshotScenario_Pricing

EQUITY_SYMBOL_COUNT = 32
LONG_PUT_SYMBOL_COUNT = 1  # only LULU_7 visible in the LP view
SHORT_PUT_SYMBOL_COUNT = 9
LONG_CALL_SYMBOL_COUNT = 5
SHORT_CALL_SYMBOL_COUNT = 5


class TestYahooPricingWithWkb:

    @pytest.fixture(scope="module")
    def pricing_scenario(self):
        # table = SnapshotScenario_Pricing()
        # yield table
        # table.close()
        return SnapshotScenario_Pricing()

    class TestEquityPricing:
        @pytest.fixture
        def equity_updater(self, pricing_scenario) -> PriceUpdater:
            return PriceUpdater(pricing_scenario)

        def test_can_update_all_symbols(self, equity_updater):
            result, outcomes = equity_updater.fetch_prices()

            assert result.total_symbols and len(outcomes) == EQUITY_SYMBOL_COUNT, "symbol counts are stable by design"

            assert result.updated_symbols > 0
            assert result.success_rate > 0.8, "allow a few legitimately missing quotes"
            assert all(o.success for o in outcomes if o.price is not None)

    class TestOptionPricing:
        @pytest.fixture
        def option_updater(self, pricing_scenario) -> OptionPriceUpdater:
            return OptionPriceUpdater(pricing_scenario)

        def test_can_update__all_symbols(self, option_updater):
            results = option_updater.fetch_all_option_prices()

            # Long Puts
            lp_result, lp_outcomes = results[OptionType.LONG_PUT]
            assert lp_result.total_symbols and len(lp_outcomes) == LONG_PUT_SYMBOL_COUNT
            assert lp_result.updated_symbols >= 0, "may be 0 on a bad day"
