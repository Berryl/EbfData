"""Explicit domain-to-row mapping for the initial trade-journal write slice."""

from dataclasses import dataclass
from datetime import datetime

from ebf_domain.money.money import Money
from ebf_trading.domain.entities.order import Order
from ebf_trading.domain.entities.trade_campaign import TradeCampaign
from ebf_trading.domain.entities.trade_legs.trade_leg import TradeLeg
from ebf_trading.domain.entities.transaction_events.transaction_event import TransactionEvent
from ebf_trading.domain.entities.transaction_events.transaction_event_type import TransactionEventType
from ebf_trading.domain.value_objects.orders.order_type_spec import MarketSpec
from ebf_trading.domain.value_objects.positions.option_position import OptionPosition
from ebf_trading.domain.value_objects.quantities.contract_quantity import ContractQuantity


@dataclass(frozen=True)
class CampaignRow:
    id: str
    account_id: str
    ticker: str
    reference_number: int
    reference_id: str


@dataclass(frozen=True)
class LegRow:
    id: str
    campaign_id: str
    option_type: str
    strike_minor_units: int
    strike_currency: str
    expiration_at: str
    position_side: str
    contract_quantity: int


@dataclass(frozen=True)
class OrderRow:
    campaign_id: str
    leg_id: str
    submission_at: str
    order_spec_type: str
    fill_at: str
    fill_price_minor_units: int
    fill_price_currency: str
    fees_minor_units: int
    fees_currency: str
    contract_quantity: int


@dataclass(frozen=True)
class EventRow:
    id: str
    campaign_id: str
    leg_id: str
    event_type: str
    notes: str | None


@dataclass(frozen=True)
class CampaignJournalRows:
    campaign: CampaignRow
    leg: LegRow
    order: OrderRow
    event: EventRow


def map_campaign(campaign: TradeCampaign) -> CampaignJournalRows:
    """Flatten the one-leg filled-option creation aggregate into SQL rows."""
    legs = campaign.legs
    orders = campaign.orders
    events = campaign.events
    if len(legs) != 1 or len(orders) != 1 or len(events) != 1:
        raise ValueError("SQLite journal persistence requires exactly one leg, order, and event")

    leg = legs[0]
    retained_leg_id, order = orders[0]
    event = events[0]
    _validate_associations(campaign, leg, retained_leg_id, order, event)

    position = leg.position
    if not isinstance(position, OptionPosition):
        raise TypeError("SQLite journal persistence currently supports only option positions")
    if not isinstance(position.quantity, ContractQuantity):
        raise TypeError("SQLite journal persistence currently supports only contract quantities")
    if position.option.underlying.value != campaign.ticker:
        raise ValueError("Option underlying must match the campaign ticker")

    fill_price, fees, order_quantity, submission_time, fill_time = _filled_order_values(order)
    if order_quantity != position.quantity:
        raise ValueError("Retained order quantity must match the opening position quantity")
    if position.entry_time != fill_time:
        raise ValueError("Opening position time must match the retained order fill time")
    if position.entry_greeks is not None:
        raise ValueError("Initial SQLite journal persistence does not store Greeks")

    campaign_id = str(campaign.id)
    leg_id = str(leg.id)
    strike = position.option.strike.price
    return CampaignJournalRows(
        campaign=CampaignRow(
            id=campaign_id,
            account_id=str(campaign.account.id),
            ticker=campaign.ticker,
            reference_number=_reference_number(campaign.ticker, campaign.reference_id),
            reference_id=campaign.reference_id,
        ),
        leg=LegRow(
            id=leg_id,
            campaign_id=campaign_id,
            option_type=position.option.option_type.value,
            strike_minor_units=strike.amount_cents,
            strike_currency=strike.currency.iso_code,
            expiration_at=_datetime_text(position.option.expiration.deadline),
            position_side=position.side.value,
            contract_quantity=position.quantity.value,
        ),
        order=OrderRow(
            campaign_id=campaign_id,
            leg_id=leg_id,
            submission_at=_datetime_text(submission_time),
            order_spec_type="market",
            fill_at=_datetime_text(fill_time),
            fill_price_minor_units=fill_price.amount_cents,
            fill_price_currency=fill_price.currency.iso_code,
            fees_minor_units=fees.amount_cents,
            fees_currency=fees.currency.iso_code,
            contract_quantity=order_quantity.value,
        ),
        event=EventRow(
            id=str(event.id),
            campaign_id=campaign_id,
            leg_id=leg_id,
            event_type=event.event_type.value,
            notes=event.notes,
        ),
    )


def _validate_associations(
    campaign: TradeCampaign,
    leg: TradeLeg,
    retained_leg_id: object,
    order: Order,
    event: TransactionEvent,
) -> None:
    if retained_leg_id != leg.id:
        raise ValueError("Retained order must belong to the persisted leg")
    if event.event_type is not TransactionEventType.OPEN:
        raise ValueError("SQLite journal persistence currently supports only OPEN events")
    if event.trade_id != campaign.id or event.leg_id != leg.id:
        raise ValueError("Transaction event identifiers do not match the campaign and leg")
    if event.order is not order:
        raise ValueError("Transaction event must retain the persisted order")


def _filled_order_values(
    order: Order,
) -> tuple[Money, Money, ContractQuantity, datetime, datetime]:
    if not isinstance(order.order_type_spec, MarketSpec):
        raise TypeError("SQLite journal persistence currently supports only market orders")
    if order.time_in_force is not None or order.cancel_time is not None:
        raise ValueError("Filled journal orders cannot contain unpersisted lifecycle fields")
    if order.submission_time is None or order.fill_time is None or order.fill_price is None:
        raise ValueError("Journal order must contain submission and fill details")
    if order.fees is None:
        raise ValueError("Journal order must contain fees")
    if not isinstance(order.quantity, ContractQuantity):
        raise TypeError("Journal order must contain a contract quantity")
    return order.fill_price, order.fees, order.quantity, order.submission_time, order.fill_time


def _reference_number(ticker: str, reference_id: str) -> int:
    if not reference_id.startswith(ticker):
        raise ValueError("Campaign reference ID must begin with its ticker")
    suffix = reference_id[len(ticker) :]
    if not suffix.isdecimal() or int(suffix) < 1:
        raise ValueError("Campaign reference ID must end with a positive sequence number")
    return int(suffix)


def _datetime_text(value: datetime) -> str:
    if value.utcoffset() is None:
        raise ValueError("Persisted datetimes must include a UTC offset")
    return value.isoformat()
