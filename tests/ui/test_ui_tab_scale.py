import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QComboBox, QGroupBox

from app.core.application import ApplicationCore
from app.core.settings_store import SettingsStore
from app.ui.main_window import MainWindow


def test_scale_group_and_combo_exist(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    core = ApplicationCore()
    core.store = SettingsStore(tmp_path / "settings.json")
    core.settings = core.store.load()
    window = MainWindow(core)
    window.show()
    app.processEvents()

    group = window.findChild(QGroupBox, "scale_group")
    assert group is not None
    # надпись группы убрана по просьбе пользователя — заголовок пустой, контрол определяется по objectName
    assert group.title() == ""

    combo = window.findChild(QComboBox, "ui_scale_combo")
    if combo is None:
        combo = window.ui_scale_combo
    assert combo.count() == 11  # -50..50 step 10 => 11 values
    assert combo.itemText(0) == "50%"
    assert combo.itemText(5) == "100%"
    assert combo.itemText(10) == "150%"
    assert combo.itemData(0) == -50
    assert combo.itemData(5) == 0
    assert combo.itemData(10) == 50

    window.close()
    app.processEvents()
