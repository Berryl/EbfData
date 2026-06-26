from ebf_data.excel.globals import CAGR_WB, SNAPSHOT_WB_NAME


def test_workbook_names() -> None:
    assert CAGR_WB == "CAGR.xlsm"
    assert SNAPSHOT_WB_NAME == "snapshot.xlsm"
