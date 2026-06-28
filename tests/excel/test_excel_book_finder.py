from types import SimpleNamespace

import pytest

from ebf_data.excel.cagr.cagr_table import CAGR_WB, CAGR_WKS, ACB
from ebf_data.excel.excel_book_finder import find_open_book, get_named_value


def make_book(name, fullname=None):
    return SimpleNamespace(name=name, fullname=fullname or name, app=None)


def make_app(pid, books):
    app = SimpleNamespace(pid=pid, books=books)
    for book in books:
        book.app = app
    return app


@pytest.mark.integration
class TestWbFinder:
    class TestFindOpenBook:

        def test_raises_when_no_excel_running(self, monkeypatch):
            monkeypatch.setattr("ebf_data.excel.excel_book_finder.xw.apps", [])

            with pytest.raises(RuntimeError, match="No running Excel instance"):
                find_open_book("snapshot.xlsm")

        def test_raises_when_workbook_not_open(self, monkeypatch):
            other_book = make_book("other.xlsm")
            app = make_app(pid=111, books=[other_book])
            monkeypatch.setattr("ebf_data.excel.excel_book_finder.xw.apps", [app])

            with pytest.raises(FileNotFoundError, match="Open Excel workbook not found: snapshot.xlsm"):
                find_open_book("snapshot.xlsm")

        def test_returns_book_when_single_match(self, monkeypatch):
            target = make_book("snapshot.xlsm", fullname=r"C:\trading\snapshot.xlsm")
            decoy = make_book("other.xlsm")
            app = make_app(pid=111, books=[decoy, target])
            monkeypatch.setattr("ebf_data.excel.excel_book_finder.xw.apps", [app])

            result = find_open_book("snapshot.xlsm")

            assert result is target

        def test_match_is_case_insensitive(self, monkeypatch):
            target = make_book("Snapshot.XLSM")
            app = make_app(pid=111, books=[target])
            monkeypatch.setattr("ebf_data.excel.excel_book_finder.xw.apps", [app])

            result = find_open_book("snapshot.xlsm")

            assert result is target

        def test_raises_on_duplicate_matches_same_app(self, monkeypatch):
            dupe_1 = make_book("snapshot.xlsm", fullname=r"C:\live\snapshot.xlsm")
            dupe_2 = make_book("snapshot.xlsm", fullname=r"C:\backup\snapshot.xlsm")
            app = make_app(pid=111, books=[dupe_1, dupe_2])
            monkeypatch.setattr("ebf_data.excel.excel_book_finder.xw.apps", [app])

            with pytest.raises(RuntimeError, match="Multiple open workbooks named 'snapshot.xlsm'"):
                find_open_book("snapshot.xlsm")

        def test_raises_on_duplicate_matches_across_apps(self, monkeypatch):
            dupe_1 = make_book("snapshot.xlsm", fullname=r"C:\live\snapshot.xlsm")
            dupe_2 = make_book("snapshot.xlsm", fullname=r"C:\stale\snapshot.xlsm")
            app_1 = make_app(pid=111, books=[dupe_1])
            app_2 = make_app(pid=222, books=[dupe_2])
            monkeypatch.setattr("ebf_data.excel.excel_book_finder.xw.apps", [app_1, app_2])

            with pytest.raises(RuntimeError) as exc_info:
                find_open_book("snapshot.xlsm")

            message = str(exc_info.value)
            assert "pid=111" in message
            assert "pid=222" in message
            assert r"C:\live\snapshot.xlsm" in message
            assert r"C:\stale\snapshot.xlsm" in message

    class TestGetNamedValue:
        def test_can_get_named_value(self):
            wb = find_open_book(CAGR_WB)
            sheet = wb.sheets[CAGR_WKS]
            value = get_named_value(sheet, ACB)
            assert value > 0
