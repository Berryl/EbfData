import pytest

from xl_base_tester import TesterTable


def pd_testing_assert_frame_equal(left, right):
    """
    Thin wrapper so the import only happens where it's used, and the
    failure message is explicit about what this assertion actually means
    if it fails.
    """
    import pandas.testing as pdt
    try:
        pdt.assert_frame_equal(left, right, check_dtype=False)
    except AssertionError as e:
        raise AssertionError(
            "update_row corrupted a row it was never supposed to touch. "
            "This is the exact failure mode that damaged production data - "
            "see the original assertion error below.\n\n" + str(e)
        ) from e


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

    class TestUpdateRow:

        @pytest.mark.parametrize("target_index, label", [
            (0, "Row-000"),  # first row - no neighbor above
            (25, "Row-025"),  # middle row
            (49, "Row-049"),  # last row - no neighbor below
        ])
        def test_update_row_changes_only_the_targeted_row(self, sut: TesterTable, target_index, label):
            sut.refresh()
            before = sut.df.copy()
            assert before.loc[target_index, "RowLabel"] == label, (
                "Sanity check failed - row layout doesn't match what this test expects. "
                "Did the workbook get modified outside this test?"
            )

            sut.update_row(target_index, {"ValueA": 9999, "ValueC": "CHANGED"})

            sut.refresh()
            after = sut.df

            # The targeted row changed exactly as requested
            assert after.loc[target_index, "ValueA"] == 9999
            assert after.loc[target_index, "ValueC"] == "CHANGED"
            assert after.loc[target_index, "RowLabel"] == label, "RowLabel should be untouched"

            # EVERY other row must be byte-for-byte identical to before -
            # this is the actual proof the fix works, not just that the
            # targeted row happened to update correctly.
            other_rows_before = before.drop(index=target_index)
            other_rows_after = after.drop(index=target_index)
            pd_testing_assert_frame_equal(other_rows_before, other_rows_after)
