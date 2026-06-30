import pytest

from ebf_data.excel.infrastructure.xl_base_tester import TesterTable


class TestTesterTable:
    @pytest.fixture(scope="module")
    def sut(self) -> TesterTable:
        table = TesterTable()
        yield table
        table.close()

    class TestReadStructure:
        def test_size(self, sut: TesterTable):
            assert len(sut.df) == 50
            assert len(sut.df.columns) == 4

        def test_headers_are_correct(self, sut: TesterTable):
            headers = sut.df.columns.tolist()
            assert "RowLabel" in headers
            assert "ValueA" in headers
            assert "ValueB" in headers
            assert "ValueC" in headers