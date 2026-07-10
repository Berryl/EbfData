from tests.excel.infrastructure.fixtures.xl_test_scenario import xlTestScenario

XL_BASE_WB = "resources/testing/xlBaseTester.xlsx"
XL_BASE_WKS = "Sheet1"
XL_BASE_TABLE = "GenericTable"


class TesterTable(xlTestScenario):
    def __init__(self) -> None:
        super().__init__(XL_BASE_WB, XL_BASE_WKS, XL_BASE_TABLE)
