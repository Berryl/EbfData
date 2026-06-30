from typing import List

import pandas as pd
import xlwings as xw


class xlTable:
    def __init__(self, book: xw.Book, sheet_name: str, table_name: str):
        self.book = book
        self.sheet = book.sheets[sheet_name]
        self.table = self.sheet.tables[table_name]
        self.name = table_name
        self._df: pd.DataFrame | None = None

    @property
    def df(self) -> pd.DataFrame:
        """Full table as DataFrame"""
        if self._df is None:
            loaded = self.table.range.options(pd.DataFrame, header=1, index=False, chunksize=5000).value
            self._df = loaded
        assert self._df is not None
        return self._df

    def refresh(self) -> pd.DataFrame:
        """Force reload from Excel"""
        self._df = None
        return self.df

    def get_slice(self,
                  columns: List[str] | None = None,
                  start_row: int = 0,
                  end_row: int | None = None) -> pd.DataFrame:
        """Get specific columns and/or row slice"""
        df = self.df

        if columns:
            missing = [c for c in columns if c not in df.columns]
            if missing:
                raise ValueError(f"Columns not found: {missing}")
            df = df[columns]

        return df.iloc[start_row:end_row]

    def get_column(self, col_name: str) -> pd.Series:
        return self.df[col_name]

    def update(self, df_new: pd.DataFrame, index: bool = False) -> None:
        """Update table and cache"""
        self.table.update(df_new, index=index)
        self._df = df_new.copy()

    def update_row(self, index_label, values: dict) -> None:
        """
        Update specific columns for a single row, identified by its DataFrame
        index label (not its positional row number).

        Use this instead of update_slice when the row to update was found by
        filtering/matching logic and may not be at a known or contiguous
        position - e.g., closing one specific matched trade out of several
        open candidates.

        IMPORTANT: this writes ONLY the target row's cells, addressed by its
        position in a freshly read copy of the live table - never the whole
        table rewritten positionally. Writing the whole table back with
        index=False assumes the cached DataFrame's row order still matches
        the live table's row order at write-time, which is not guaranteed.
        (The cache can go stale relative to the workbook for any reason.)
        That mismatch causes values to land on the WRONG rows silently -
        this method exists specifically to make that failure impossible by
        construction: it never re-positions any row other than the one
        being targeted.

        Args:
            index_label: the .index value of the row to update (as returned
                by a filtered/matched DataFrame's .index).
            values: mapping of column name -> new value for that row.

        Raises:
            KeyError: if index_label is not present in the table, or if a
                column in `values` does not exist in the table.
        """
        self.refresh()
        current_df = self.df

        if index_label not in current_df.index:
            raise KeyError(f"Row index {index_label!r} not found in table '{self.name}'")

        missing_columns = [c for c in values if c not in current_df.columns]
        if missing_columns:
            raise KeyError(f"Columns not found in table '{self.name}': {missing_columns}")

        # Positional offset of this row within the table RIGHT NOW, from the
        # fresh read above - never from a cache that could have gone stale.
        row_position = current_df.index.get_loc(index_label)

        columns_in_order = current_df.columns.tolist()
        for column, value in values.items():
            col_position = columns_in_order.index(column)
            # data_body_range excludes the header row, so (row_position, col_position)
            # maps directly onto the table's data rows/columns.
            self.table.data_body_range[row_position, col_position].value = value
            current_df.loc[index_label, column] = value

        self._df = current_df

    def update_slice(self, df_slice: pd.DataFrame, start_row: int = 0,columns: List[str] | None = None) -> None:
        """Update only part of the table"""
        full_df = self.df.copy()
        rows = slice(start_row, start_row + len(df_slice))

        if columns:
            full_df.loc[rows, columns] = df_slice.values
        else:
            full_df.iloc[rows] = df_slice.values

        self.table.update(full_df, index=False)
        self._df = full_df