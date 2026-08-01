"""Serializes fetched prices into the JSON contract consumed by the VBA pricing updater.

PriceExporter takes the price-fetch results produced by PriceUpdater and
OptionPriceUpdater (equity plus the four option legs) and writes a single
JSON file under runtime/pricing/pending/. VBA later moves that file to
runtime/pricing/updated/ once it has applied the prices to the workbook,
overwriting any existing file of the same name in each folder.

Failures are dropped entirely rather than carried through as "existing"
values. VBA just skips symbols that don't appear in a section's price
list, leaving those cells at whatever value was last successfully written.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Sequence

from ebf_core.fileutil.project_file_locator import ProjectFileLocator

from ebf_data.excel.pricing.price_fetcher import PriceUpdateResult


@dataclass(frozen=True)
class SectionSpec:
    """Static config for one of the five price sections.

    key is the JSON key used in the output file. symbol_column and
    target_column are the Excel column headers VBA reads from / writes to.
    """

    key: str
    symbol_column: str
    target_column: str


EQUITY = SectionSpec(key="equity", symbol_column="Symbol", target_column="Last Price")
SHORT_CALLS = SectionSpec(key="short_calls", symbol_column="SC Symbol", target_column="SC Current Ask")
SHORT_PUTS = SectionSpec(key="short_puts", symbol_column="SP Symbol", target_column="SP Current Ask")
LONG_CALLS = SectionSpec(key="long_calls", symbol_column="LC Symbol", target_column="LC Contract Value")
LONG_PUTS = SectionSpec(key="long_puts", symbol_column="LP Symbol", target_column="LP Contract Value")


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


class PriceExporter:
    """Builds the pricing JSON contract and writes it to the pending folder.

    One PriceExporter instance corresponds to one workbook (production
    snapshot or a scenario workbook). The output filename is derived from
    the workbook name so scenario workbooks flow through the same pipeline
    as production without colliding on disk.
    """

    def __init__(self, wkb: str, wks: str, tbl: str, locator: ProjectFileLocator | None = None) -> None:
        self._wkb = wkb
        self._wks = wks
        self._tbl = tbl
        self._locator = locator or ProjectFileLocator()

    @property
    def _pending_dir(self) -> Path:
        return self._locator.resolve("runtime/pricing/pending")

    def _filename(self) -> str:
        return f"{Path(self._wkb).stem}.json"

    def export(
        self,
        equity_results: Sequence[PriceUpdateResult],
        short_call_results: Sequence[PriceUpdateResult],
        short_put_results: Sequence[PriceUpdateResult],
        long_call_results: Sequence[PriceUpdateResult],
        long_put_results: Sequence[PriceUpdateResult],
    ) -> Path:
        """Builds the full export and writes it atomically to pending/.

        Writing is atomic (temp file + replace) so a VBA poll of pending/
        never observes a partially written file. Returns the path written.
        """
        export = PricingExport(
            identity=Identity(
                wkb=self._wkb,
                wks=self._wks,
                tbl=self._tbl,
                created=datetime.now().isoformat(),
            ),
            equity=self._build_section(EQUITY, equity_results),
            short_calls=self._build_section(SHORT_CALLS, short_call_results),
            short_puts=self._build_section(SHORT_PUTS, short_put_results),
            long_calls=self._build_section(LONG_CALLS, long_call_results),
            long_puts=self._build_section(LONG_PUTS, long_put_results),
        )
        return self._write_atomic(export)

    @staticmethod
    def _build_section(spec: SectionSpec, results: Sequence[PriceUpdateResult]) -> SectionExport:
        succeeded = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        return SectionExport(
            symbol_column=spec.symbol_column,
            target_column=spec.target_column,
            prices=[PriceEntry(symbol=r.symbol, price=r.price) for r in succeeded],
            summary=SectionSummary(
                total=len(results),
                succeeded=len(succeeded),
                failed=len(failed),
                failed_symbols=[r.symbol for r in failed],
            ),
        )

    def _write_atomic(self, export: PricingExport) -> Path:
        self._pending_dir.mkdir(parents=True, exist_ok=True)
        final_path = self._pending_dir / self._filename()
        tmp_path = final_path.with_suffix(final_path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(asdict(export), indent=2), encoding="utf-8")
        tmp_path.replace(final_path)  # atomic on both Windows and POSIX
        return final_path