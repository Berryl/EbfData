from unittest.mock import MagicMock

from ebf_data.excel.infrastructure.suspend_app_updates import SuspendAppUpdates


def test_suspends_and_restores():
    app = MagicMock()
    app.screen_updating = True
    app.calculation = "automatic"

    with SuspendAppUpdates(app):
        assert app.screen_updating is False
        assert app.calculation == "manual"

    assert app.screen_updating is True
    assert app.calculation == "automatic"
    app.api.Calculate.assert_called_once()