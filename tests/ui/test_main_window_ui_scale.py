import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLineEdit

from app.core.application import ApplicationCore
from app.core.settings_store import SettingsStore
from app.ui.main_window import MainWindow
from app.ui.styles import apply_global_styles
from app.ui.ui_scale_overrides import apply_scale_to_widget, ensure_text_control_heights


def test_manual_delta_saves_and_updates_scale(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    core = ApplicationCore()
    core.store = SettingsStore(tmp_path / "settings.json")
    core.settings = core.store.load()
    window = MainWindow(core)
    window.show()
    app.processEvents()

    # set delta to 20% (120% displayed)
    idx = window.ui_scale_combo.findData(20)
    window.ui_scale_combo.setCurrentIndex(idx)
    app.processEvents()

    assert core.settings["ui_scale_delta_percent"] == 20
    assert window.get_ui_scale_factor() > 0
    persisted = core.store.load()
    assert persisted["window_width"] == window.normalGeometry().width()
    assert persisted["window_height"] == window.normalGeometry().height()
    assert persisted["window_geometry"]

    window.close()
    app.processEvents()


def test_first_launch_fits_all_button_labels_after_auto_scale(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    apply_global_styles(app)
    core = ApplicationCore()
    core.store = SettingsStore(tmp_path / "settings.json")
    core.settings = core.store.load()
    assert core.settings["window_width"] is None

    window = MainWindow(core)
    window.show()
    app.processEvents()

    assert all(button.width() >= button.sizeHint().width() for button in window._all_buttons)
    assert window.width() > 400

    window.close()
    app.processEvents()


def test_session_rows_keep_matching_unclipped_name_fields_at_every_scale(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    core = ApplicationCore()
    core.store = SettingsStore(tmp_path / "settings.json")
    core.settings = core.store.load()
    core.settings["sessions"] = [
        {
            "id": "session-1",
            "name": "Тестовая сессия",
            "applications": [
                {
                    "id": "app-1",
                    "name": "Очень длинное название приложения",
                    "path": "D:/apps/example.exe",
                    "process_name": "example.exe",
                },
                {
                    "id": "pause-1",
                    "name": "Пауза",
                    "path": "",
                    "process_name": "",
                    "action": "pause",
                    "is_pause": True,
                    "duration": 5,
                },
            ],
        }
    ]
    window = MainWindow(core)
    window.show()
    app.processEvents()

    for factor in (0.7, 1.0, 1.2, 2.0, 3.0):
        apply_global_styles(app, scale_factor=factor)
        apply_scale_to_widget(window, factor)
        ensure_text_control_heights(window, factor)
        window.refresh_session_app_row_heights(factor)
        app.processEvents()

        application_item = window.session_app_list.item(0)
        pause_item = window.session_app_list.item(1)
        application_row = window.session_app_list.itemWidget(application_item)
        pause_row = window.session_app_list.itemWidget(pause_item)
        assert application_row is not None
        assert pause_row is not None

        application_field = application_row.name_edit
        pause_field = pause_row.name_edit
        assert isinstance(application_field, QLineEdit)
        assert isinstance(pause_field, QLineEdit)
        assert pause_field.isReadOnly()
        assert pause_field.styleSheet() == application_field.styleSheet() == ""
        assert pause_field.minimumWidth() == application_field.minimumWidth()
        assert pause_field.minimumHeight() == application_field.minimumHeight()
        assert pause_field.height() == application_field.height()
        assert pause_row.duration_combo.minimumWidth() == application_row.action_combo.minimumWidth()
        assert pause_row.duration_combo.width() == application_row.action_combo.width()
        assert pause_field.width() == application_field.width()
        assert pause_row.layout().contentsMargins() == application_row.layout().contentsMargins()

        for item, row, text_field in (
            (application_item, application_row, application_field),
            (pause_item, pause_row, pause_field),
        ):
            margins = row.layout().contentsMargins()
            required_row_height = (
                text_field.minimumHeight() + margins.top() + margins.bottom()
            )
            assert text_field.height() >= text_field.minimumHeight()
            assert text_field.height() >= text_field.fontMetrics().height()
            assert item.sizeHint().height() >= required_row_height
            assert row.height() >= required_row_height
            assert text_field.geometry().top() >= margins.top()
            assert text_field.geometry().bottom() < row.height() - margins.bottom()
            assert window.session_app_list.visualItemRect(item).height() >= row.height()

    window.close()
    app.processEvents()


def test_screen_metrics_change_does_not_force_resize(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    core = ApplicationCore()
    core.store = SettingsStore(tmp_path / "settings.json")
    core.settings = core.store.load()
    window = MainWindow(core)
    window.show()
    app.processEvents()
    window.resize(800, 500)
    app.processEvents()
    before = window.size()

    # simulate screen metrics change: should not force resize
    window.on_ui_scale_screen_metrics_changed()
    app.processEvents()
    after = window.size()
    # size may change slightly due to scale factor, but should not be forced to hint
    # For this test we check that resize policy respects allow_window_resize=False
    # So window size should remain close to before (or at least not drastically changed to hint)
    # We allow small drift due to stylesheet but not full fit
    assert abs(after.width() - before.width()) < 200

    window.close()
    app.processEvents()
