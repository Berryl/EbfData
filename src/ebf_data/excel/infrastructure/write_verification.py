from typing import Any

import pandas as pd
import numpy as np
from xlwings import Sheet


class PriceWriteVerificationError(Exception):
    """Raised when a bulk Excel write cannot be verified."""
    pass


def find_verification_sample(
        symbol_to_indices: dict[str, list[int]],
        prices: dict[str, float | None],
        df_index: pd.Index,
        first_row: int = 0,
) -> tuple[int, float] | None:
    """
    Find the first successfully fetched symbol and return
    (ws_row, expected_value) for post-write verification.

    Returns None if no successful prices exist.

    Assumptions
    -----------
    - Each list in symbol_to_indices is non-empty.
    - df_index labels are unique (get_loc returns an int).
    - The integer stored in the indices lists are valid labels present in df_index.
    """
    for symbol, indices in symbol_to_indices.items():
        if not indices:  # defensive
            continue
        price = prices.get(symbol)
        if price is not None:
            row_position = df_index.get_loc(indices[0])
            assert isinstance(row_position, (int, np.integer)), (
                f"Non-unique index label {indices[0]!r} – cannot determine a single worksheet row"
            )
            return first_row + int(row_position), price
    return None


def verify_column_write(
        sheet: Sheet,
        ws_row: int,
        ws_col: int,
        expected: Any,
        *,
        tolerance: float | int = 0.001,
) -> None:
    """
    Read back a single cell after a bulk column write and confirm the
    expected value landed. Raises PriceWriteVerificationError if it didn't.

    Args:
        sheet: xlwings Sheet object
        ws_row: worksheet row of the cell to check
        ws_col: worksheet column of the cell to check
        expected: the value that should be in the cell
        tolerance: allowed difference for float comparison
    """
    actual = sheet.range((ws_row, ws_col)).value

    if actual is None:
        if expected is None:
            return
        raise PriceWriteVerificationError(
            f"Write verification failed at ({ws_row}, {ws_col}): "
            f"expected {expected}, got None"
        )

    try:
        if abs(float(actual) - float(expected)) > tolerance:
            raise PriceWriteVerificationError(
                f"Write verification failed at ({ws_row}, {ws_col}): "
                f"expected {expected}, got {actual}"
            )
    except (TypeError, ValueError) as e:
        raise PriceWriteVerificationError(
            f"Write verification failed at ({ws_row}, {ws_col}): "
            f"could not compare expected {expected!r} with actual {actual!r}"
        ) from e
