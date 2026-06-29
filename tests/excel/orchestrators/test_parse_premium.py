import pytest

from ebf_data.excel.orchestrators.opex_processor import OpexProcessor


class TestParsePremium:
    """
    _parse_premium is a @staticmethod with no Excel/DataFrame dependency,
    so these tests call it directly - no mocking, no OpexProcessor
    instance, nothing invasive.
    """

    @pytest.mark.parametrize("entry_trade, expected_premium", [
        ("STO 2 Jan-30 $115.00 C @ 1.75", 1.75),
        ("STO 2 Feb-27 $115.00 C @ 10.76", 10.76),
        ("STO 2 Apr-17 $120.00 C @ 10.27", 10.27),
        ("STO 2 May-15 $120.00 C @ 8.93", 8.93),
        ("STO 2 May-29 $111.00 C @ 1.05", 1.05),
        ("STO 2 Jun-5 $115.00 C @ 2.65", 2.65),
        ("STO 2 Jul-17 $120.00 C @ 10.36", 10.36),
    ])
    def test_parses_real_entry_trade_strings(self, entry_trade: str, expected_premium: float):
        """Real production 'Entry Trade' strings, all following the pattern
        'STO <qty> <Mon-DD> $<strike> C @ <premium>'."""
        assert OpexProcessor._parse_premium(entry_trade) == expected_premium

    def test_non_string_input_returns_zero(self):
        assert OpexProcessor._parse_premium(None) == 0.0
        assert OpexProcessor._parse_premium(123) == 0.0

    def test_empty_string_returns_zero(self):
        assert OpexProcessor._parse_premium("") == 0.0

    def test_string_with_no_numeric_token_returns_zero(self):
        assert OpexProcessor._parse_premium("STO C @ N/A") == 0.0