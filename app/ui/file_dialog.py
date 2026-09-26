from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    QAbstractItemModel,
    QIdentityProxyModel,
    QModelIndex,
    QPersistentModelIndex,
    QStandardPaths,
    QStorageInfo,
    Qt,
    QUrl,
    Signal,
)
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialogButtonBox,
    QFileDialog,
    QFileSystemModel,
    QSizePolicy,
    QTreeView,
    QWidget,
)


class CreationDateProxyModel(QIdentityProxyModel):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.creation_date_column = 4
        self._source_anchors: dict[int, QPersistentModelIndex] = {}

    def setSourceModel(self, source_model: QAbstractItemModel | None) -> None:
        self._source_anchors.clear()
        super().setSourceModel(source_model)
        if source_model is not None:
            self.creation_date_column = source_model.columnCount()

    def columnCount(self, parent: QModelIndex | None = None) -> int:
        parent = QModelIndex() if parent is None else parent
        return super().columnCount(parent) + 1

    def rowCount(self, parent: QModelIndex | None = None) -> int:
        parent = QModelIndex() if parent is None else parent
        if parent.isValid() and parent.column() == self.creation_date_column:
            return 0
        return super().rowCount(parent)

    def index(
        self,
        row: int,
        column: int,
        parent: QModelIndex | None = None,
    ) -> QModelIndex:
        parent = QModelIndex() if parent is None else parent
        if column != self.creation_date_column:
            return super().index(row, column, parent)
        source_model = self.sourceModel()
        if source_model is None:
            return QModelIndex()
        source_index = source_model.index(row, 0, self.mapToSource(parent))
        if not source_index.isValid():
            return QModelIndex()
        anchor_id = source_index.internalId()
        self._source_anchors[anchor_id] = QPersistentModelIndex(source_index)
        return self.createIndex(row, column, anchor_id)

    def mapToSource(self, proxy_index: QModelIndex) -> QModelIndex:
        if (
            proxy_index.isValid()
            and proxy_index.column() == self.creation_date_column
        ):
            source_index = self._source_anchors.get(proxy_index.internalId())
            if source_index is not None and source_index.isValid():
                return QModelIndex(source_index)
            return QModelIndex()
        return super().mapToSource(proxy_index)

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if index.column() != self.creation_date_column:
            return super().data(index, role)
        if role not in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.ToolTipRole,
        ):
            return None
        source_model = self.sourceModel()
        source_index = self.mapToSource(index)
        if not isinstance(source_model, QFileSystemModel) or not source_index.isValid():
            return None
        created_at = source_model.fileInfo(source_index).birthTime()
        return created_at.toString("dd.MM.yyyy HH:mm") if created_at.isValid() else "—"

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if (
            section == self.creation_date_column
            and orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            return "Дата создания"
        return super().headerData(section, orientation, role)


class PersistentFileDialog(QFileDialog):
    filesChosen = Signal(list)

    def __init__(
        self,
        parent: QWidget | None = None,
        recent_directories: list[str] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        self.setWindowTitle("Выберите программы и файлы")
        self.setFileMode(QFileDialog.FileMode.ExistingFiles)
        self.setAcceptMode(QFileDialog.AcceptMode.AcceptOpen)
        self.setLabelText(QFileDialog.DialogLabel.Accept, "Добавить")
        self.setNameFilters(["Все файлы (*)", "Приложения Windows (*.exe)"])
        self._details_proxy = CreationDateProxyModel(self)
        self.setProxyModel(self._details_proxy)
        self.setSidebarUrls(self._build_sidebar_urls(recent_directories or []))

        tree_view = self.findChild(QTreeView, "treeView")
        if tree_view is not None:
            tree_view.setColumnWidth(self._details_proxy.creation_date_column, 160)
        button_box = self.findChild(QDialogButtonBox)
        if button_box is not None:
            accept_button = button_box.button(QDialogButtonBox.StandardButton.Open)
            if accept_button is not None:
                accept_button.setObjectName("fileDialogAcceptButton")
                accept_button.setMinimumSize(112, 36)
                accept_button.setSizePolicy(
                    QSizePolicy.Policy.Minimum,
                    QSizePolicy.Policy.Fixed,
                )
            cancel_button = button_box.button(QDialogButtonBox.StandardButton.Cancel)
            if cancel_button is not None:
                cancel_button.hide()

    def _build_sidebar_urls(self, recent_directories: list[str]) -> list[QUrl]:
        default_urls = self.sidebarUrls()
        computer_urls = [
            url
            for url in default_urls
            if url.scheme() == "file" and not url.toLocalFile()
        ]
        desktop_path = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.DesktopLocation
        )
        home_path = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.HomeLocation
        )
        drive_paths = [
            volume.rootPath()
            for volume in QStorageInfo.mountedVolumes()
            if volume.isValid() and volume.isReady()
        ]

        urls = [
            QUrl.fromLocalFile(desktop_path),
            *computer_urls,
            *(QUrl.fromLocalFile(path) for path in drive_paths),
            QUrl.fromLocalFile(home_path),
            *(QUrl.fromLocalFile(path) for path in recent_directories),
        ]
        unique_urls: list[QUrl] = []
        known_urls: set[str] = set()
        for url in urls:
            local_path = url.toLocalFile()
            if local_path and not Path(local_path).is_dir():
                continue
            key = (
                str(Path(local_path).resolve()).casefold()
                if local_path
                else url.toString().casefold()
            )
            if key in known_urls:
                continue
            unique_urls.append(url)
            known_urls.add(key)
        return unique_urls

    def accept(self) -> None:
        paths = self.selectedFiles()
        if paths:
            self.filesChosen.emit(paths)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)
