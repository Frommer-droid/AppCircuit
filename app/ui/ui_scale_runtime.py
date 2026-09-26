from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from app.services.ui_scale_service import (
    UIScaleState,
    resolve_ui_scale_from_screen,
)
from app.ui.styles import apply_global_styles
from app.ui.ui_scale_overrides import apply_scale_to_widget, ensure_text_control_heights

if TYPE_CHECKING:
    from app.ui.main_window import MainWindow


def _get_active_screen(window: MainWindow):
    handle = window.windowHandle()
    if handle is not None and handle.screen() is not None:
        return handle.screen()
    screen = QGuiApplication.primaryScreen()
    if screen is not None:
        return screen
    # fallback: first screen
    screens = QGuiApplication.screens()
    return screens[0] if screens else None


def _get_screen_metrics(screen) -> tuple[int, int, float]:
    if screen is None:
        return 1920, 1080, 96.0
    geom = screen.availableGeometry()
    try:
        dpi = float(screen.logicalDotsPerInch())
    except (TypeError, ValueError):
        dpi = 96.0
    if dpi <= 0:
        dpi = 96.0
    return int(geom.width()), int(geom.height()), dpi


def resolve_scale_for_window(window: MainWindow, delta_percent: int) -> UIScaleState:
    screen = _get_active_screen(window)
    w, h, dpi = _get_screen_metrics(screen)
    return resolve_ui_scale_from_screen(w, h, dpi, delta_percent)


def apply_ui_scale_to_app_and_window(
    window: MainWindow,
    state: UIScaleState,
    allow_window_resize: bool,
    previous_scale_factor: float,
) -> None:
    app = QApplication.instance()
    if app is not None:
        apply_global_styles(app, scale_factor=state.scale_factor)  # type: ignore[arg-type]

    # локальные метрики окна
    apply_scale_to_widget(window, state.scale_factor)
    ensure_text_control_heights(window, state.scale_factor)
    window.refresh_session_app_row_heights(state.scale_factor)

    # обновить открытые дочерние окна/диалоги (если есть)
    if app is not None:
        for widget in app.topLevelWidgets():
            if widget is window:
                continue
            if widget.isWindow() and widget.isVisible():
                try:
                    apply_scale_to_widget(widget, state.scale_factor)  # type: ignore[arg-type]
                    ensure_text_control_heights(widget, state.scale_factor)
                except (RuntimeError, AttributeError):
                    continue

    if allow_window_resize and not window.isMaximized():
        # Пересчитываем размер относительно предыдущего масштаба, а не
        # относительно уже сохранённой высоты. Это исключает накопительное
        # увеличение при выборе 120% -> 130% и сохраняет пользовательский размер.
        previous_factor = max(float(previous_scale_factor), 0.01)
        ratio = state.scale_factor / previous_factor
        hint = window.sizeHint()
        target_width = max(int(hint.width()), int(round(window.width() * ratio)), 400)
        target_height = max(int(hint.height()), int(round(window.height() * ratio)), 300)
        window.resize(target_width, target_height)
        geometry = window.normalGeometry()
        window.core.settings.update(
            {
                "window_pos_x": geometry.x(),
                "window_pos_y": geometry.y(),
                "window_width": geometry.width(),
                "window_height": geometry.height(),
                "window_geometry": bytes(window.saveGeometry().toBase64()).decode("ascii"),
                "maximized": False,
            }
        )
        window.core.save()


def install_ui_scale_hooks(window: MainWindow) -> None:
    # вызывается после show() и processEvents(), когда у окна есть windowHandle
    handle = window.windowHandle()
    if handle is None:
        return
    # window screen changed
    try:
        handle.screenChanged.connect(window.on_ui_scale_window_screen_changed)  # type: ignore[attr-defined]
        window._ui_scale_window_hook_installed = True  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError):
        pass
    _install_screen_hooks(window)
    _install_app_hooks(window)


def _install_screen_hooks(window: MainWindow) -> None:
    screen = _get_active_screen(window)
    if screen is None:
        return
    # отключаем старые
    old = getattr(window, "_ui_scale_screen", None)
    if old is not None and old is not screen:
        _disconnect_screen(old, window)
    window._ui_scale_screen = screen  # type: ignore[attr-defined]
    try:
        screen.logicalDotsPerInchChanged.connect(window.on_ui_scale_screen_metrics_changed)  # type: ignore[attr-defined]
        screen.geometryChanged.connect(window.on_ui_scale_screen_metrics_changed)  # type: ignore[attr-defined]
        screen.availableGeometryChanged.connect(window.on_ui_scale_screen_metrics_changed)  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError):
        pass


def _disconnect_screen(screen, window: MainWindow) -> None:
    try:
        screen.logicalDotsPerInchChanged.disconnect(window.on_ui_scale_screen_metrics_changed)  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError, TypeError):
        pass
    try:
        screen.geometryChanged.disconnect(window.on_ui_scale_screen_metrics_changed)  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError, TypeError):
        pass
    try:
        screen.availableGeometryChanged.disconnect(window.on_ui_scale_screen_metrics_changed)  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError, TypeError):
        pass


def _install_app_hooks(window: MainWindow) -> None:
    if getattr(window, "_ui_scale_app_hooks_installed", False):
        return
    app = QApplication.instance()
    if app is None:
        return
    try:
        app.primaryScreenChanged.connect(window.on_ui_scale_topology_changed)  # type: ignore[attr-defined]
        app.screenAdded.connect(window.on_ui_scale_topology_changed)  # type: ignore[attr-defined]
        app.screenRemoved.connect(window.on_ui_scale_topology_changed)  # type: ignore[attr-defined]
        window._ui_scale_app_hooks_installed = True  # type: ignore[attr-defined]
    except (AttributeError, RuntimeError):
        pass


def uninstall_ui_scale_hooks(window: MainWindow) -> None:
    handle = window.windowHandle()
    if handle is not None and getattr(window, "_ui_scale_window_hook_installed", False):
        try:
            handle.screenChanged.disconnect(window.on_ui_scale_window_screen_changed)  # type: ignore[attr-defined]
        except (AttributeError, RuntimeError, TypeError):
            pass
        window._ui_scale_window_hook_installed = False  # type: ignore[attr-defined]
    old = getattr(window, "_ui_scale_screen", None)
    if old is not None:
        _disconnect_screen(old, window)
        window._ui_scale_screen = None  # type: ignore[attr-defined]
    if getattr(window, "_ui_scale_app_hooks_installed", False):
        app = QApplication.instance()
        if app is not None:
            try:
                app.primaryScreenChanged.disconnect(window.on_ui_scale_topology_changed)  # type: ignore[attr-defined]
            except (AttributeError, RuntimeError, TypeError):
                pass
            try:
                app.screenAdded.disconnect(window.on_ui_scale_topology_changed)  # type: ignore[attr-defined]
            except (AttributeError, RuntimeError, TypeError):
                pass
            try:
                app.screenRemoved.disconnect(window.on_ui_scale_topology_changed)  # type: ignore[attr-defined]
            except (AttributeError, RuntimeError, TypeError):
                pass
        window._ui_scale_app_hooks_installed = False  # type: ignore[attr-defined]
