"""
Open/close infrastructure for DISPOSABLE TEST WORKBOOKS ONLY.

This module exists for one purpose: letting test fixtures open and close
scenario workbooks freely - files that exist solely for testing and have
no other consumers, no live formulas, and no harm done by being opened or
closed by code.

THIS IS NOT FOR PRODUCTION WORKBOOKS. CAGR.xlsm, snapshot.xlsm, and any
other live, 24/7 trading workbook must continue to go through
excel_book_finder.find_open_book(), which only ever ATTACHES to an
already-open instance and never opens or closes anything. That contract
does not change and this module must never be used as a substitute for it.

If you're not sure which one to use: if the workbook is something a human
trader is actively relying on right now, use find_open_book. If it's a
file that exists only so a test suite has something to open and throw
away, use this module.

Why this resolves the path via ProjectFileLocator instead of just calling
xw.Book(str(path)) or resolving against Path.cwd(): xw.Book's own matching
against already-open instances is sensitive to exactly how the path string
is spelled - relative vs absolute, case, separators, and critically, what
the current working directory happens to be when the test process starts.
A path resolved against cwd() works fine until the test is launched from a
different working directory (a different IDE config, CI, a teammate
running from a subfolder) and then silently breaks. Anchoring against the
PROJECT ROOT (auto-detected via ProjectFileLocator's marker search, e.g.
.git/pyproject.toml) instead of cwd() makes resolution consistent
regardless of where the process was launched from.
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

    The path is resolved against the project root first (via
    ProjectFileLocator) so matching against an already-open instance is
    reliable regardless of how the caller spelled the path or what the
    current working directory happens to be.

    Safe to call freely in test fixtures. Never use this for a production
    workbook - see module docstring.
    """
    resolved_path = _resolved(path)

    for app in xw.apps:
        for book in app.books:
            try:
                book_path = Path(book.fullname).resolve()
            except Exception:
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