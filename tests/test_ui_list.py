import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QStandardPaths, QStorageInfo, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTreeView,
)

from app.core.application import ApplicationCore
from app.core.session_executable import FOOTER_MAGIC
from app.core.settings_store import SettingsStore
from app.models import ApplicationEntry, Session
from app.ui import main_window as main_window_module
from app.ui.main_window import MainWindow, PersistentFileDialog
from app.ui.styles import apply_global_styles


def populated_core(tmp_path) -> ApplicationCore:
    core = ApplicationCore()
    core.store = SettingsStore(tmp_path / "settings.json")
    core.settings = core.store.load()
    applications = [
        ApplicationEntry.from_path(rf"C:\Apps\Program {number}\launcher.exe")
        for number in range(1, 5)
    ]
    session = Session.create("Приложения")
    session.applications = applications
    core.settings["sessions"] = [session.to_dict()]
    return core


def test_create_exe_uses_highlighted_session_without_export_checkmark(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    core = populated_core(tmp_path)
    destination = tmp_path / "picked.exe"
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "Исполняемый файл (*.exe)"),
    )
    window = MainWindow(core)
    window.show()
    app.processEvents()
    assert window.session_list.currentItem().checkState() == Qt.CheckState.Unchecked
    window.create_session_exe_button.click()
    assert destination.is_file()
    assert destination.read_bytes().endswith(FOOTER_MAGIC)
    window.close()
    app.processEvents()


