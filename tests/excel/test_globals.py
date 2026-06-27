from ebf_data.excel.snapshot.snapshot_table import SNAPSHOT_WB
from ebf_data.excel.cagr.cagr_table import CAGR_WB


def test_workbook_names() -> None:
    assert CAGR_WB == "CAGR.xlsm"
    assert SNAPSHOT_WB == "snapshot.xlsm"
