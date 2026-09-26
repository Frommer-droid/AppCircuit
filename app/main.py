from __future__ import annotations

import ctypes
import logging
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.core.app_config import APP_NAME, APP_USER_MODEL_ID, APP_VERSION, ICON_FILE
from app.core.application import ApplicationCore
from app.core.localization import install_russian_translations, set_russian_locale
from app.ui.main_window import MainWindow
from app.ui.styles import apply_global_styles
from app.utils.logging_utils import configure_logging

LOGGER = logging.getLogger(__name__)


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except OSError:
        LOGGER.exception("Не удалось установить AppUserModelID")


def main() -> int:
    configure_logging()
    _set_windows_app_id()
    set_russian_locale()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app._russian_translators = install_russian_translations(app)
    if ICON_FILE.is_file():
        app.setWindowIcon(QIcon(str(ICON_FILE)))

    core = ApplicationCore()
    # начальный масштаб от primary screen до создания окна, чтобы избежать моргания
    try:
        from PySide6.QtGui import QGuiApplication

        from app.services.ui_scale_service import resolve_ui_scale_from_screen

        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            geom = screen.availableGeometry()
            dpi = float(screen.logicalDotsPerInch() or 96.0)
            delta = int(core.settings.get("ui_scale_delta_percent", 0))
            state = resolve_ui_scale_from_screen(
                int(geom.width()), int(geom.height()), dpi, delta
            )
            apply_global_styles(app, scale_factor=state.scale_factor)
            core.settings["ui_scale_percent"] = int(state.final_percent)
            core.settings["ui_scale_mode"] = "auto"
            core.save()
        else:
            apply_global_styles(app)
    except (AttributeError, RuntimeError, TypeError, ValueError):
        apply_global_styles(app)

    window = MainWindow(core)
    window.show()
    return app.exec()