def test_window_starts_empty_with_session_and_detail_panels(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    core = ApplicationCore()
    core.store = SettingsStore(tmp_path / "settings.json")
    core.settings = core.store.load()
    window = MainWindow(core)
    window.show()
    app.processEvents()

    assert window.session_list.count() == 0
    assert window.session_app_list.count() == 0
    from app.services.ui_scale_service import scale_px

    expected_min = scale_px(300, window.get_ui_scale_factor()) if hasattr(
        window, "get_ui_scale_factor"
    ) else 300
    assert window.minimumHeight() == expected_min

    window.close()
    app.processEvents()


def test_window_shows_session_apps_and_preserves_hidden_data(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    core = populated_core(tmp_path)
    window = MainWindow(core)
    window.show()
    app.processEvents()

    assert not window.findChildren(QTableWidget)
    # В группе масштабирования остаётся только краткая подпись к списку.
    labels = [
        lbl
        for lbl in window.findChildren(QLabel)
        if lbl.text() not in ("Масштаб:", "Пауза")
    ]
    assert not labels
    assert not hasattr(window, "ui_scale_info_label")
    assert window.session_list.count() == 1
    assert window.session_list.item(0).text() == "Приложения"
    window.session_list.setCurrentRow(0)
    app.processEvents()

    assert window.session_app_list.count() == len(core.sessions[0].applications)

    row = window.session_app_list.itemWidget(window.session_app_list.item(0))
    entry = row.build()
    assert row.name_edit.text() == entry.name
    assert entry.path
    assert entry.process_name
    assert entry.action in ("launch", "stop")

    buttons = window.findChildren(QPushButton)
    assert len(buttons) == 11
    assert all(not button.icon().isNull() for button in buttons)
    assert all(button.toolTip() == button.accessibleName() for button in buttons)

    assert window.add_pause_button.toolTip() == "Добавить шаг-паузу в выбранное место сессии"

    assert window.apply_session_button.toolTip() == "Применить сессию"
    assert [button.toolTip() for button in window._action_buttons] == [
        "Применить сессию",
    ]

    window.close()
    app.processEvents()


def test_apply_button_uses_dedicated_green_background(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    apply_global_styles(app)
    core = populated_core(tmp_path)
    window = MainWindow(core)

    assert window.apply_session_button.objectName() == "sessionLaunch"
    stylesheet = app.styleSheet()
    assert "QPushButton#sessionLaunch" in stylesheet
    assert "background: #2f7d4f" in stylesheet
    assert "QPushButton#sessionLaunch:hover" in stylesheet
    assert "QPushButton#sessionLaunch:pressed" in stylesheet

    window.close()
    app.processEvents()


def test_toggling_app_checkbox_updates_session(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    core = populated_core(tmp_path)
    window = MainWindow(core)
    window.session_list.setCurrentRow(0)
    app.processEvents()

    def row_checkbox(row: int) -> Qt.CheckState:
        widget = window.session_app_list.itemWidget(window.session_app_list.item(row))
        return (
            Qt.CheckState.Checked
            if widget.checkbox.isChecked()
            else Qt.CheckState.Unchecked
        )

    window.session_app_list.itemWidget(
        window.session_app_list.item(1)
    ).checkbox.setChecked(False)
    window.session_app_list.itemWidget(
        window.session_app_list.item(3)
    ).checkbox.setChecked(False)
    app.processEvents()

    enabled = [app.name for app in core.sessions[0].applications if app.enabled]
    assert enabled == [
        core.sessions[0].applications[0].name,
        core.sessions[0].applications[2].name,
    ]

    window.session_app_list.itemWidget(
        window.session_app_list.item(1)
    ).checkbox.setChecked(True)
    app.processEvents()
    enabled = [app.name for app in core.sessions[0].applications if app.enabled]
    assert core.sessions[0].applications[1].name in enabled

    window.close()
    app.processEvents()


def test_remove_button_deletes_selected_apps_from_session(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    core = populated_core(tmp_path)
    window = MainWindow(core)

    def fail_if_confirmation_is_shown(*_args, **_kwargs):
        raise AssertionError("Подтверждение удаления не должно отображаться")

    monkeypatch.setattr(QMessageBox, "question", fail_if_confirmation_is_shown)
    window.session_list.setCurrentRow(0)
    app.processEvents()

    names_to_remove = {
        window.session_app_list.itemWidget(
            window.session_app_list.item(1)
        ).name_edit.text(),
        window.session_app_list.itemWidget(
            window.session_app_list.item(3)
        ).name_edit.text(),
    }
    window.session_app_list.item(1).setSelected(True)
    window.session_app_list.item(3).setSelected(True)
    window._remove_session_apps()

    remaining_names = {
        window.session_app_list.item(row).text()
        for row in range(window.session_app_list.count())
    }
    assert not names_to_remove & remaining_names
    assert window.session_app_list.count() == 2
    assert len(core.sessions[0].applications) == 2
    assert window.statusBar().currentMessage() == "Приложения удалены из сессии"

    window.close()
    app.processEvents()


def test_file_dialog_stays_open_after_confirming_a_selection(monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    apply_global_styles(app)
    dialog = PersistentFileDialog()
    assert dialog.selectedNameFilter() == "Все файлы (*)"
    chosen_batches = []
    finished_results = []
    dialog.filesChosen.connect(chosen_batches.append)
    dialog.finished.connect(finished_results.append)
    monkeypatch.setattr(
        dialog,
        "selectedFiles",
        lambda: [r"C:\Apps\First.exe"],
    )
    dialog.show()
    app.processEvents()

    dialog.accept()
    app.processEvents()

    assert chosen_batches == [[r"C:\Apps\First.exe"]]
    assert dialog.isVisible()
    assert finished_results == []

    button_box = dialog.findChild(QDialogButtonBox)
    accept_button = button_box.button(QDialogButtonBox.StandardButton.Open)
    assert accept_button.text() == "Добавить"
    assert accept_button.objectName() == "fileDialogAcceptButton"
    assert accept_button.minimumWidth() == 112
    assert accept_button.minimumHeight() == 36
    assert "padding: 7px 18px" in app.styleSheet()
    assert button_box.button(QDialogButtonBox.StandardButton.Cancel).isHidden()
    QTest.keyClick(dialog, Qt.Key.Key_Escape)
    app.processEvents()
    assert dialog.isVisible()

    dialog.close()
    app.processEvents()
    assert not dialog.isVisible()


def test_file_dialog_sidebar_contains_system_locations_and_recent_folders(
    tmp_path,
) -> None:
    QApplication.instance() or QApplication([])
    recent_directory = tmp_path / "Recent App Folder"
    recent_directory.mkdir()

    dialog = PersistentFileDialog(recent_directories=[str(recent_directory)])
    sidebar_paths = {
        str(Path(url.toLocalFile()).resolve()).casefold()
        for url in dialog.sidebarUrls()
        if url.toLocalFile()
    }
    desktop = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DesktopLocation
    )
    home = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.HomeLocation)
    mounted_drives = {
        str(Path(volume.rootPath()).resolve()).casefold()
        for volume in QStorageInfo.mountedVolumes()
        if volume.isValid() and volume.isReady()
    }

    assert any(not url.toLocalFile() for url in dialog.sidebarUrls())
    assert str(Path(desktop).resolve()).casefold() in sidebar_paths
    assert str(Path(home).resolve()).casefold() in sidebar_paths
    assert str(recent_directory.resolve()).casefold() in sidebar_paths
    assert mounted_drives <= sidebar_paths


def test_file_dialog_shows_creation_date_column(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    executable = tmp_path / "Created App.exe"
    executable.touch()
    dialog = PersistentFileDialog()
    dialog.setDirectory(str(tmp_path))
    dialog.show()
    for _ in range(10):
        app.processEvents()

    tree_view = dialog.findChild(QTreeView, "treeView")
    model = tree_view.model()
    root_index = tree_view.rootIndex()
    creation_column = model.columnCount(root_index) - 1
    executable_row = next(
        row
        for row in range(model.rowCount(root_index))
        if model.data(model.index(row, 0, root_index)) == executable.name
    )
    creation_index = model.index(executable_row, creation_column, root_index)
    source_index = dialog.proxyModel().mapToSource(creation_index)

    assert model.headerData(creation_column, Qt.Orientation.Horizontal) == "Дата создания"
    assert creation_index.isValid()
    assert model.data(creation_index)
    assert Path(dialog.proxyModel().sourceModel().filePath(source_index)) == executable

    dialog.close()
    app.processEvents()


def test_add_button_collects_applications_until_dialog_is_closed(
    tmp_path, monkeypatch
) -> None:
    app = QApplication.instance() or QApplication([])
    core = ApplicationCore()
    core.store = SettingsStore(tmp_path / "settings.json")
    core.settings = core.store.load()
    window = MainWindow(core)

    class SelectionSignal:
        def connect(self, callback) -> None:
            self.callback = callback

        def emit(self, paths: list[str]) -> None:
            self.callback(paths)

    class FakePersistentFileDialog:
        def __init__(self, _parent, _recent_directories) -> None:
            self.filesChosen = SelectionSignal()

        def exec(self) -> int:
            self.filesChosen.emit([r"C:\Folder One\First.exe"])
            self.filesChosen.emit(
                [r"D:\Folder Two\Second.exe", r"c:\folder one\first.exe"]
            )
            return 0

    monkeypatch.setattr(
        main_window_module,
        "PersistentFileDialog",
        FakePersistentFileDialog,
    )

    window._create_session()
    assert window.current_session_id is not None
    window._add_apps_to_session()

    session = core.get_session(window.current_session_id)
    assert [item.path for item in session.applications] == [
        r"C:\Folder One\First.exe",
        r"D:\Folder Two\Second.exe",
    ]
    assert [item.name for item in session.applications] == ["Folder One", "Folder Two"]
    assert window.session_app_list.count() == 2
    assert window.statusBar().currentMessage() == "Программы и файлы добавлены в сессию"

    window.close()
    app.processEvents()


def test_added_file_is_shown_as_open_step(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    core = ApplicationCore()
    core.store = SettingsStore(tmp_path / "settings.json")
    core.settings = core.store.load()
    window = MainWindow(core)

    class SelectionSignal:
        def connect(self, callback) -> None:
            self.callback = callback

        def emit(self, paths: list[str]) -> None:
            self.callback(paths)

    class FakePersistentFileDialog:
        def __init__(self, _parent, _recent_directories) -> None:
            self.filesChosen = SelectionSignal()

        def exec(self) -> int:
            self.filesChosen.emit([str(tmp_path / "notes.txt")])
            return 0

    monkeypatch.setattr(
        main_window_module, "PersistentFileDialog", FakePersistentFileDialog
    )
    window._create_session()
    window._add_apps_to_session()

    saved = core.get_session(window.current_session_id)
    row = window.session_app_list.itemWidget(window.session_app_list.item(0))
    assert saved.applications[0].name == "notes.txt"
    assert saved.applications[0].action == "open"
    assert row.action_combo.currentData() == "open"
    assert row.action_combo.count() == 1

    window.close()
    app.processEvents()


def test_add_pause_step_inserts_into_session(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    core = populated_core(tmp_path)
    window = MainWindow(core)
    window.session_list.setCurrentRow(0)
    app.processEvents()

    assert window.session_app_list.count() == 4
    window.session_app_list.setCurrentRow(1)
    window._add_pause()
    app.processEvents()

    assert window.session_app_list.count() == 5
    row = window.session_app_list.itemWidget(window.session_app_list.item(2))
    entry = row.build()
    assert entry.is_pause is True
    assert entry.duration == 1
    assert window.session_app_list.currentRow() == 2

    row.duration_combo.setCurrentIndex(row.duration_combo.findData(7))
    app.processEvents()
    saved = core.get_session(window.current_session_id)
    pause_entries = [app for app in saved.applications if app.is_pause]
    assert len(pause_entries) == 1
    assert pause_entries[0].duration == 7
    assert pause_entries[0].enabled is True

    window.close()
    app.processEvents()


def test_move_buttons_reorder_session_apps(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    core = populated_core(tmp_path)
    window = MainWindow(core)
    window.session_list.setCurrentRow(0)
    app.processEvents()

    names_before = [app.name for app in core.sessions[0].applications]
    assert names_before == ["Program 1", "Program 2", "Program 3", "Program 4"]

    window.session_app_list.setCurrentRow(1)
    window._move_selected_app(1)
    app.processEvents()

    names_after = [app.name for app in core.sessions[0].applications]
    assert names_after == ["Program 1", "Program 3", "Program 2", "Program 4"]

    window.session_app_list.setCurrentRow(0)
    window._move_selected_app(-1)
    app.processEvents()
    assert window.session_app_list.currentRow() == 0

    window.close()
    app.processEvents()


def test_ctrl_and_shift_click_follow_explorer_selection_model(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    core = populated_core(tmp_path)
    window = MainWindow(core)
    window.session_list.setCurrentRow(0)
    window.show()
    app.processEvents()

    def click(row: int, modifier: Qt.KeyboardModifier = Qt.KeyboardModifier.NoModifier) -> None:
        item = window.session_app_list.item(row)
        position = window.session_app_list.visualItemRect(item).center()
        QTest.mouseClick(
            window.session_app_list.viewport(),
            Qt.MouseButton.LeftButton,
            modifier,
            position,
        )

    def selected_rows() -> set[int]:
        return {index.row() for index in window.session_app_list.selectedIndexes()}

    click(0)
    assert selected_rows() == {0}
    click(2, Qt.KeyboardModifier.ShiftModifier)
    assert selected_rows() == {0, 1, 2}
    click(1, Qt.KeyboardModifier.ControlModifier)
    assert selected_rows() == {0, 2}

    window.close()
    app.processEvents()


def test_window_geometry_is_saved_and_restored(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    settings_path = tmp_path / "settings.json"
    core = ApplicationCore()
    core.store = SettingsStore(settings_path)
    core.settings = core.store.load()
    window = MainWindow(core)
    window.move(20, 30)
    window.resize(820, 480)
    window.show()
    app.processEvents()
    # из-за авто-масштаба startup может сделать fit-to-content — берём фактический размер после show
    actual_w = window.size().width()
    actual_h = window.size().height()
    window.close()
    app.processEvents()

    saved = SettingsStore(settings_path).load()
    assert saved["window_geometry"]
    assert saved["window_width"] == actual_w
    assert saved["window_height"] == actual_h

    restored_core = ApplicationCore()
    restored_core.store = SettingsStore(settings_path)
    restored_core.settings = restored_core.store.load()
    restored_window = MainWindow(restored_core)
    assert abs(restored_window.size().width() - actual_w) <= 24
    assert abs(restored_window.size().height() - actual_h) <= 24
    restored_window.close()
    app.processEvents()


def test_session_can_be_created_and_receive_applications(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    core = ApplicationCore()
    core.store = SettingsStore(tmp_path / "settings.json")
    core.settings = core.store.load()
    window = MainWindow(core)
    window.show()
    app.processEvents()

    assert window.session_list.count() == 0
    window.new_session_button.click()
    assert window.session_list.count() == 1
    assert len(core.sessions) == 1
    session_id = core.sessions[0].id
    assert window.current_session_id == session_id

    class SelectionSignal:
        def connect(self, callback) -> None:
            self.callback = callback

        def emit(self, paths: list[str]) -> None:
            self.callback(paths)

    class FakePersistentFileDialog:
        def __init__(self, _parent, _recent_directories) -> None:
            self.filesChosen = SelectionSignal()

        def exec(self) -> int:
            self.filesChosen.emit([r"C:\SessionApp\tool.exe"])
            return 0

    monkeypatch.setattr(
        main_window_module,
        "PersistentFileDialog",
        FakePersistentFileDialog,
    )
    window._add_apps_to_session()
    app.processEvents()

    assert window.session_app_list.count() == 1
    assert core.get_session(session_id).applications[0].name == "SessionApp"

    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    window.delete_session_button.click()
    app.processEvents()
    assert window.session_list.count() == 0
    assert len(core.sessions) == 0

    window.close()
    app.processEvents()


def test_session_import_and_export_buttons(tmp_path, monkeypatch) -> None:
    app = QApplication.instance() or QApplication([])
    core = populated_core(tmp_path)
    window = MainWindow(core)
    window.show()
    app.processEvents()
    export_path = tmp_path / "exported.json"

    class FakeFileDialog:
        @staticmethod
        def getSaveFileName(*_args):
            return str(export_path), ""

        @staticmethod
        def getOpenFileName(*_args):
            return str(export_path), ""

    monkeypatch.setattr(main_window_module, "QFileDialog", FakeFileDialog)
    window.export_sessions_button.click()
    assert not export_path.exists()
    assert window.statusBar().currentMessage() == "Отметьте галочками сессии для экспорта"

    window.session_list.item(0).setCheckState(Qt.CheckState.Checked)
    assert core.sessions[0].export_selected is True
    assert core.store.load()["sessions"][0]["export_selected"] is True
    assert window.current_session_id == core.sessions[0].id
    window.export_sessions_button.click()
    assert export_path.is_file()
    assert window.statusBar().currentMessage() == "Экспортировано сессий: 1"

    window.import_sessions_button.click()
    assert len(core.sessions) == 1
    assert window.session_list.count() == 1
    assert window.current_session_id == core.sessions[0].id
    assert window.session_list.item(0).checkState() == Qt.CheckState.Checked
    assert window.statusBar().currentMessage() == "Импортировано сессий: 1"

    window.close()
    app.processEvents()
