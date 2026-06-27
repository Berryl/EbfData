from ebf_data.excel.globals import SNAPSHOT_WB
from ebf_data.excel.cagr.cagr_table import CAGR_WB


def test_workbook_names() -> None:
    assert CAGR_WB == "CAGR.xlsm"
    assert SNAPSHOT_WB == "snapshot.xlsm"
