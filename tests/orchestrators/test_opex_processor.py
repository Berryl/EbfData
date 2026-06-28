import pytest

from ebf_data.excel.cagr.cagr_table import CagrTable
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable
from ebf_data.orchestrators.opex_processor import OpexProcessor


class TestOpexProcessor:
    @pytest.fixture
    def sut(self) -> OpexProcessor:
        return OpexProcessor(CagrTable(), SnapshotTable())