"""
Open/close infrastructure for TEST WORKBOOKS ONLY.
"""
from pathlib import Path

import xlwings as xw
from ebf_core.fileutil.project_file_locator import ProjectFileLocator


def _resolved(path: str | Path) -> Path:
    """
    Resolve a scenario workbook path against the project root (not cwd).

    Relative paths are resolved as <project_root>/<path>. Absolute paths
    pass through as-is. Raises FileNotFoundError if the resolved file
    doesn't exist - a missing scenario workbook should fail loudly, not
    silently attempt to open a path that isn't there.
    """
    locator = ProjectFileLocator()
    return locator.get_project_file(path, must_exist=True)


def open_scenario_workbook(path: str | Path) -> xw.Book:
    """
    Open (or attach to, if already open) a disposable test workbook.
    """
    resolved_path = _resolved(path)

    for app in xw.apps:
        for book in app.books:
            try:
                book_path = Path(book.fullname).resolve()
            except (FileNotFoundError, NotADirectoryError, ValueError, OSError, RuntimeError):
                continue
            if book_path == resolved_path:
                return book

    return xw.Book(str(resolved_path))


def close_scenario_workbook(book: xw.Book, save_changes: bool = False) -> None:
    """
    Close a disposable test workbook opened via open_scenario_workbook.

    Args:
        book: the workbook to close.
        save_changes: if True, saves before closing. Default False -
            xlwings' Book.close() discards unsaved changes on its own, so
            most scenario tests want this left as False to guarantee a
            clean, unmodified file on the next run regardless of what the
            test wrote to it.
    """
    if save_changes:
        book.save()
    book.close()