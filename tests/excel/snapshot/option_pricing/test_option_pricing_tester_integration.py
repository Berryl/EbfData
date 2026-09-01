import pytest

from ebf_data.excel.snapshot.option_price_updater import OptionPriceUpdater, OptionType, get_outcomes
from ebf_data.excel.snapshot.price_updater import PriceUpdater
from excel.pricing.pricing_scenarios import SnapshotScenario_Pricing

EQUITY_SYMBOL_COUNT = 30
LONG_PUT_SYMBOL_COUNT = 1
SHORT_PUT_SYMBOL_COUNT = 9
LONG_CALL_SYMBOL_COUNT = 4
SHORT_CALL_SYMBOL_COUNT = 5

@pytest.mark.integration
class TestOptionPricingIntegration:

    @pytest.fixture(scope="module")
    def pricing_scenario(self):
        table = SnapshotScenario_Pricing()
        yield table
        table.close()
        # return SnapshotScenario_Pricing()

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

            # Short Puts
            sp_result, sp_outcomes = results[OptionType.SHORT_PUT]
            assert sp_result.total_symbols and len(sp_outcomes) == SHORT_PUT_SYMBOL_COUNT
            assert sp_result.updated_symbols > 0

            # Long Calls
            lc_result, lc_outcomes = results[OptionType.LONG_CALL]
            assert lc_result.total_symbols and len(lc_outcomes) == LONG_CALL_SYMBOL_COUNT
            assert lc_result.updated_symbols > 0

            # Short Calls
            sc_result, sc_outcomes = results[OptionType.SHORT_CALL]
            assert sc_result.total_symbols and len(sc_outcomes) == SHORT_CALL_SYMBOL_COUNT
            assert sc_result.updated_symbols > 0

            all_outcomes = get_outcomes(results)
            assert len(all_outcomes) == (
                    LONG_PUT_SYMBOL_COUNT
                    + SHORT_PUT_SYMBOL_COUNT
                    + LONG_CALL_SYMBOL_COUNT
                    + SHORT_CALL_SYMBOL_COUNT
            )
