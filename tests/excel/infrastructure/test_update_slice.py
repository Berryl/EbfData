from unittest.mock import MagicMock

import pandas as pd
import pytest

from ebf_data.excel.infrastructure.xl_table_base import xlTable


def make_table(df: pd.DataFrame) -> xlTable:
    """
    Build an xlTable backed by a real pandas DataFrame, with the Excel
    boundary (book/sheet/table) fully mocked. No real Excel/COM is touched.

    table.range.options(...).value is wired to return the SAME df whenever
    refresh() is called, so refresh() doesn't clobber the test's carefully
    constructed DataFrame with an unconfigured MagicMock.

    safe_data_body_range is mocked to return a MagicMock indexable range,
    so cell writes can be inspected without real Excel.
    """
    t = xlTable.__new__(xlTable)
    t.book = MagicMock()
    t.sheet = MagicMock()
    t.table = MagicMock()
    t.table.data_body_range = MagicMock()
    t.table.range.options.return_value.value = df.copy()
    t.name = "TestTable"
    t._df = df
    return t


def sample_df() -> pd.DataFrame:
    return pd.DataFrame({
        "Label": [f"Row-{i:03d}" for i in range(10)],
        "ValueA": list(range(10)),
        "ValueB": [str(i) for i in range(10)],
    }, index=[100 + i for i in range(10)])  # deliberately non-trivial index


class TestUpdateSlice:

    def test_writes_contiguous_block_starting_at_position(self):
        table = make_table(sample_df())
        slice_df = pd.DataFrame({
            "Label": ["X", "Y"],
            "ValueA": [999, 888],
            "ValueB": ["a", "b"],
        })

        table.update_slice(slice_df, start_row=3)

        assert table._df.iloc[3]["ValueA"] == 999
        assert table._df.iloc[4]["ValueA"] == 888

    def test_does_not_touch_rows_outside_the_slice(self):
        table = make_table(sample_df())
        before = table._df.copy()
        slice_df = pd.DataFrame({
            "Label": ["X", "Y"],
            "ValueA": [999, 888],
            "ValueB": ["a", "b"],
        })

        table.update_slice(slice_df, start_row=3)

        # rows 0-2 and 5-9 must be untouched
        for i in list(range(0, 3)) + list(range(5, 10)):
            assert table._df.iloc[i]["ValueA"] == before.iloc[i]["ValueA"]
            assert table._df.iloc[i]["Label"] == before.iloc[i]["Label"]

    def test_respects_columns_param_leaves_other_columns_alone(self):
        table = make_table(sample_df())
        slice_df = pd.DataFrame({
            "Label": ["IGNORED"],
            "ValueA": [777],
            "ValueB": ["IGNORED"],
        })

        table.update_slice(slice_df, start_row=2, columns=["ValueA"])

        assert table._df.iloc[2]["ValueA"] == 777
        assert table._df.iloc[2]["Label"] == "Row-002"  # untouched
        assert table._df.iloc[2]["ValueB"] == "2"  # untouched

    def test_writes_individual_cells_not_whole_table(self):
        """The actual fix: confirm there is no whole-table positional
        rewrite happening - table.update should never be called."""
        table = make_table(sample_df())
        slice_df = pd.DataFrame({"ValueA": [999]})

        table.update_slice(slice_df, start_row=0, columns=["ValueA"])

        table.table.update.assert_not_called()

    def test_raises_indexerror_when_slice_exceeds_table_bounds(self):
        table = make_table(sample_df())
        slice_df = pd.DataFrame({"ValueA": [1, 2, 3]})

        with pytest.raises(IndexError, match="only has 10 rows"):
            table.update_slice(slice_df, start_row=8, columns=["ValueA"])

    def test_raises_keyerror_on_unknown_column(self):
        table = make_table(sample_df())
        slice_df = pd.DataFrame({"NotARealColumn": [1]})

        with pytest.raises(KeyError, match="NotARealColumn"):
            table.update_slice(slice_df, start_row=0)

    def test_empty_slice_is_a_no_op(self):
        table = make_table(sample_df())
        before = table._df.copy()
        empty_slice = pd.DataFrame({"ValueA": []})

        table.update_slice(empty_slice, start_row=0)

        pd.testing.assert_frame_equal(table._df, before)

    def test_start_row_at_exact_table_end_with_empty_slice_does_not_raise(self):
        table = make_table(sample_df())
        empty_slice = pd.DataFrame({"ValueA": []})

        table.update_slice(empty_slice, start_row=10)  # at the boundary, 0 rows to write

    def test_uses_freshly_refreshed_position_not_stale_cache(self):
        """If the cached _df has a different row order than what a fresh
        read would produce, start_row must apply against the FRESH read,
        not the stale cache."""
        table = make_table(sample_df())

        # simulate the cache going stale: pretend a fresh read would
        # return a DIFFERENTLY ordered table
        reordered = table._df.iloc[::-1].reset_index(drop=False).set_index(table._df.index[::-1])
        original_df_property = type(table).df

        # monkeypatch refresh() to swap in the reordered version, mimicking
        # what a real refresh against a reordered live table would produce
        def fake_refresh(self):
            self._df = reordered.copy()
            return self._df

        table.refresh = fake_refresh.__get__(table)

        slice_df = pd.DataFrame({"ValueA": [555]})
        table.update_slice(slice_df, start_row=0, columns=["ValueA"])

        # row 0 of the REORDERED (fresh) table should be updated, which is
        # row 9 of the original ordering (Row-009)
        assert table._df.iloc[0]["Label"] == "Row-009"
        assert table._df.iloc[0]["ValueA"] == 555