from tests.excel.infrastructure.fixtures.xl_test_scenario import xlTestScenario

SNAP_EQUITY_WB = "resources/scenarios/snapshot equity pricing.xlsx"
SNAP_SC_WB = "resources/scenarios/snapshot SC pricing.xlsx"
SNAP_SP_WB = "resources/scenarios/snapshot SP pricing.xlsx"
SNAP_BAD_SYMBOL_WB = "resources/scenarios/snapshot With Bad Symbol.xlsx"
SNAP_WKS = "SNAP"
SNAP_TABLE = "SnapshotTable"


class SnapshotScenario_EquityPricing(xlTestScenario):
    """
    Scenario for testing equity pricing.
    """
    def __init__(self) -> None:
        super().__init__(SNAP_EQUITY_WB, SNAP_WKS, SNAP_TABLE)


class SnapshotScenario_WithBadSymbol(xlTestScenario):
    """
    Scenario for testing how gracefully pricing handles symbols that return None from the pricing engine.
    """
    def __init__(self) -> None:
        super().__init__(SNAP_BAD_SYMBOL_WB, SNAP_WKS, SNAP_TABLE)

class SnapshotScenario_ShortPuts(xlTestScenario):
    """
    Scenario for testing short calls.
    """
    def __init__(self) -> None:
        super().__init__(SNAP_SP_WB, SNAP_WKS, SNAP_TABLE)
