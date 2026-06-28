import xlwings as xw


def find_open_book(workbook_name: str) -> xw.Book:
    """
    Attach to an already-open workbook by name. Never launches or closes Excel.
    """
    if len(xw.apps) == 0:
        raise RuntimeError("No running Excel instance found (xw.apps is empty)")

    matches = [
        book
        for app in xw.apps
        for book in app.books
        if book.name.lower() == workbook_name.lower()
    ]

    if len(matches) > 1:
        locations = ", ".join(f"pid={book.app.pid} path={book.fullname}" for book in matches)
        raise RuntimeError(
            f"Multiple open workbooks named '{workbook_name}' found: {locations}. "
            f"Close the duplicate/stale copy before continuing."
        )

    if not matches:
        raise FileNotFoundError(f"Open Excel workbook not found: {workbook_name}")

    return matches[0]

def get_named_value(sheet: xw.Sheet, name: str):
    return sheet.range(name).value