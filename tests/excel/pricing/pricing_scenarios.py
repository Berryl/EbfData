from tests.excel.infrastructure.fixtures.xl_test_scenario import xlTestScenario

SNAP_PRICING_TESTER = "resources/scenarios/snapshot_pricing_tester.xlsm"
SNAP_EQUITY_WB = "resources/scenarios/snapshot equity pricing.xlsx"
SNAP_WKS = "SNAP"
SNAP_TABLE = "SnapshotTable"


class SnapshotScenario_Pricing(xlTestScenario):
    """
    Scenario for testing both equity and option pricing.
    """
    def __init__(self) -> None:
        super().__init__(SNAP_PRICING_TESTER, SNAP_WKS, SNAP_TABLE)


class SnapshotScenario_EquityPricing(xlTestScenario):
    """
    Scenario for testing equity pricing.
    """
    def __init__(self) -> None:
        super().__init__(SNAP_EQUITY_WB, SNAP_WKS, SNAP_TABLE)

