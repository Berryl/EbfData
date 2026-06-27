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
            self._df = self.table.range.options(pd.DataFrame, header=1, index=False, chunksize=5000).value
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

    def update_slice(self,
                     df_slice: pd.DataFrame,
                     start_row: int = 0,
                     columns: List[str] | None = None) -> None:
        """Update only part of the table"""
        full_df = self.df.copy()
        rows = slice(start_row, start_row + len(df_slice))

        if columns:
            full_df.loc[rows, columns] = df_slice.values
        else:
            full_df.iloc[rows] = df_slice.values

        self.table.update(full_df, index=False)
        self._df = full_df
