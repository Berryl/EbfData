import xlwings as xw


class SuspendAppUpdates:
    """
    Context manager that suspends Excel screen updating and calculation,
    then restores the original state on exit — whether an exception occurred or not.
    Captures state on entry rather than assuming defaults, so it composes safely with
    other code that may have already changed these settings.

    Usage:
        with SuspendAppUpdates(app):
            # bulk writes here
    """

    def __init__(self, app: xw.App) -> None:
        self._app = app
        self._screen_updating: bool | None = None
        self._calculation: str | None = None

    def __enter__(self) -> "SuspendAppUpdates":
        self._screen_updating = self._app.screen_updating
        self._calculation = self._app.calculation
        self._app.screen_updating = False
        self._app.calculation = "manual"
        return self

    def __exit__(self, *_) -> None:
        self._app.calculation = self._calculation
        self._app.screen_updating = self._screen_updating
