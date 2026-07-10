from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests.excel.infrastructure.scenario_workbook import (
    open_scenario_workbook,
    close_scenario_workbook,
    _resolved,
)


def make_book(fullname: str):
    return SimpleNamespace(fullname=fullname)


def make_app(books):
    return SimpleNamespace(books=books)


@pytest.fixture
def project_root(tmp_path, monkeypatch):
    """
    A real temp directory with a .git marker, so ProjectFileLocator's
    marker search has something real to find - and a deeply nested cwd,
    to prove resolution doesn't depend on cwd().
    """
    root = tmp_path / "fake_project"
    root.mkdir()
    (root / ".git").mkdir()

    nested_cwd = root / "some" / "deep" / "subdir"
    nested_cwd.mkdir(parents=True)
    monkeypatch.chdir(nested_cwd)

    return root


@pytest.fixture
def workbook_file(project_root):
    """A real (empty) file at the project root, since must_exist=True."""
    f = project_root / "xlBaseTester.xlsx"
    f.write_bytes(b"")
    return f


class TestResolved:
    """The actual bug: paths used to resolve against cwd(), which broke
    depending on where the test process was launched from. These confirm
    resolution is now anchored to the PROJECT ROOT instead."""

    def test_resolves_relative_to_project_root_not_cwd(self, workbook_file, project_root):
        resolved = _resolved("xlBaseTester.xlsx")
        assert resolved == workbook_file
        assert resolved.parent == project_root

    def test_works_regardless_of_nested_cwd(self, workbook_file):
        """cwd was set deep under the project root by the fixture - this
        must still resolve correctly to the project root, not cwd."""
        assert Path.cwd() != workbook_file.parent
        resolved = _resolved("xlBaseTester.xlsx")
        assert resolved == workbook_file

    def test_result_is_always_absolute(self, workbook_file):
        assert _resolved("xlBaseTester.xlsx").is_absolute()

    def test_missing_file_raises_file_not_found(self, project_root):
        with pytest.raises(FileNotFoundError, match="not_a_real_file.xlsx"):
            _resolved("not_a_real_file.xlsx")


class TestOpenScenarioWorkbook:

    def test_attaches_to_already_open_book_instead_of_reopening(self, monkeypatch, workbook_file):
        already_open = make_book(fullname=str(workbook_file))
        app = make_app(books=[already_open])
        monkeypatch.setattr("scenario_workbook.xw.apps", [app])

        xw_book_mock = MagicMock()
        monkeypatch.setattr("scenario_workbook.xw.Book", xw_book_mock)

        result = open_scenario_workbook("xlBaseTester.xlsx")

        assert result is already_open
        xw_book_mock.assert_not_called()

    def test_opens_new_when_nothing_matches(self, monkeypatch, workbook_file, project_root):
        other_book = make_book(fullname=str(project_root / "some_other_file.xlsx"))
        app = make_app(books=[other_book])
        monkeypatch.setattr("scenario_workbook.xw.apps", [app])

        xw_book_mock = MagicMock()
        monkeypatch.setattr("scenario_workbook.xw.Book", xw_book_mock)

        open_scenario_workbook("xlBaseTester.xlsx")

        xw_book_mock.assert_called_once()

    def test_opens_new_when_no_apps_running(self, monkeypatch, workbook_file):
        monkeypatch.setattr("scenario_workbook.xw.apps", [])

        xw_book_mock = MagicMock()
        monkeypatch.setattr("scenario_workbook.xw.Book", xw_book_mock)

        open_scenario_workbook("xlBaseTester.xlsx")

        xw_book_mock.assert_called_once()

    def test_skips_books_with_unreadable_fullname_without_crashing(self, monkeypatch, workbook_file):
        """A book whose .fullname raises (e.g., a book in a broken state)
        should not crash the matching loop - just be skipped."""
        broken_book = MagicMock()
        type(broken_book).fullname = property(lambda f: (_ for _ in ()).throw(RuntimeError("boom")))
        app = make_app(books=[broken_book])
        monkeypatch.setattr("scenario_workbook.xw.apps", [app])

        xw_book_mock = MagicMock()
        monkeypatch.setattr("scenario_workbook.xw.Book", xw_book_mock)

        open_scenario_workbook("xlBaseTester.xlsx")

        xw_book_mock.assert_called_once()

    def test_raises_when_workbook_file_does_not_exist(self, monkeypatch, project_root):
        monkeypatch.setattr("scenario_workbook.xw.apps", [])

        with pytest.raises(FileNotFoundError):
            open_scenario_workbook("does_not_exist.xlsx")


class TestCloseScenarioWorkbook:

    def test_default_does_not_save(self):
        book = MagicMock()

        close_scenario_workbook(book)

        book.save.assert_not_called()
        book.close.assert_called_once()

    def test_save_changes_true_saves_before_closing(self):
        book = MagicMock()

        close_scenario_workbook(book, save_changes=True)

        book.save.assert_called_once()
        book.close.assert_called_once()