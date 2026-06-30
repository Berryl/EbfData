"""
Open/close infrastructure for TEST WORKBOOKS ONLY.

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

Why this resolves the path explicitly (norm_path) instead of just calling
xw.Book(str(path)): xw.Book's own matching against already-open instances
is sensitive to exactly how the path string is spelled - relative vs
absolute, case, separators, whether it's resolved against the current
working directory at all. A bare, unresolved string can fail to match an
already-open book (causing a spurious second open) or fail to find one to
close. Resolving to one canonical absolute path before ANY xlwings call
removes that ambiguity entirely.
"""
from pathlib import Path

import xlwings as xw
from ebf_core.fileutil.path_norm import norm_path


def _resolved(path: str | Path) -> Path:
    resolved = norm_path(path, base=Path.cwd(), require_absolute=True)
    if resolved is None:
        raise ValueError(f"Could not resolve scenario workbook path: {path!r}")
    return resolved


def open_scenario_workbook(path: str | Path) -> xw.Book:
    """
    Open (or attach to, if already open) a disposable test workbook.

    The path is resolved to an absolute, canonical form first (via
    norm_path) so matching against an already-open instance is reliable
    regardless of how the caller spelled the path or what the current
    working directory happens to be.

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