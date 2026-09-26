import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import QApplication

from app.core.app_config import ICONS_DIR
from app.ui.styles import (
    _BASE_APPLICATION_FONT_ATTRIBUTE,
    apply_global_styles,
    build_global_stylesheet,
)


def test_stylesheet_scales_with_factor() -> None:
    s1 = build_global_stylesheet(scale_factor=1.0)
    s15 = build_global_stylesheet(scale_factor=1.5)
    assert s1 != s15
    # border radius 8 at 1.0 -> 12 at 1.5
    assert "border-radius: 8px" in s1
    assert "border-radius: 12px" in s15
    # min-height 38 at 1.0 -> 57 at 1.5 (38*1.5=57)
    assert "min-height: 38px" in s1
    assert "min-height: 57px" in s15


def test_stylesheet_contains_scaled_qss_elements() -> None:
    sheet = build_global_stylesheet(scale_factor=1.0)
    assert "QCheckBox::indicator" in sheet
    assert "QComboBox" in sheet
    assert "QGroupBox" in sheet
    assert "QSplitter::handle" in sheet


def test_combo_arrow_is_visible_and_scales_with_interface() -> None:
    app = QApplication.instance() or QApplication([])
    assert app is not None
    arrow = ICONS_DIR / "chevron-down.svg"
    assert not QPixmap(str(arrow)).isNull()

    sheet = build_global_stylesheet(scale_factor=1.0)
    enlarged_sheet = build_global_stylesheet(scale_factor=1.5)
    assert 'QComboBox::down-arrow {' in sheet
    assert f'image: url("{arrow.as_posix()}")' in sheet
    assert "width: 14px;\n            height: 14px" in sheet
    assert "width: 21px;\n            height: 21px" in enlarged_sheet


def test_reapplying_scale_does_not_compound_application_font() -> None:
    app = QApplication.instance() or QApplication([])
    original_font = QFont(app.font())
    original_stylesheet = app.styleSheet()
    if hasattr(app, _BASE_APPLICATION_FONT_ATTRIBUTE):
        delattr(app, _BASE_APPLICATION_FONT_ATTRIBUTE)
    app.setFont(QFont("Segoe UI", 10))
    try:
        apply_global_styles(app, scale_factor=1.2)
        first_size = app.font().pointSizeF()
        apply_global_styles(app, scale_factor=1.2)
        assert app.font().pointSizeF() == pytest.approx(first_size)
    finally:
        app.setFont(original_font)
        app.setStyleSheet(original_stylesheet)
        if hasattr(app, _BASE_APPLICATION_FONT_ATTRIBUTE):
            delattr(app, _BASE_APPLICATION_FONT_ATTRIBUTE)
