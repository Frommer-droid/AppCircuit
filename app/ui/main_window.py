from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QByteArray, QObject, QSize, Qt, QThread, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.core.app_config import APP_NAME, APP_VERSION, ICONS_DIR
from app.core.application import ApplicationCore
from app.core.session_executable import create_session_executable, suggested_executable_name
from app.models import ApplicationEntry, Session
from app.services.process_service import ActionReport
from app.services.ui_scale_service import normalize_ui_scale_delta_percent, scale_px
from app.ui.file_dialog import PersistentFileDialog
from app.ui.styles import LIST_ITEM_VERTICAL_PADDING
from app.ui.ui_scale_overrides import apply_scale_to_widget, ensure_text_control_heights
from app.ui.ui_scale_runtime import (
    apply_ui_scale_to_app_and_window,
    install_ui_scale_hooks,
    resolve_scale_for_window,
)

SESSION_ROW_TRAILING_CONTROL_MIN_WIDTH = 112


class ActionWorker(QObject):
    finished = Signal(object)

    def __init__(
        self,
        core: ApplicationCore,
        action: str,
        applications: list[ApplicationEntry],
    ) -> None:
        super().__init__()
        self.core = core
        self.action = action
        self.applications = applications

    @Slot()
    def run(self) -> None:
        try:
            report = self.core.run_action(self.action, self.applications)
        except Exception as exc:  # страховка на границе фонового потока
            report = ActionReport("Операция", failed=[str(exc)])
        self.finished.emit(report)


class SessionActionWorker(QObject):
    finished = Signal(object)

    def __init__(self, core: ApplicationCore, session: Session) -> None:
        super().__init__()
        self.core = core
        self.session = session

    @Slot()
    def run(self) -> None:
        try:
            report = self.core.run_session_action(self.session)
        except Exception as exc:
            report = ActionReport("Операция", failed=[str(exc)])
        self.finished.emit(report)


