"""
xlTable subclass for disposable test scenario workbooks.

Kept deliberately separate from xlTableBase.py (the production base
class) because this class's whole reason for existing - owning its own
open/close lifecycle - is something production tables must NEVER do.
Production tables (CagrTable, SnapshotTable, etc.) always go through
find_open_book, which only attaches and never opens or closes anything.
Putting this in its own module keeps that boundary visible at the file
level, not just in a docstring buried inside a much bigger class.
"""
from ebf_data.excel.infrastructure.scenario_workbook import open_scenario_workbook, close_scenario_workbook
from ebf_data.excel.infrastructure.xl_table_base import xlTable


class xlTestScenario(xlTable):
    """
    xlTable subclass for disposable test scenario workbooks.

    Owns its own open/close lifecycle - the test fixture only needs to
    construct and close this object; no separate open/close choreography
    required. Supports use as a context manager.

    ONLY for test workbooks that are safe to open and close freely.
    NEVER for production workbooks (CAGR.xlsm, snapshot.xlsm, etc.).

    Usage (fixture):
        @pytest.fixture(scope="module")
        def sut():
            table = TesterTable()
            yield table
            table.close()

    Usage (context manager):
        with TesterTable() as table:
            assert len(table.df) == 50
    """

    def __init__(self, workbook_path: str, sheet_name: str, table_name: str) -> None:
        book = open_scenario_workbook(workbook_path)
        super().__init__(book, sheet_name, table_name)

    def close(self, save_changes: bool = False) -> None:
        """
        Close the scenario workbook.

        Args:
            save_changes: if True, saves before closing. Default False
                so the file is always clean for the next test run.
        """
        close_scenario_workbook(self.book, save_changes)

    def __enter__(self) -> "xlTestScenario":
        return self

    def __exit__(self, *_) -> None:
        self.close()