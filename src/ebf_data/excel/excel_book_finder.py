import xlwings as xw


def find_open_book(workbook_name: str) -> xw.Book:
    for app in xw.apps:
        for book in app.books:
            if book.name.lower() == workbook_name.lower():
                return book

    raise FileNotFoundError(f"Open Excel workbook not found: {workbook_name}")

def get_named_value(sheet: xw.Sheet, name: str):
    return sheet.range(name).value
