import pytest

KEEP_OPEN = False

def make_book_fixture(creator, scope="module"):
    # noinspection PyCallingNonCallable
    @pytest.fixture(scope=scope)
    def _fixture(_self):
        book = creator()
        yield book
        if not KEEP_OPEN:
            book.close()
    return _fixture