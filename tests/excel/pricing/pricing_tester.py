from tests.excel.infrastructure.fixtures.xl_test_scenario import xlTestScenario

SNAP_SC_WB = "resources/scenarios/snapshot SCs.xlsx"
SNAP_SC_WKS = "SNAP"
SNAP_SC_TABLE = "SnapshotTable"


class SnapshotScenarioTable(xlTestScenario):
    def __init__(self) -> None:
        super().__init__(SNAP_SC_WB, SNAP_SC_WKS, SNAP_SC_TABLE)
