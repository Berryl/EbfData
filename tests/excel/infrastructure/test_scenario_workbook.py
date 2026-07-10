from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tests.excel.infrastructure.scenario_workbook import (
    open_scenario_workbook,
    close_scenario_workbook,
    _resolved,
)


# region Fixtures
@pytest.fixture
def project_root(tmp_path, monkeypatch):
    """Create a fake project with .git marker and nested cwd."""
    root = tmp_path / "fake_project"
    root.mkdir()
    (root / ".git").mkdir()  # marker for ProjectFileLocator

    # Simulate running tests from a deep subdirectory
    nested_cwd = root / "some" / "deep" / "subdir"
    nested_cwd.mkdir(parents=True)
    monkeypatch.chdir(nested_cwd)

    return root


@pytest.fixture
def workbook_file(project_root):
    """Create a real empty workbook file under the project root."""
    f = project_root / "xlBaseTester.xlsx"
    f.write_bytes(b"")
    return f


def make_book(fullname: str):
    return SimpleNamespace(fullname=fullname)


def make_app(books=None):
    return SimpleNamespace(books=books or [])
# endregion


class TestResolved:
    """Test that workbook paths are resolved against the project root, not cwd."""

    def test_resolves_relative_to_project_root(self, workbook_file, project_root):
        resolved = _resolved("xlBaseTester.xlsx")
        assert resolved == workbook_file
        assert resolved.parent == project_root

    def test_works_from_deep_nested_cwd(self, workbook_file):
        assert Path.cwd() != workbook_file.parent
        resolved = _resolved("xlBaseTester.xlsx")
        assert resolved == workbook_file

    def test_always_returns_absolute_path(self, workbook_file):
        assert _resolved("xlBaseTester.xlsx").is_absolute()

    def test_raises_if_file_does_not_exist(self, project_root):
        with pytest.raises(FileNotFoundError):
            _resolved("nonexistent.xlsx")


class TestOpenScenarioWorkbook:

    def test_attaches_to_already_open_book(self, monkeypatch, workbook_file):
        """Should reuse an already open workbook instead of reopening it."""
        already_open = make_book(fullname=str(workbook_file))
        app = make_app([already_open])

        monkeypatch.setattr("tests.excel.infrastructure.scenario_workbook.xw.apps", [app])

        xw_book_mock = MagicMock()
        monkeypatch.setattr("tests.excel.infrastructure.scenario_workbook.xw.Book", xw_book_mock)

        result = open_scenario_workbook("xlBaseTester.xlsx")

        assert result is already_open
        xw_book_mock.assert_not_called()

    def test_opens_new_book_when_no_match(self, monkeypatch, workbook_file):
        """Should open a new book if no matching open workbook is found."""
        other_book = make_book(fullname=str(workbook_file.parent / "other.xlsx"))
        app = make_app([other_book])

        monkeypatch.setattr("tests.excel.infrastructure.scenario_workbook.xw.apps", [app])

        xw_book_mock = MagicMock()
        monkeypatch.setattr("tests.excel.infrastructure.scenario_workbook.xw.Book", xw_book_mock)

        open_scenario_workbook("xlBaseTester.xlsx")

        xw_book_mock.assert_called_once()

    def test_opens_new_book_when_no_apps_running(self, monkeypatch, workbook_file):
        monkeypatch.setattr("tests.excel.infrastructure.scenario_workbook.xw.apps", [])

        xw_book_mock = MagicMock()
        monkeypatch.setattr("tests.excel.infrastructure.scenario_workbook.xw.Book", xw_book_mock)

        open_scenario_workbook("xlBaseTester.xlsx")

        xw_book_mock.assert_called_once()

    def test_skips_broken_books_gracefully(self, monkeypatch, workbook_file):
        """Should skip books whose .fullname property raises."""
        broken_book = MagicMock()
        type(broken_book).fullname = property(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))

        app = make_app([broken_book])
        monkeypatch.setattr("tests.excel.infrastructure.scenario_workbook.xw.apps", [app])

        xw_book_mock = MagicMock()
        monkeypatch.setattr("tests.excel.infrastructure.scenario_workbook.xw.Book", xw_book_mock)

        open_scenario_workbook("xlBaseTester.xlsx")

        xw_book_mock.assert_called_once()

    def test_raises_when_file_does_not_exist(self, monkeypatch):
        monkeypatch.setattr("tests.excel.infrastructure.scenario_workbook.xw.apps", [])

        with pytest.raises(FileNotFoundError):
            open_scenario_workbook("does_not_exist.xlsx")


class TestCloseScenarioWorkbook:

    def test_default_does_not_save_changes(self):
        book = MagicMock()
        close_scenario_workbook(book)

        book.save.assert_not_called()
        book.close.assert_called_once()

    def test_save_changes_true_saves_before_closing(self):
        book = MagicMock()
        close_scenario_workbook(book, save_changes=True)

        book.save.assert_called_once()
        book.close.assert_called_once()