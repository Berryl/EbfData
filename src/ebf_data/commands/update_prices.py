from ebf_data.excel.snapshot.price_updater import PriceUpdater
from ebf_data.excel.snapshot.snapshot_table import SnapshotTable


def main() -> None:
    updater = PriceUpdater(SnapshotTable())
    updater.update_prices()


if __name__ == "__main__":
    main()