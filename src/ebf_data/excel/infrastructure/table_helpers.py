import pandas as pd
from xlwings import Range

def get_data_body_column(db_range: Range, df: pd.DataFrame, column_name: str) -> int:
    """
    Return the 1-based worksheet column number for a column inside the table's data body range.
    """
    try:
        col_index = df.columns.get_loc(column_name)
    except KeyError:
        raise KeyError(
            f"Column '{column_name}' not found in DataFrame. "
            f"Available columns: {list(df.columns)}"
        ) from None

    # Safely handle int vs. slice from the Excel COM object
    col = db_range.column
    start_col = col.start if isinstance(col, slice) else col

    return start_col + col_index