import re
from typing import Any, Optional

import xlwings as xw


def find_open_book(workbook_name: str) -> xw.Book:
    """
    Attach to an already-open workbook by name. Never launches or closes Excel.
    """
    if not xw.apps:
        raise RuntimeError("No running Excel instance found (xw.apps is empty)")

    target = workbook_name.lower()
    matches = [
        book
        for app in xw.apps
        for book in app.books
        if book.name.lower() == target or book.fullname.lower() == target
    ]

    if len(matches) > 1:
        locations = ", ".join(
            f"pid={book.app.pid} path={book.fullname}" for book in matches
        )
        raise RuntimeError(
            f"Multiple open workbooks named {workbook_name!r} found: {locations}. "
            "Close the duplicate/stale copy before continuing."
        )
    if not matches:
        open_names = [b.name for app in xw.apps for b in app.books]
        raise FileNotFoundError(
            f"Open Excel workbook not found: {workbook_name!r}. "
            f"Currently open: {open_names}"
        )
    return matches[0]


# region Defined Names
def get_named_value(book: xw.Book, name: str, refers_to: bool = False) -> Any:
    """Return a workbook-scoped defined name's value, or its RefersTo formula."""
    nm = _find_in_names(book.names, name)
    if nm is None:
        raise KeyError(f"Defined name {name!r} not found in workbook {book.name!r}")
    return _name_payload(nm, refers_to)


def get_sheet_named_value(sheet: xw.Sheet, name: str, refers_to: bool = False) -> Any:
    """Return a sheet-scoped defined name's value, or its RefersTo formula."""
    nm = _find_in_names(sheet.names, name)
    if nm is None:
        nm = _find_in_names(sheet.book.names, f"{sheet.name}!{name}")
    if nm is None:
        raise KeyError(
            f"Defined name {name!r} not found on sheet {sheet.name!r}"
        )
    return _name_payload(nm, refers_to)


_RANGE_REF = re.compile(
    r"^(?:'[^']+'|\w+)!\$?[A-Za-z]{1,3}\$?\d+(?::\$?[A-Za-z]{1,3}\$?\d+)?$"
)


def _name_payload(nm: xw.Name, refers_to: bool) -> Any:
    body = _formula_body(nm)
    if refers_to:
        return body
    if _RANGE_REF.match(body):
        return nm.refers_to_range.value
    return _coerce_literal(body)


def _formula_body(nm: xw.Name) -> str:
    formula = nm.refers_to
    if isinstance(formula, str) and formula.startswith("="):
        return formula[1:]
    return formula


def _coerce_literal(text: str) -> Any:
    for caster in (int, float):
        try:
            return caster(text)
        except (TypeError, ValueError):
            pass
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _find_in_names(names: xw.main.Names, name: str) -> Optional[xw.Name]:
    """Case-insensitive lookup in a Names collection."""
    key = name.lower()
    for nm in names:
        if nm.name.lower() == key:
            return nm
    return None
# endregion
