from typing import Any
from xlwings import Sheet


class PriceWriteVerificationError(Exception):
    """Raised when a bulk Excel write cannot be verified."""
    pass


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