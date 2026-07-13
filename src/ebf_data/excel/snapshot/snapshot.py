def main():

    from ebf_data.excel.snapshot.snapshot_table import SnapshotTable
    from ebf_data.excel.snapshot.price_updater import PriceUpdater

    snapshot = SnapshotTable()
    PriceUpdater(snapshot).update_prices()