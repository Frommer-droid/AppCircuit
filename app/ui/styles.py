from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app.core.app_config import ICONS_DIR
from app.services.ui_scale_service import scale_point_size, scale_px

_BASE_APPLICATION_FONT_ATTRIBUTE = "_app_circuit_base_font"
LIST_ITEM_VERTICAL_PADDING = 6
LIST_ITEM_HORIZONTAL_PADDING = 8


def build_global_stylesheet(
    scale_factor: float = 1.0,
    base_font_point_size: float = 10.0,
) -> str:
    def s_px(value: int) -> int:
        return scale_px(int(value), scale_factor)

    def s_pt(value: float) -> float:
        return scale_point_size(float(value), scale_factor)

    # helper to format point size without trailing zeros
    def fmt_pt(value: float) -> str:
        text = f"{value:.2f}"
        text = text.rstrip("0").rstrip(".")
        return text

    _ = fmt_pt(s_pt(base_font_point_size))  # keep helper reachable for future use
    combo_arrow = (ICONS_DIR / "chevron-down.svg").as_posix()
    return f"""
        QWidget {{
            background: #171b22;
            color: #eef2f6;
        }}
        QMainWindow {{ background: #171b22; }}
        QListWidget {{
            background: #202630;
            alternate-background-color: #1b212a;
            border: {s_px(1)}px solid #394452;
            border-radius: {s_px(8)}px;
            selection-background-color: #315d82;
            outline: none;
        }}
        QListWidget::item {{
            min-height: {s_px(38)}px;
            padding: {s_px(LIST_ITEM_VERTICAL_PADDING)}px {s_px(LIST_ITEM_HORIZONTAL_PADDING)}px;
            border-radius: {s_px(4)}px;
        }}
        QListWidget::item:selected {{
            background: #315d82;
        }}
        QFrame#controlBlock {{
            background: #202630;
            border: {s_px(1)}px solid #394452;
            border-radius: {s_px(8)}px;
        }}
        QFrame#toolbarSeparator {{
            background: #45515f;
            border: none;
        }}
        QPushButton {{
            background: #3779b7;
            border: {s_px(1)}px solid #4589c8;
            border-radius: {s_px(7)}px;
            padding: {s_px(8)}px {s_px(14)}px;
        }}
        QPushButton:hover {{ background: #4389c9; }}
        QPushButton:pressed {{ background: #2d679d; }}
        QPushButton:disabled {{ background: #303843; color: #798492; border-color: #3a434f; }}
        QPushButton#fileDialogAcceptButton {{
            background: #3779b7;
            border: {s_px(1)}px solid #5597d4;
            border-radius: {s_px(6)}px;
            padding: {s_px(7)}px {s_px(18)}px;
            font-weight: 600;
        }}
        QPushButton#fileDialogAcceptButton:hover {{
            background: #4389c9;
            border-color: #6aace7;
        }}
        QPushButton#fileDialogAcceptButton:pressed {{
            background: #2d679d;
            border-color: #397db9;
        }}
        QPushButton#fileDialogAcceptButton:disabled {{
            background: #303843;
            color: #798492;
            border-color: #3a434f;
        }}
        QPushButton#stopButton {{
            background: #b33645;
            border-color: #db5363;
        }}
        QPushButton#stopButton:hover {{
            background: #ca4050;
            border-color: #ee6574;
        }}
        QPushButton#stopButton:pressed {{
            background: #8f2936;
            border-color: #b83b49;
        }}
        QPushButton#stopButton:disabled {{
            background: #4f3037;
            border-color: #654049;
        }}
        QPushButton#dangerButton {{ background: #8e4450; border-color: #ad5664; }}
        QPushButton#dangerButton:hover {{ background: #a64e5c; }}
        QPushButton#checkButton {{
            background: #283746;
            border-color: #4b6174;
        }}
        QPushButton#checkButton:hover {{
            background: #344b60;
            border-color: #64829b;
        }}
        QPushButton#checkButton:pressed {{
            background: #22313e;
        }}
        QPushButton#sessionLaunch {{
            background: #2f7d4f;
            border-color: #3fa068;
        }}
        QPushButton#sessionLaunch:hover {{
            background: #37935d;
            border-color: #4fbf7e;
        }}
        QPushButton#sessionLaunch:pressed {{
            background: #266742;
            border-color: #338754;
        }}
        QTabWidget::pane {{
            background: #171b22;
            border: {s_px(1)}px solid #394452;
            border-radius: {s_px(8)}px;
        }}
        QTabBar::tab {{
            background: #202630;
            color: #c7d0db;
            padding: {s_px(7)}px {s_px(18)}px;
            border: {s_px(1)}px solid #394452;
            border-bottom: none;
            border-top-left-radius: {s_px(7)}px;
            border-top-right-radius: {s_px(7)}px;
            margin-right: {s_px(3)}px;
        }}
        QTabBar::tab:selected {{
            background: #2b3a49;
            color: #ffffff;
        }}
        QTabBar::tab:hover:!selected {{
            background: #28353f;
        }}
        QLineEdit {{
            background: #202630;
            border: {s_px(1)}px solid #45515f;
            border-radius: {s_px(7)}px;
            padding: {s_px(10)}px {s_px(12)}px;
            color: #eef2f6;
            selection-background-color: #315d82;
        }}
        QLineEdit:focus {{
            border-color: #4f86c6;
        }}
        QCheckBox {{
            color: #eef2f6;
            spacing: {s_px(6)}px;
        }}
        QCheckBox::indicator {{
            width: {s_px(16)}px;
            height: {s_px(16)}px;
            border: {s_px(1)}px solid #566576;
            border-radius: {s_px(4)}px;
            background: #202630;
        }}
        QCheckBox::indicator:checked {{
            background: #3779b7;
            border-color: #4f86c6;
        }}
        QComboBox {{
            background: #202630;
            border: {s_px(1)}px solid #45515f;
            border-radius: {s_px(7)}px;
            padding: {s_px(4)}px {s_px(8)}px;
            color: #eef2f6;
        }}
        QComboBox:hover {{ border-color: #5a6b7d; }}
        QComboBox:focus {{ border-color: #4f86c6; }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            width: {s_px(26)}px;
            border: none;
            border-left: {s_px(1)}px solid #45515f;
            border-top-right-radius: {s_px(7)}px;
            border-bottom-right-radius: {s_px(7)}px;
        }}
        QComboBox::drop-down:hover {{ background: #2b3847; }}
        QComboBox::down-arrow {{
            image: url("{combo_arrow}");
            width: {s_px(14)}px;
            height: {s_px(14)}px;
        }}
        QComboBox QAbstractItemView {{
            background: #202630;
            border: {s_px(1)}px solid #45515f;
            border-radius: {s_px(7)}px;
            selection-background-color: #315d82;
        }}
        QGroupBox {{
            border: {s_px(1)}px solid #394452;
            border-radius: {s_px(8)}px;
            margin-top: {s_px(8)}px;
            padding-top: {s_px(10)}px;
            font-weight: 600;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            subcontrol-position: top left;
            padding: 0 {s_px(6)}px;
            color: #c7d0db;
        }}
        QSplitter {{
            background: transparent;
            border: none;
        }}
        QSplitter::handle {{
            background: #2b333d;
            border-radius: {s_px(3)}px;
        }}
        QSplitter::handle:horizontal {{
            width: {s_px(3)}px;
        }}
        QSplitter::handle:vertical {{
            height: {s_px(3)}px;
        }}
        QStatusBar {{ background: #11151a; color: #aeb8c5; }}
        QToolTip {{ background: #242c37; color: #ffffff; border: {s_px(1)}px solid #566576; }}
        """


def apply_global_styles(
    app: QApplication,
    scale_factor: float = 1.0,
    base_font_point_size: float | None = None,
) -> None:
    # Всегда рассчитываем от исходного системного шрифта. Если брать текущий
    # шрифт приложения, повторный вызов (в том числе после перезапуска) умножает
    # уже применённый масштаб ещё раз.
    base_font = getattr(app, _BASE_APPLICATION_FONT_ATTRIBUTE, None)
    if not isinstance(base_font, QFont):
        base_font = QFont(app.font())
        setattr(app, _BASE_APPLICATION_FONT_ATTRIBUTE, QFont(base_font))
    else:
        base_font = QFont(base_font)

    if base_font_point_size is not None:
        base_font.setPointSizeF(float(base_font_point_size))

    try:
        point_size = float(base_font.pointSizeF())
    except (TypeError, ValueError):
        point_size = 10.0
    if point_size <= 0:
        point_size = 10.0
        base_font.setPointSizeF(point_size)

    font = QFont(base_font)
    font.setFamilies(["Aptos", "Segoe UI", "Calibri"])
    font.setPointSizeF(scale_point_size(point_size, scale_factor))
    app.setFont(font)
    app.setStyleSheet(build_global_stylesheet(scale_factor, point_size))
