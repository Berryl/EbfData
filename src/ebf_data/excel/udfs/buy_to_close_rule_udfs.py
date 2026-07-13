"""
xlwings UDF wrappers for BuyToCloseRule.

Thin wrappers only - all logic lives in BuyToCloseRule. These functions
exist solely to bridge Excel cell values into domain types and return
something Excel can display.

Location:
    C:\\Users\\finge\\PycharmProjects\\EbfData\\src\\ebf_data\\excel\\udfs\\buy_to_close_rule_udfs.py

Registration (one-time, in the xlwings ribbon):
    - Interpreter: C:\\Users\\finge\\PycharmProjects\\.venv\\Scripts\\python.exe
    - PYTHONPATH: C:\\Users\\finge\\PycharmProjects\\EbfData\\src\\ebf_data\\excel\\udfs
    - UDF Modules: buy_to_close_rule_udfs
    Then click "Import Python UDFs".
"""
from datetime import date

import xlwings as xw

from ebf_core.date_time.python_dates import to_date
from ebf_core.date_time.term import Term
from ebf_domain.money.money import Money, to_excel
from ebf_trading.domain.value_objects.option_specific.exit_strategies.buy_to_close_rule import BuyToCloseRule


def _make_rule(start_date, end_date, premium, evaluation_date=None):
    term = Term(start=to_date(start_date), end=to_date(end_date))
    eval_date = _resolve_date(evaluation_date)
    return BuyToCloseRule(
        term=term,
        premium=Money.mint(premium),
        evaluation_date=eval_date,
    )


def _resolve_date(value):
    """Resolve an Excel cell value to a date, defaulting to today if blank."""
    if value is None or value == "" or value == 0:
        return date.today()
    return to_date(value)


@xw.func
def btc_test(x):
    return str(type(x)) + " | " + str(x)


@xw.func
def btc_next_cutoff_date(start_date, end_date, evaluation_date=None):
    """
    Next BTC cutoff date for a short option contract.

    Returns the midpoint of the term in the first half, or the last
    trading day on or before expiration in the second half. Always
    returns a market-close datetime (4:00 PM ET).

    Args:
        start_date:      Contract book date (SC Book Date)
        end_date:        Contract expiration date (SC Exp Date)
        evaluation_date: Date to evaluate against - defaults to today
    """
    try:
        rule = _make_rule(start_date, end_date, 0.01, evaluation_date)
        return rule.next_buyback_cutoff_date
    except Exception as e:
        return f"#ERR: {e}"


@xw.func
def btc_max_buyback_amount(start_date, end_date, premium, evaluation_date=None):
    """
    The maximum price at which buying back this contract makes sense.

    Returns 20% of premium in the first half of the term, 10% in the
    second half. The result is a decimal (e.g., 0.04 for $0.04).

    Args:
        start_date:      Contract book date (SC Book Date)
        end_date:        Contract expiration date (SC Exp Date)
        premium:         Premium received when the contract was sold (SC Book Price)
        evaluation_date: Date to evaluate against - defaults to today
    """
    try:
        rule = _make_rule(start_date, end_date, premium, evaluation_date)
        return to_excel(rule.max_buyback_amount)
    except Exception as e:
        return f"#ERR: {e}"


@xw.func
def btc_should_buy_back(start_date, end_date, premium, current_ask,
                        evaluation_date=None, ask_override=None):
    """
    Returns TRUE if the contract should be bought back now.

    Compares current_ask (or ask_override if provided and positive)
    against the max buyback amount for the current half of the term.

    Args:
        start_date:      Contract book date (SC Book Date)
        end_date:        Contract expiration date (SC Exp Date)
        premium:         Premium received when the contract was sold (SC Book Price)
        current_ask:     Current Ask price for the contract (SC Current Ask)
        evaluation_date: Date to evaluate against - defaults to today
        ask_override:    Optional override price (leave blank or 0 to ignore)
    """
    try:
        rule = _make_rule(start_date, end_date, premium, evaluation_date)
        override = Money.mint(ask_override) if ask_override else None
        return rule.should_buy_back(Money.mint(current_ask), ask_override=override)
    except Exception as e:
        return f"#ERR: {e}"
