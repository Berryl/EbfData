from types import SimpleNamespace

import pytest
import xlwings as xw

from ebf_data.excel.infrastructure.excel_book_finder import find_open_book, get_named_value, get_sheet_named_value
from excel.pricing.pricing_scenarios import ExcelBookFinderTester


def make_book(name, fullname=None):
    return SimpleNamespace(name=name, fullname=fullname or name, app=None)


def make_app(pid, books):
    app = SimpleNamespace(pid=pid, books=books)
    for book in books:
        book.app = app
    return app

KEEP_OPEN = True

class TestXlBookFinder:
    @pytest.fixture(scope="module")
    def known_wkb(self) -> xw.Book:
        book = ExcelBookFinderTester().book
        yield book
        if not KEEP_OPEN:
            book.close()

    class TestFindOpenBook:

        def test_can_find_known_open_wkb_by_name(self, known_wkb) -> None:
            found = find_open_book(known_wkb.name)
            assert found.fullname == known_wkb.fullname

        def test_can_find_known_open_wkb_by_fullname(self, known_wkb) -> None:
            found = find_open_book(known_wkb.fullname)
            assert found.fullname == known_wkb.fullname

        def test_search_is_case_insensitive(self, known_wkb) -> None:
            found = find_open_book(known_wkb.fullname.upper())
            assert found.fullname == known_wkb.fullname

        class TestErrorConditions:
            APPS = "apps" # the xlwing collection of running Excel processes

            def test_when_excel_app_is_not_running(self, monkeypatch):
                monkeypatch.setattr(xw, self.APPS, [])
                with pytest.raises(RuntimeError, match="No running Excel instance"):
                    find_open_book("anything.xlsx")

            def test_when_wkb_is_not_open(self, monkeypatch):
                app = make_app(101, [make_book("other.xlsx")])
                monkeypatch.setattr(xw, self.APPS, [app])
                with pytest.raises(FileNotFoundError, match="not found"):
                    find_open_book("blah.xlsx")

            def test_when_duplicate_matches_found_within_the_same_app(self, monkeypatch):
                app = make_app(
                    101,
                    [
                        make_book("blah.xlsx", r"C:\one\blah.xlsx"),
                        make_book("blah.xlsx", r"C:\two\blah.xlsx"),
                    ],
                )
                monkeypatch.setattr(xw, self.APPS, [app])
                with pytest.raises(RuntimeError, match="Multiple open workbooks"):
                    find_open_book("blah.xlsx")

            def test_when_duplicate_matches_found_across_apps(self, monkeypatch):
                apps = [
                    make_app(101, [make_book("blah.xlsx", r"C:\one\blah.xlsx")]),
                    make_app(202, [make_book("blah.xlsx", r"C:\two\blah.xlsx")]),
                ]
                monkeypatch.setattr(xw, self.APPS, apps)
                with pytest.raises(RuntimeError, match="Multiple open workbooks"):
                    find_open_book("blah.xlsx")


    class TestDefinedNames:
        class TestGetNamedValue:
            def test_can_get_named_value(self, known_wkb):
                assert get_named_value(known_wkb, "WBK_SCOPE") == "some global value"

            def test_can_get_refers_to_value(self, known_wkb):
                assert get_named_value(known_wkb, "MEANING_OF_LIFE", refers_to=True) == '42'

            def test_undefined_name_raises(self, known_wkb):
                with pytest.raises(KeyError):
                    get_named_value(known_wkb, "non existing name")

        class TestGetSheetNamedValue:

            def test_can_get_sheet_scoped_name(self, known_wkb):
                sheet = known_wkb.sheets[0]
                assert get_sheet_named_value(sheet, "LOCAL_SCOPE") == "some local value"

            def test_can_get_sheet_scoped_refers_to(self, known_wkb):
                sheet = known_wkb.sheets[0]
                assert get_sheet_named_value(sheet, "MIN", refers_to=True) == "18"