class SessionAppRow(QWidget):
    changed = Signal()

    def __init__(self, entry: ApplicationEntry, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entry = entry
        self._is_pause = entry.is_pause
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        self.checkbox = QCheckBox(self)
        self.checkbox.setChecked(entry.enabled)
        self.checkbox.setToolTip("Включить шаг в сессию")
        layout.addWidget(self.checkbox)

        self.name_edit = QLineEdit(self)
        self.name_edit.setText("Пауза" if self._is_pause else entry.name)
        self.name_edit.setMinimumWidth(120)
        layout.addWidget(self.name_edit, 1)

        if self._is_pause:
            self.name_edit.setReadOnly(True)
            self.name_edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.name_edit.setAccessibleName("Шаг паузы")

            self.duration_combo = QComboBox(self)
            self.duration_combo.setMinimumWidth(
                SESSION_ROW_TRAILING_CONTROL_MIN_WIDTH
            )
            for seconds in range(1, 11):
                self.duration_combo.addItem(f"{seconds} с", seconds)
            duration_index = self.duration_combo.findData(int(entry.duration))
            if duration_index >= 0:
                self.duration_combo.setCurrentIndex(duration_index)
            self.duration_combo.setToolTip("Длительность паузы")
            layout.addWidget(self.duration_combo)
            self.duration_combo.currentIndexChanged.connect(
                lambda _=None: self.changed.emit()
            )
        else:
            self.action_combo = QComboBox(self)
            self.action_combo.setMinimumWidth(
                SESSION_ROW_TRAILING_CONTROL_MIN_WIDTH
            )
            if Path(entry.path).suffix.casefold() == ".exe":
                self.action_combo.addItem("Запустить", "launch")
                self.action_combo.addItem("Остановить", "stop")
            else:
                self.action_combo.addItem("Открыть", "open")
            index = self.action_combo.findData(entry.action)
            if index >= 0:
                self.action_combo.setCurrentIndex(index)
            self.action_combo.setToolTip("Действие при применении сессии")
            layout.addWidget(self.action_combo)
            self.name_edit.textEdited.connect(lambda _=None: self.changed.emit())
            self.action_combo.currentIndexChanged.connect(
                lambda _=None: self.changed.emit()
            )

        self.checkbox.toggled.connect(lambda _=None: self.changed.emit())

    def build(self) -> ApplicationEntry:
        if self._is_pause:
            return ApplicationEntry(
                id=self._entry.id,
                name="Пауза",
                path="",
                process_name="",
                enabled=self.checkbox.isChecked(),
                action="pause",
                is_pause=True,
                duration=int(self.duration_combo.currentData()),
            )
        name = self.name_edit.text().strip() or ApplicationEntry.default_name_for_path(
            getattr(self._entry, "path", "") or "app"
        )
        return ApplicationEntry(
            id=self._entry.id,
            name=name,
            path=str(getattr(self._entry, "path", "")),
            process_name=str(getattr(self._entry, "process_name", "")),
            enabled=self.checkbox.isChecked(),
            action=str(self.action_combo.currentData()),
        )


class MainWindow(QMainWindow):
    def __init__(self, core: ApplicationCore) -> None:
        super().__init__()
        self.core = core
        self._thread: QThread | None = None
        self._worker: QObject | None = None
        self._busy = False
        self._ui_scale_state = None
        self._ui_scale_factor = 1.0
        self._ui_scale_screen = None
        self._ui_scale_app_hooks_installed = False
        self._ui_scale_window_hook_installed = False
        self._ui_scale_initialized = False

        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self._build_ui()
        self._restore_window_state()

    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal, central)
        layout.addWidget(splitter, 1)

        self._build_sessions_panel(splitter)
        self._build_session_detail_panel(splitter)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        for button in self._all_buttons:
            button.setAccessibleName(button.toolTip())
        self._refresh_session_list()

        self.setCentralWidget(central)
        self.setMinimumHeight(300)
        self.statusBar().showMessage("Готово")

    # ------------------------------------------------------------------ #
    # Левая панель: список сессий                                        #
    # ------------------------------------------------------------------ #

    def _build_sessions_panel(self, parent: QSplitter) -> None:
        left = QWidget(parent)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(6)

        self.session_list = QListWidget(left)
        self.session_list.setUniformItemSizes(True)
        self.session_list.setMinimumSize(0, 0)
        self.session_list.currentItemChanged.connect(self._on_session_selected)
        self.session_list.itemChanged.connect(self._on_session_export_toggled)
        left_layout.addWidget(self.session_list, 1)

        session_toolbar = QHBoxLayout()
        session_toolbar.setContentsMargins(0, 0, 0, 0)
        session_toolbar.setSpacing(6)
        self.new_session_button = QPushButton("Новая", left)
        self.new_session_button.setObjectName("checkButton")
        self.new_session_button.setIcon(QIcon(str(ICONS_DIR / "add.svg")))
        self.new_session_button.setToolTip("Создать сессию")
        self.new_session_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.new_session_button.clicked.connect(self._create_session)
        self.delete_session_button = QPushButton("Удалить", left)
        self.delete_session_button.setObjectName("dangerButton")
        self.delete_session_button.setIcon(QIcon(str(ICONS_DIR / "remove.svg")))
        self.delete_session_button.setToolTip("Удалить сессию")
        self.delete_session_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.delete_session_button.clicked.connect(self._delete_session)
        session_toolbar.addWidget(self.new_session_button, 1)
        session_toolbar.addWidget(self.delete_session_button, 1)
        left_layout.addLayout(session_toolbar)

        transfer_toolbar = QHBoxLayout()
        transfer_toolbar.setContentsMargins(0, 0, 0, 0)
        transfer_toolbar.setSpacing(6)
        self.import_sessions_button = QPushButton("Импорт", left)
        self.import_sessions_button.setObjectName("checkButton")
        self.import_sessions_button.setIcon(QIcon(str(ICONS_DIR / "down.svg")))
        self.import_sessions_button.setToolTip("Импортировать сессии из JSON")
        self.import_sessions_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.import_sessions_button.clicked.connect(self._import_sessions)
        self.export_sessions_button = QPushButton("Экспорт", left)
        self.export_sessions_button.setObjectName("checkButton")
        self.export_sessions_button.setIcon(QIcon(str(ICONS_DIR / "up.svg")))
        self.export_sessions_button.setToolTip("Экспортировать отмеченные сессии в JSON")
        self.export_sessions_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.export_sessions_button.clicked.connect(self._export_sessions)
        transfer_toolbar.addWidget(self.import_sessions_button, 1)
        transfer_toolbar.addWidget(self.export_sessions_button, 1)
        left_layout.addLayout(transfer_toolbar)

        self.create_session_exe_button = QPushButton("Создать EXE", left)
        self.create_session_exe_button.setObjectName("checkButton")
        self.create_session_exe_button.setIcon(QIcon(str(ICONS_DIR / "launch-checked.svg")))
        self.create_session_exe_button.setToolTip(
            "Создать автономный EXE для подсвеченной сессии"
        )
        self.create_session_exe_button.clicked.connect(self._create_session_exe)
        left_layout.addWidget(self.create_session_exe_button)

        self.scale_group = QGroupBox(left)
        self.scale_group.setObjectName("scale_group")
        self.scale_group.setTitle("")
        scale_group_layout = QVBoxLayout(self.scale_group)
        scale_group_layout.setContentsMargins(8, 8, 8, 8)
        scale_group_layout.setSpacing(4)
        scale_row = QHBoxLayout()
        scale_row.setSpacing(6)
        scale_label = QLabel("Масштаб:", self.scale_group)
        self.ui_scale_combo = QComboBox(self.scale_group)
        self.ui_scale_combo.setObjectName("ui_scale_combo")
        for delta in range(-50, 51, 10):
            self.ui_scale_combo.addItem(f"{100 + delta}%", delta)
        delta = normalize_ui_scale_delta_percent(
            self.core.settings.get("ui_scale_delta_percent", 0)
        )
        idx = self.ui_scale_combo.findData(delta)
        if idx >= 0:
            self.ui_scale_combo.setCurrentIndex(idx)
        self.ui_scale_combo.currentIndexChanged.connect(self.on_ui_scale_delta_changed)
        scale_row.addWidget(scale_label)
        scale_row.addWidget(self.ui_scale_combo, 1)
        scale_group_layout.addLayout(scale_row)
        left_layout.addWidget(self.scale_group)

        self.current_session_id: str | None = None

    # ------------------------------------------------------------------ #
    # Правая панель: настройка выбранной сессии                          #
    # ------------------------------------------------------------------ #

    def _build_session_detail_panel(self, parent: QSplitter) -> None:
        right = QWidget(parent)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)

        self.session_name_edit = QLineEdit(right)
        self.session_name_edit.setPlaceholderText("Имя сессии")
        self.session_name_edit.editingFinished.connect(self._rename_session)
        right_layout.addWidget(self.session_name_edit)

        self.session_app_list = QListWidget(right)
        self.session_app_list.setAlternatingRowColors(True)
        self.session_app_list.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        # У строк с полями ввода разная высота после смены масштаба.
        self.session_app_list.setUniformItemSizes(False)
        self.session_app_list.setSpacing(2)
        self.session_app_list.setMinimumSize(0, 0)
        self.session_app_list.setDragEnabled(True)
        self.session_app_list.setAcceptDrops(True)
        self.session_app_list.setDragDropMode(
            QAbstractItemView.DragDropMode.InternalMove
        )
        self.session_app_list.model().rowsMoved.connect(self._on_apps_reordered)
        right_layout.addWidget(self.session_app_list, 1)

        # Верхний ряд: Добавить | Удалить | Добавить паузу — на 3 части
        session_top_toolbar = QHBoxLayout()
        session_top_toolbar.setContentsMargins(0, 0, 0, 0)
        session_top_toolbar.setSpacing(6)
        self.add_session_app_button = QPushButton("Добавить", right)
        self.add_session_app_button.setObjectName("checkButton")
        self.add_session_app_button.setIcon(QIcon(str(ICONS_DIR / "add.svg")))
        self.add_session_app_button.setToolTip("Добавить программу или файл в сессию")
        self.add_session_app_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.add_session_app_button.clicked.connect(self._add_apps_to_session)
        self.remove_session_app_button = QPushButton("Удалить", right)
        self.remove_session_app_button.setObjectName("dangerButton")
        self.remove_session_app_button.setIcon(QIcon(str(ICONS_DIR / "remove.svg")))
        self.remove_session_app_button.setToolTip("Удалить шаг из сессии")
        self.remove_session_app_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.remove_session_app_button.clicked.connect(self._remove_session_apps)
        self.add_pause_button = QPushButton("Добавить паузу", right)
        self.add_pause_button.setObjectName("checkButton")
        self.add_pause_button.setIcon(QIcon(str(ICONS_DIR / "pause.svg")))
        self.add_pause_button.setToolTip(
            "Добавить шаг-паузу в выбранное место сессии"
        )
        self.add_pause_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.add_pause_button.clicked.connect(self._add_pause)
        session_top_toolbar.addWidget(self.add_session_app_button, 1)
        session_top_toolbar.addWidget(self.remove_session_app_button, 1)
        session_top_toolbar.addWidget(self.add_pause_button, 1)
        right_layout.addLayout(session_top_toolbar)

        # Нижний ряд перемещения — пополам
        session_move_toolbar = QHBoxLayout()
        session_move_toolbar.setContentsMargins(0, 0, 0, 0)
        session_move_toolbar.setSpacing(6)
        self.move_up_button = QPushButton("Вверх", right)
        self.move_up_button.setObjectName("checkButton")
        self.move_up_button.setIcon(QIcon(str(ICONS_DIR / "up.svg")))
        self.move_up_button.setToolTip("Переместить выбранное приложение вверх")
        self.move_up_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.move_up_button.clicked.connect(lambda: self._move_selected_app(-1))
        self.move_down_button = QPushButton("Вниз", right)
        self.move_down_button.setObjectName("checkButton")
        self.move_down_button.setIcon(QIcon(str(ICONS_DIR / "down.svg")))
        self.move_down_button.setToolTip("Переместить выбранное приложение вниз")
        self.move_down_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        self.move_down_button.clicked.connect(lambda: self._move_selected_app(1))
        session_move_toolbar.addWidget(self.move_up_button, 1)
        session_move_toolbar.addWidget(self.move_down_button, 1)
        right_layout.addLayout(session_move_toolbar)

        # Самый низ — один контейнер с кнопкой «Применить сессию», растянутой пропорционально по ширине
        apply_container = QFrame(right)
        apply_container.setObjectName("applyBlock")
        apply_container_layout = QHBoxLayout(apply_container)
        apply_container_layout.setContentsMargins(0, 4, 0, 0)
        apply_container_layout.setSpacing(0)
        self.apply_session_button = QPushButton("Применить сессию", apply_container)
        self.apply_session_button.setObjectName("sessionLaunch")
        self.apply_session_button.setIcon(QIcon(str(ICONS_DIR / "launch-checked.svg")))
        self.apply_session_button.setToolTip("Применить сессию")
        self.apply_session_button.setMinimumHeight(34)
        self.apply_session_button.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self.apply_session_button.clicked.connect(self._apply_session)
        apply_container_layout.addWidget(self.apply_session_button, 1)
        right_layout.addWidget(apply_container)

        self._action_buttons = [self.apply_session_button]
        self._all_buttons = [
            self.new_session_button,
            self.delete_session_button,
            self.import_sessions_button,
            self.export_sessions_button,
            self.create_session_exe_button,
            self.add_session_app_button,
            self.remove_session_app_button,
            self.move_up_button,
            self.move_down_button,
            self.apply_session_button,
            self.add_pause_button,
        ]

    # ------------------------------------------------------------------ #
    # Работа с сессиями                                                  #
    # ------------------------------------------------------------------ #

    def _refresh_session_list(self) -> None:
        self.session_list.blockSignals(True)
        self.session_list.clear()
        for session in self.core.sessions:
            item = QListWidgetItem(session.name)
            item.setData(Qt.ItemDataRole.UserRole, session.id)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if session.export_selected else Qt.CheckState.Unchecked
            )
            self.session_list.addItem(item)
        self.session_list.blockSignals(False)
        if self.current_session_id:
            self._select_session_item(self.current_session_id)
        elif self.session_list.count():
            self.session_list.setCurrentRow(0)

    def _select_session_item(self, session_id: str) -> None:
        for row in range(self.session_list.count()):
            if self.session_list.item(row).data(Qt.ItemDataRole.UserRole) == session_id:
                self.session_list.setCurrentRow(row)
                return

    def _on_session_export_toggled(self, item: QListWidgetItem) -> None:
        session = self.core.get_session(item.data(Qt.ItemDataRole.UserRole))
        if session is None:
            return
        selected = item.checkState() == Qt.CheckState.Checked
        if session.export_selected != selected:
            session.export_selected = selected
            self.core.update_session(session)

    def _on_session_selected(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            self.current_session_id = None
            self.session_name_edit.clear()
            self.session_app_list.clear()
            return
        session_id = current.data(Qt.ItemDataRole.UserRole)
        session = self.core.get_session(session_id)
        if session is None:
            return
        self.current_session_id = session.id
        self.session_name_edit.setText(session.name)
        self._load_session_apps(session)

    def _load_session_apps(self, session: Session) -> None:
        self.session_app_list.blockSignals(True)
        self.session_app_list.clear()
        for application in session.applications:
            item = QListWidgetItem()
            row = SessionAppRow(application, self.session_app_list)
            row.changed.connect(self._on_session_app_changed)
            item.setSizeHint(row.sizeHint())
            self.session_app_list.addItem(item)
            self.session_app_list.setItemWidget(item, row)
        self.session_app_list.blockSignals(False)
        self.refresh_session_app_row_heights()

    def refresh_session_app_row_heights(self, scale_factor: float | None = None) -> None:
        """Синхронизировать строки списка с высотой текста в полях ввода."""
        factor = self.get_ui_scale_factor() if scale_factor is None else scale_factor
        rows: list[tuple[QListWidgetItem, SessionAppRow]] = []
        for index in range(self.session_app_list.count()):
            item = self.session_app_list.item(index)
            row = self.session_app_list.itemWidget(item)
            if isinstance(row, SessionAppRow):
                # После смены масштаба строки пересоздаются из модели. Поэтому
                # их margins/spacing/min-width нужно масштабировать здесь, а не
                # полагаться только на ранее выполненный обход главного окна.
                apply_scale_to_widget(row, factor)
                rows.append((item, row))
        ensure_text_control_heights(self.session_app_list, factor)
        trailing_controls = [
            row.duration_combo if row._is_pause else row.action_combo
            for _item, row in rows
        ]
        if trailing_controls:
            trailing_width = max(
                scale_px(SESSION_ROW_TRAILING_CONTROL_MIN_WIDTH, factor),
                *(control.sizeHint().width() for control in trailing_controls),
            )
            for control in trailing_controls:
                control.setFixedWidth(trailing_width)
        for item, row in rows:
            if row.layout() is not None:
                row.layout().invalidate()
                row.layout().activate()
            row.updateGeometry()
            hint = row.sizeHint().expandedTo(row.minimumSizeHint())
            # QListWidget::item из QSS имеет собственный padding. Qt вычитает
            # его из прямоугольника, отдаваемого setItemWidget(), поэтому этот
            # padding должен входить в полный sizeHint элемента списка.
            item_vertical_padding = 2 * scale_px(
                LIST_ITEM_VERTICAL_PADDING,
                factor,
            )
            item.setSizeHint(
                QSize(hint.width(), hint.height() + item_vertical_padding)
            )
        self.session_app_list.doItemsLayout()
        self.session_app_list.viewport().update()

    def _collect_session_apps(self) -> list[ApplicationEntry]:
        applications: list[ApplicationEntry] = []
        for row in range(self.session_app_list.count()):
            item = self.session_app_list.item(row)
            row_widget = self.session_app_list.itemWidget(item)
            if isinstance(row_widget, SessionAppRow):
                applications.append(row_widget.build())
        return applications

    @Slot()
    def _on_session_app_changed(self) -> None:
        session = self._current_session()
        if session is None:
            return
        session.applications = self._collect_session_apps()
        self.core.update_session(session)

    @Slot()
    def _on_apps_reordered(self) -> None:
        session = self._current_session()
        if session is None:
            return
        session.applications = self._collect_session_apps()
        self.core.update_session(session)
        self._load_session_apps(session)

    def _move_selected_app(self, direction: int) -> None:
        session = self._current_session()
        if session is None:
            return
        indexes = self.session_app_list.selectedIndexes()
        if not indexes:
            self.statusBar().showMessage("Сначала выберите приложение", 5000)
            return
        row = indexes[0].row()
        target = row + direction
        if target < 0 or target >= len(session.applications):
            return
        applications = session.applications
        applications[row], applications[target] = applications[target], applications[row]
        self.core.update_session(session)
        self._load_session_apps(session)
        self.session_app_list.setCurrentRow(target)
        self.statusBar().showMessage("Порядок приложений изменён", 5000)

    def _current_session(self) -> Session | None:
        if not self.current_session_id:
            return None
        return self.core.get_session(self.current_session_id)

    def _rename_session(self) -> None:
        session = self._current_session()
        if session is None:
            return
        new_name = self.session_name_edit.text().strip() or "Новая сессия"
        if new_name == session.name:
            return
        session.name = new_name
        self.core.update_session(session)
        self._refresh_session_list()

    def _create_session(self) -> None:
        session = self.core.add_session("Новая сессия")
        self.current_session_id = session.id
        self._refresh_session_list()
        self.session_name_edit.setFocus()
        self.session_name_edit.selectAll()
        self.statusBar().showMessage("Создана новая сессия", 5000)

    def _delete_session(self) -> None:
        session = self._current_session()
        if session is None:
            return
        answer = QMessageBox.question(
            self,
            "Удаление сессии",
            f"Удалить сессию «{session.name}»?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.core.remove_session(session.id)
        self.current_session_id = None
        self._refresh_session_list()
        self.statusBar().showMessage("Сессия удалена", 5000)

    def _import_sessions(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Импорт сессий",
            "",
            "Сессии AppCircuit (*.json);;Все файлы (*)",
        )
        if not selected:
            return
        try:
            imported = self.core.import_sessions(Path(selected))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Импорт сессий", str(exc))
            return
        self.current_session_id = imported[0].id
        self._refresh_session_list()
        self.statusBar().showMessage(f"Импортировано сессий: {len(imported)}", 5000)

    def _export_sessions(self) -> None:
        if not any(session.export_selected for session in self.core.sessions):
            self.statusBar().showMessage("Отметьте галочками сессии для экспорта", 5000)
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт сессий",
            "AppCircuit_sessions.json",
            "Сессии AppCircuit (*.json)",
        )
        if not selected:
            return
        destination = Path(selected)
        if destination.suffix.casefold() != ".json":
            destination = Path(f"{destination}.json")
        try:
            count = self.core.export_sessions(destination)
        except OSError as exc:
            QMessageBox.warning(self, "Экспорт сессий", str(exc))
            return
        self.statusBar().showMessage(f"Экспортировано сессий: {count}", 5000)

    def _create_session_exe(self) -> None:
        session = self._current_session()
        if session is None:
            self.statusBar().showMessage("Сначала выберите сессию в списке", 5000)
            return
        if not any(step.enabled for step in session.applications):
            self.statusBar().showMessage("В выбранной сессии нет включённых шагов", 5000)
            return
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "Создать EXE выбранной сессии",
            suggested_executable_name(session),
            "Исполняемый файл (*.exe)",
        )
        if not selected:
            return
        try:
            destination = create_session_executable(session, Path(selected))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Создание EXE", str(exc))
            return
        self.statusBar().showMessage(f"Создан файл: {destination}", 10000)

    def _add_apps_to_session(self) -> None:
        session = self._current_session()
        if session is None:
            self.statusBar().showMessage("Сначала создайте или выберите сессию", 5000)
            return
        known_paths = {str(Path(app.path)).casefold() for app in session.applications}
        chosen_paths: list[str] = []

        def collect_paths(paths: list[str]) -> None:
            chosen_paths.extend(paths)
            for path in paths:
                normalized = str(Path(path)).casefold()
                if normalized not in known_paths:
                    session.applications.append(ApplicationEntry.from_path(path))
                    known_paths.add(normalized)

        dialog = PersistentFileDialog(self, self.core.recent_application_directories)
        dialog.filesChosen.connect(collect_paths)
        dialog.exec()
        self.core.remember_application_directories(chosen_paths)
        if not chosen_paths:
            return
        self.core.update_session(session)
        self._load_session_apps(session)
        self.statusBar().showMessage("Программы и файлы добавлены в сессию", 5000)

    def _remove_session_apps(self) -> None:
        session = self._current_session()
        if session is None:
            return
        selected_rows = {index.row() for index in self.session_app_list.selectedIndexes()}
        if not selected_rows:
            self.statusBar().showMessage("Сначала выберите приложения", 5000)
            return
        session.applications = [
            app
            for row, app in enumerate(session.applications)
            if row not in selected_rows
        ]
        self.core.update_session(session)
        self._load_session_apps(session)
        self.statusBar().showMessage("Приложения удалены из сессии", 5000)

    def _apply_session(self) -> None:
        if self._busy:
            return
        session = self._current_session()
        if session is None:
            self.statusBar().showMessage("Сначала выберите сессию", 5000)
            return
        if not session.applications:
            self.statusBar().showMessage("В сессии нет приложений", 5000)
            return
        self._run_worker(
            SessionActionWorker(self.core, session),
            on_finished=self._on_session_action_finished,
        )

    def _add_pause(self) -> None:
        session = self._current_session()
        if session is None:
            self.statusBar().showMessage("Сначала создайте или выберите сессию", 5000)
            return
        pause = ApplicationEntry(
            id=uuid4().hex,
            name="Пауза",
            path="",
            process_name="",
            is_pause=True,
            duration=1,
        )
        selected = self.session_app_list.selectedIndexes()
        insert_at = selected[0].row() + 1 if selected else len(session.applications)
        session.applications.insert(insert_at, pause)
        self.core.update_session(session)
        self._load_session_apps(session)
        self.session_app_list.setCurrentRow(insert_at)
        self.statusBar().showMessage("Добавлена пауза", 5000)

    # ------------------------------------------------------------------ #
    # Масштабирование интерфейса                                       #
    # ------------------------------------------------------------------ #

    def get_ui_scale_factor(self) -> float:
        return float(getattr(self, "_ui_scale_factor", 1.0))

    def apply_ui_scale(self, allow_window_resize: bool, reason: str) -> None:
        previous_scale_factor = self.get_ui_scale_factor()
        delta = normalize_ui_scale_delta_percent(
            self.core.settings.get("ui_scale_delta_percent", 0)
        )
        state = resolve_scale_for_window(self, delta)
        self._ui_scale_state = state  # type: ignore[attr-defined]
        self.core.settings["ui_scale_mode"] = "auto"
        self.core.settings["ui_scale_delta_percent"] = int(state.delta_percent)
        self.core.settings["ui_scale_percent"] = int(state.final_percent)
        self.core.save()
        apply_ui_scale_to_app_and_window(
            self,
            state,
            allow_window_resize,
            previous_scale_factor,
        )
        self._ui_scale_factor = float(state.scale_factor)
        # обновить комбо без сигнала
        if hasattr(self, "ui_scale_combo"):
            self.ui_scale_combo.blockSignals(True)
            idx = self.ui_scale_combo.findData(int(state.delta_percent))
            if idx >= 0:
                self.ui_scale_combo.setCurrentIndex(idx)
            self.ui_scale_combo.blockSignals(False)
        # обновить высоту элементов списка после масштабирования
        if getattr(self, "current_session_id", None) is not None:
            session = self.core.get_session(self.current_session_id)  # type: ignore[attr-defined]
            if session is not None:
                self._load_session_apps(session)

    def install_ui_scale_screen_hooks(self) -> None:
        install_ui_scale_hooks(self)

    @Slot(object)
    def on_ui_scale_window_screen_changed(self, screen) -> None:  # type: ignore[no-untyped-def]
        self._ui_scale_screen = screen
        self.install_ui_scale_screen_hooks()
        self.apply_ui_scale(allow_window_resize=False, reason="screen-changed")

    @Slot()
    def on_ui_scale_screen_metrics_changed(self) -> None:
        self.apply_ui_scale(allow_window_resize=False, reason="screen-metrics")

    @Slot()
    def on_ui_scale_topology_changed(self) -> None:
        self.apply_ui_scale(allow_window_resize=False, reason="screen-topology")

    @Slot(int)
    def on_ui_scale_delta_changed(self, _index: int) -> None:
        delta = normalize_ui_scale_delta_percent(self.ui_scale_combo.currentData())
        self.core.settings["ui_scale_delta_percent"] = int(delta)
        self.core.save()
        self.apply_ui_scale(allow_window_resize=True, reason="manual-delta")

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if not getattr(self, "_ui_scale_initialized", False):
            self._ui_scale_initialized = True
            from PySide6.QtWidgets import QApplication

            QApplication.processEvents()
            self.install_ui_scale_screen_hooks()
            self.apply_ui_scale(allow_window_resize=False, reason="startup")
            if self._fit_width_on_first_show and not self.isMaximized():
                screen = self.screen()
                content_width = self.sizeHint().width()
                if screen is not None:
                    content_width = min(content_width, screen.availableGeometry().width())
                self.resize(max(self.width(), content_width), self.height())

    @Slot(object)
    def _on_session_action_finished(self, report: ActionReport) -> None:
        self._finish_worker()
        self.statusBar().showMessage(report.summary, 12000)
        self.statusBar().setToolTip("\n".join(report.failed))
        if report.failed:
            QMessageBox.warning(
                self,
                "Операция завершена с ошибками",
                report.summary + "\n\n" + "\n".join(report.failed),
            )

    # ------------------------------------------------------------------ #
    # Общий механизм фоновых операций                                    #
    # ------------------------------------------------------------------ #

    def _run_worker(self, worker: QObject, on_finished) -> None:
        self._busy = True
        self._set_actions_enabled(False)
        self.statusBar().showMessage("Операция выполняется…")
        thread = QThread(self)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._clear_worker)
        self._thread = thread
        self._worker = worker
        thread.start()

    def _finish_worker(self) -> None:
        self._busy = False
        self._set_actions_enabled(True)

    @Slot()
    def _clear_worker(self) -> None:
        self._thread = None
        self._worker = None

    def _set_actions_enabled(self, enabled: bool) -> None:
        for button in self._all_buttons:
            button.setEnabled(enabled)
        self.session_name_edit.setEnabled(enabled)
        self.session_app_list.setEnabled(enabled)
        self.session_list.setEnabled(enabled)

    # ------------------------------------------------------------------ #
    # Состояние окна                                                     #
    # ------------------------------------------------------------------ #

    def _restore_window_state(self) -> None:
        settings = self.core.settings
        self._fit_width_on_first_show = (
            settings.get("window_width") is None
            and not settings.get("window_geometry")
        )
        restored = False
        encoded_geometry = settings.get("window_geometry")
        if encoded_geometry:
            geometry = QByteArray.fromBase64(encoded_geometry.encode("ascii"))
            restored = self.restoreGeometry(geometry)
        if not restored:
            saved_width = settings.get("window_width")
            self.resize(
                self.sizeHint().width() if saved_width is None else int(saved_width),
                int(settings["window_height"]),
            )
            if (
                settings.get("window_pos_x") is not None
                and settings.get("window_pos_y") is not None
            ):
                self.move(int(settings["window_pos_x"]), int(settings["window_pos_y"]))
        if settings.get("maximized"):
            self.showMaximized()

    def closeEvent(self, event) -> None:
        if self._busy:
            event.ignore()
            self.statusBar().showMessage("Дождитесь завершения операции", 5000)
            return
        geometry = self.normalGeometry()
        self.core.settings.update(
            {
                "window_pos_x": geometry.x(),
                "window_pos_y": geometry.y(),
                "window_width": geometry.width(),
                "window_height": geometry.height(),
                "maximized": self.isMaximized(),
                "window_geometry": bytes(self.saveGeometry().toBase64()).decode("ascii"),
            }
        )
        self.core.save()
        event.accept()
