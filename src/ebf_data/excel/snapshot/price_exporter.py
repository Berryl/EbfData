"""
Serializes fetched prices into the JSON contract consumed by the VBA pricing updater.

PriceExporter takes the already-fetched results from PriceUpdater (equity)
and OptionPriceUpdater (all four option types) and writes a single JSON
file under runtime/pricing/pending/. VBA later moves that file to
runtime/pricing/updated/ once it has applied the prices to the workbook,
overwriting any existing file of the same name in each folder - this
class only ever writes to pending/.

Failures are dropped entirely rather than carried through as "existing"
values: a symbol that failed to fetch doesn't appear in a section's price
list, so VBA leaves that cell at whatever value was last successfully written.
(Failures are still noted in the run summary)

Every section carries an "attempted" flag. This exists specifically for
a scoped run (PriceOrchestrator.run_equity_only()/run_options_only()),
where sections outside the scope come through as an empty placeholder
(zero symbols, no failures) so the JSON keeps a uniform five-section
shape regardless of what was actually fetched. Without "attempted",
that placeholder is indistinguishable from a section that was genuinely
fetched and genuinely found nothing active - and VBA, which writes a
per-column tooltip from every section on every 'apply', would overwrite a
correct tooltip from an earlier pass with a false "0 symbols" on a
later pass that never touched that section. "attempted" is what
lets VBA skip writing a tooltip for a section this run didn't touch.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from ebf_core.fileutil.project_file_locator import ProjectFileLocator

from ebf_data.excel.pricing.pricing_helpers import PriceUpdateResult, SymbolPriceOutcome
from ebf_data.excel.snapshot.option_price_updater import OptionType
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable

PENDING_FOLDER = Path("runtime/pricing/pending")


@dataclass(frozen=True)
class SectionSpec:
    """Static config for one of the five price sections.

    key is the JSON key used in the output file. symbol_column and
    target_column are the Excel column headers VBA reads from / writes
    to - sourced from SnapshotTable so this never drifts from the real
    worksheet headers. (See LC_BID_COLUMN / LP_BID_COLUMN, whose actual
    text doesn't match what a clean rename would look like, because
    legacy VBA is hard-coded to the current strings.)
    """
    key: str
    symbol_column: str
    target_column: str


EQUITY = SectionSpec(
    key="equity", symbol_column=SnapshotTable.SYMBOL_COLUMN, target_column=SnapshotTable.LAST_PRICE_COLUMN)
SHORT_CALLS = SectionSpec(
    key="short_calls", symbol_column=SnapshotTable.SC_SYMBOL_COLUMN, target_column=SnapshotTable.SC_ASK_COLUMN)
SHORT_PUTS = SectionSpec(
    key="short_puts", symbol_column=SnapshotTable.SP_SYMBOL_COLUMN, target_column=SnapshotTable.SP_ASK_COLUMN)
LONG_CALLS = SectionSpec(
    key="long_calls", symbol_column=SnapshotTable.LC_SYMBOL_COLUMN, target_column=SnapshotTable.LC_BID_COLUMN)
LONG_PUTS = SectionSpec(
    key="long_puts", symbol_column=SnapshotTable.LP_SYMBOL_COLUMN, target_column=SnapshotTable.LP_BID_COLUMN)


@dataclass(frozen=True)
class PriceEntry:
    symbol: str
    price: float


@dataclass(frozen=True)
class SectionSummary:
    total: int
    succeeded: int
    failed: int
    failed_symbols: list[str]


@dataclass(frozen=True)
class SectionExport:
    symbol_column: str
    target_column: str
    attempted: bool
    prices: list[PriceEntry]
    summary: SectionSummary


@dataclass(frozen=True)
class Identity:
    wkb: str
    wks: str
    tbl: str
    created: str


@dataclass(frozen=True)
class PricingExport:
    identity: Identity
    equity: SectionExport
    short_calls: SectionExport
    short_puts: SectionExport
    long_calls: SectionExport
    long_puts: SectionExport


EquityFetch = tuple[PriceUpdateResult, list[SymbolPriceOutcome]]
OptionFetch = dict[OptionType, tuple[PriceUpdateResult, list[SymbolPriceOutcome]]]


class PriceExporter:
    """
    Builds the pricing JSON contract and writes it to runtime/pricing/pending/.
    """

    def __init__(self, snapshot: SnapshotTable, locator: ProjectFileLocator | None = None) -> None:
        self._snapshot = snapshot
        self._locator = locator or ProjectFileLocator()

    def export(
            self,
            equity: EquityFetch,
            options: OptionFetch,
            equity_attempted: bool = True,
            attempted_option_types: set[OptionType] | None = None,
    ) -> Path:
        """
        Build the full export and write it atomically to pending/.

        equity is PriceUpdater.fetch_prices()'s return value directly.
        options is OptionPriceUpdater.fetch_all_option_prices()'s return
        value directly - all four OptionType keys must be present.

        equity_attempted and attempted_option_types default to "everything
        was attempted" - a full run() doesn't need to pass either. A
        scoped run passes these explicitly so sections outside its scope
        are marked attempted=False rather than looking identical to a
        genuinely-empty attempted section.

        Writing is atomic (temp file + replace), so a VBA poll of pending/
        never observes a partially written file. Returns the path written.
        """
        _, equity_outcomes = equity
        attempted_types = attempted_option_types if attempted_option_types is not None else set(OptionType)

        export_data = PricingExport(
            identity=self._build_identity(),
            equity=self._build_section(EQUITY, equity_outcomes, equity_attempted),
            short_calls=self._build_section(
                SHORT_CALLS, options[OptionType.SHORT_CALL][1], OptionType.SHORT_CALL in attempted_types),
            short_puts=self._build_section(
                SHORT_PUTS, options[OptionType.SHORT_PUT][1], OptionType.SHORT_PUT in attempted_types),
            long_calls=self._build_section(
                LONG_CALLS, options[OptionType.LONG_CALL][1], OptionType.LONG_CALL in attempted_types),
            long_puts=self._build_section(
                LONG_PUTS, options[OptionType.LONG_PUT][1], OptionType.LONG_PUT in attempted_types),
        )
        return self._write_atomic(export_data)

    def _build_identity(self) -> Identity:
        return Identity(
            wkb=self._snapshot.book.name,
            wks=self._snapshot.sheet.name,
            tbl=self._snapshot.name,
            created=datetime.now().isoformat(),
        )

    @staticmethod
    def _build_section(spec: SectionSpec, outcomes: list[SymbolPriceOutcome], attempted: bool) -> SectionExport:
        succeeded = [o for o in outcomes if o.success]
        failed = [o for o in outcomes if not o.success]
        return SectionExport(
            symbol_column=spec.symbol_column,
            target_column=spec.target_column,
            attempted=attempted,
            prices=[PriceEntry(symbol=o.symbol, price=o.price) for o in succeeded],
            summary=SectionSummary(
                total=len(outcomes),
                succeeded=len(succeeded),
                failed=len(failed),
                failed_symbols=[o.symbol for o in failed],
            ),
        )

    def _filename(self) -> str:
        return f"{Path(self._snapshot.book.name).stem}.json"

    def _write_atomic(self, export_data: PricingExport) -> Path:
        pending_relpath = PENDING_FOLDER / self._filename()
        final_path = self._locator.get_project_file(pending_relpath, must_exist=False)
        if final_path is None:
            raise RuntimeError(f"Could not resolve pending path: {pending_relpath}")

        final_path.parent.mkdir(parents=True, exist_ok=True)

        tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(asdict(export_data), indent=2), encoding="utf-8")
        tmp_path.replace(final_path)  # atomic on both Windows and POSIX
        return final_path