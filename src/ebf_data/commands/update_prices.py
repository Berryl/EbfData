from ebf_data.excel.snapshot.price_updater import PriceUpdater
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable


def main() -> None:
    updater = PriceUpdater(SnapshotTable())
    result = updater.update_prices()

    if result.failed:
        raise RuntimeError(
            f"Price update completed with failures: {', '.join(result.failed)}"
        )


if __name__ == "__main__":
    main()