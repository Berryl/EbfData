import pandas as pd
import pytest

from tests.excel.infrastructure.xl_base_tester import TesterTable


# region assertion helper
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


# endregion


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
        def test_only_the_targeted_row_is_updated(self, sut: TesterTable, target_index, label):
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

    class TestUpdateSlice:
        """
        Real-Excel proof that update_slice writes ONLY the targeted rows and
        leaves every other row in the table untouched.

        Covers slices at the start, middle, and end of the table, plus the
        columns-param path (partial-column write). The same
        pd_testing_assert_frame_equal assertion used in TestUpdateRow is
        the actual proof - it would catch any positional rewrite that
        scrambles untargeted rows.
        """

        @pytest.mark.parametrize("start_row, row_count, label", [
            (0, 3, "start"),  # slice at the top - no rows above
            (23, 4, "middle"),  # slice in the middle
            (47, 3, "end"),  # slice at the bottom - no rows below
        ])
        def test_update_slice_changes_only_targeted_rows(self, sut: TesterTable, start_row, row_count, label):
            sut.refresh()
            before = sut.df.copy()

            slice_df = pd.DataFrame({
                "RowLabel": [f"SLICE-{label}-{i}" for i in range(row_count)],
                "ValueA": [7777 + i for i in range(row_count)],
                "ValueB": [8888 + i for i in range(row_count)],
                "ValueC": [f"slice-{label}-{i}" for i in range(row_count)],
            })

            sut.update_slice(slice_df, start_row=start_row)

            sut.refresh()
            after = sut.df

            # targeted rows changed
            for i in range(row_count):
                assert after.iloc[start_row + i]["ValueA"] == 7777 + i
                assert after.iloc[start_row + i]["ValueC"] == f"slice-{label}-{i}"

            # every other row untouched
            target_positions = list(range(start_row, start_row + row_count))
            other_before = before.drop(index=before.index[target_positions])
            other_after = after.drop(index=after.index[target_positions])
            pd_testing_assert_frame_equal(other_before, other_after)

        def test_update_slice_with_columns_param_leaves_other_columns_alone(self, sut: TesterTable):
            """The columns param writes only specific columns per row -
            other columns in the same rows must be untouched."""
            sut.refresh()
            before = sut.df.copy()

            slice_df = pd.DataFrame({"ValueA": [5555, 6666]})

            sut.update_slice(slice_df, start_row=10, columns=["ValueA"])

            sut.refresh()
            after = sut.df

            # ValueA changed
            assert after.iloc[10]["ValueA"] == 5555
            assert after.iloc[11]["ValueA"] == 6666

            # ValueB, ValueC, RowLabel in those same rows untouched
            assert after.iloc[10]["RowLabel"] == before.iloc[10]["RowLabel"]
            assert after.iloc[10]["ValueC"] == before.iloc[10]["ValueC"]
            assert after.iloc[11]["RowLabel"] == before.iloc[11]["RowLabel"]
            assert after.iloc[11]["ValueC"] == before.iloc[11]["ValueC"]

            # all other rows untouched
            other_before = before.drop(index=before.index[[10, 11]])
            other_after = after.drop(index=after.index[[10, 11]])
            pd_testing_assert_frame_equal(other_before, other_after)
