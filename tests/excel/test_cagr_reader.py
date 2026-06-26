# test_cagr_reader.py
import pytest

from ebf_data.excel.cagr_reader import CagrReader


class TestCagrReader:
    @pytest.fixture
    def sut(self) -> CagrReader:
        return CagrReader()

    class TestReadTableValues:
        def test_can_read_cagr_table(self, sut: CagrReader):
            values = sut.read_table_values()

            assert values
            assert len(values) > 6000
            assert values[0]

    class TestHeaders:
        def test_headers_are_correct(self, sut: CagrReader):
            headers = sut.read_table_values()[0]
            assert "Symbol" in headers
