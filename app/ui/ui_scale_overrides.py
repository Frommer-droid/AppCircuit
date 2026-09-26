from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QComboBox, QLayout, QLineEdit, QStyle, QWidget

from app.services.ui_scale_service import scale_px

_BASE_MARGINS = "_base_margins"
_BASE_SPACING = "_base_spacing"
_BASE_CONTENTS_MARGINS = "_base_contents_margins"
_BASE_MIN_SIZE = "_base_min_size"
_BASE_MAX_SIZE = "_base_max_size"
_BASE_FIXED_SIZE = "_base_fixed_size"
_BASE_ICON_SIZE = "_base_icon_size"
_BASE_TEXT_CONTROL_MIN_HEIGHT = "_base_text_control_min_height"


def _scale_value(value: int, factor: float) -> int:
    return max(0, int(round(value * factor)))


def _store_base_margins(layout: QLayout) -> tuple[int, int, int, int]:
    stored = layout.property(_BASE_MARGINS)
    if isinstance(stored, (list, tuple)) and len(stored) == 4:
        return tuple(int(x) for x in stored)  # type: ignore[return-value]
    m = layout.contentsMargins()
    base = (m.left(), m.top(), m.right(), m.bottom())
    layout.setProperty(_BASE_MARGINS, list(base))
    return base


def _store_base_spacing(layout: QLayout) -> int:
    stored = layout.property(_BASE_SPACING)
    if stored is not None:
        try:
            return int(stored)
        except (TypeError, ValueError):
            pass
    base = int(layout.spacing())
    layout.setProperty(_BASE_SPACING, base)
    return base


def _store_base_widget_margins(widget: QWidget) -> tuple[int, int, int, int]:
    stored = widget.property(_BASE_CONTENTS_MARGINS)
    if isinstance(stored, (list, tuple)) and len(stored) == 4:
        return tuple(int(x) for x in stored)  # type: ignore[return-value]
    m = widget.contentsMargins()
    base = (m.left(), m.top(), m.right(), m.bottom())
    widget.setProperty(_BASE_CONTENTS_MARGINS, list(base))
    return base


def _store_base_min_size(widget: QWidget) -> QSize:
    stored = widget.property(_BASE_MIN_SIZE)
    if isinstance(stored, QSize):
        return stored
    base = widget.minimumSize()
    widget.setProperty(_BASE_MIN_SIZE, QSize(base))
    return base


def _store_base_max_size(widget: QWidget) -> QSize:
    stored = widget.property(_BASE_MAX_SIZE)
    if isinstance(stored, QSize):
        return stored
    base = widget.maximumSize()
    widget.setProperty(_BASE_MAX_SIZE, QSize(base))
    return base


def _store_base_fixed_size(widget: QWidget) -> tuple[int, int] | None:
    stored = widget.property(_BASE_FIXED_SIZE)
    if isinstance(stored, (list, tuple)) and len(stored) == 2:
        return (int(stored[0]), int(stored[1]))
    if stored is None:
        # check if already stored as None, return None
        # but we need to detect first time
        if widget.property(_BASE_FIXED_SIZE) is not None:
            return None
    min_s = widget.minimumSize()
    max_s = widget.maximumSize()
    if min_s.isValid() and max_s.isValid() and min_s == max_s and not min_s.isEmpty():
        base = (min_s.width(), min_s.height())
        widget.setProperty(_BASE_FIXED_SIZE, list(base))
        return base
    widget.setProperty(_BASE_FIXED_SIZE, None)
    return None


def _store_base_icon_size(widget: QWidget) -> QSize | None:
    stored = widget.property(_BASE_ICON_SIZE)
    if isinstance(stored, QSize):
        return stored
    if stored is None and widget.property(_BASE_ICON_SIZE) is not None:
        return None
    try:
        base = widget.iconSize()  # type: ignore[attr-defined]
    except AttributeError:
        widget.setProperty(_BASE_ICON_SIZE, None)
        return None
    if base.isValid() and not base.isEmpty():
        widget.setProperty(_BASE_ICON_SIZE, QSize(base))
        return base
    widget.setProperty(_BASE_ICON_SIZE, None)
    return None


def apply_scale_to_layout(
    layout: QLayout,
    factor: float,
    visited_widgets: set[int] | None = None,
) -> None:
    if visited_widgets is None:
        visited_widgets = set()
    base_margins = _store_base_margins(layout)
    left, top, right, bottom = base_margins
    layout.setContentsMargins(
        _scale_value(left, factor),
        _scale_value(top, factor),
        _scale_value(right, factor),
        _scale_value(bottom, factor),
    )
    base_spacing = _store_base_spacing(layout)
    if base_spacing >= 0:
        layout.setSpacing(_scale_value(base_spacing, factor))
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is None:
            continue
        child_layout = item.layout()
        if child_layout is not None:
            apply_scale_to_layout(child_layout, factor, visited_widgets)
            continue
        widget = item.widget()
        if isinstance(widget, QWidget):
            apply_scale_to_widget(widget, factor, visited_widgets)


def apply_scale_to_widget(
    widget: QWidget,
    factor: float,
    visited_widgets: set[int] | None = None,
) -> None:
    # В PySide после удаления старых test widgets может кратковременно
    # встретиться wrapper QLayoutItem вместо QWidget. Не вызываем на нём
    # QObject API и не обходим один и тот же widget повторно.
    if not isinstance(widget, QWidget) or not callable(getattr(widget, "property", None)):
        return
    if visited_widgets is None:
        visited_widgets = set()
    widget_id = id(widget)
    if widget_id in visited_widgets:
        return
    visited_widgets.add(widget_id)

    base_margins = _store_base_widget_margins(widget)
    left, top, right, bottom = base_margins
    if any(v != 0 for v in base_margins):
        widget.setContentsMargins(
            _scale_value(left, factor),
            _scale_value(top, factor),
            _scale_value(right, factor),
            _scale_value(bottom, factor),
        )
    base_fixed = _store_base_fixed_size(widget)
    if base_fixed is not None:
        w, h = base_fixed
        widget.setFixedSize(_scale_value(w, factor), _scale_value(h, factor))
    else:
        base_min = _store_base_min_size(widget)
        if base_min.isValid() and not base_min.isEmpty():
            widget.setMinimumSize(
                _scale_value(base_min.width(), factor),
                _scale_value(base_min.height(), factor),
            )
        base_max = _store_base_max_size(widget)
        if base_max.isValid() and base_max.width() < 16777215 and base_max.height() < 16777215:
            if not base_max.isEmpty():
                widget.setMaximumSize(
                    _scale_value(base_max.width(), factor),
                    _scale_value(base_max.height(), factor),
                )
    base_icon = _store_base_icon_size(widget)
    if base_icon is not None:
        try:
            widget.setIconSize(QSize(_scale_value(base_icon.width(), factor), _scale_value(base_icon.height(), factor)))  # type: ignore[attr-defined]
        except AttributeError:
            pass
    # recurse layout
    if widget.layout() is not None:
        apply_scale_to_layout(widget.layout(), factor, visited_widgets)
    # recurse direct children not in layout
    for child in widget.findChildren(
        QWidget,
        options=Qt.FindChildOption.FindDirectChildrenOnly,
    ):
        apply_scale_to_widget(child, factor, visited_widgets)


def _base_text_control_minimum_height(widget: QWidget) -> int:
    stored = widget.property(_BASE_TEXT_CONTROL_MIN_HEIGHT)
    if stored is not None:
        try:
            return max(0, int(stored))
        except (TypeError, ValueError):
            pass

    base_size = widget.property(_BASE_MIN_SIZE)
    if isinstance(base_size, QSize):
        minimum_height = max(0, base_size.height())
    else:
        minimum_height = max(0, widget.minimumHeight())
    widget.setProperty(_BASE_TEXT_CONTROL_MIN_HEIGHT, minimum_height)
    return minimum_height


def _set_text_control_minimum_height(
    widget: QLineEdit | QComboBox,
    factor: float,
) -> None:
    # Padding совпадает с QSS в styles.py. Высота основана на фактическом
    # QFontMetrics виджета, поэтому текст не обрезается при любом масштабе.
    vertical_padding = 10 if isinstance(widget, QLineEdit) else 4
    border = max(
        scale_px(1, factor),
        int(
            widget.style().pixelMetric(
                QStyle.PixelMetric.PM_DefaultFrameWidth,
                None,
                widget,
            )
        ),
    )
    content_height = widget.fontMetrics().height()
    required_height = content_height + 2 * (scale_px(vertical_padding, factor) + border)
    base_minimum_height = _base_text_control_minimum_height(widget)
    widget.setMinimumHeight(max(_scale_value(base_minimum_height, factor), required_height))


def ensure_text_control_heights(root: QWidget, factor: float) -> None:
    """Дать полям ввода высоту, достаточную для текущего шрифта и QSS."""
    controls: list[QLineEdit | QComboBox] = []
    if isinstance(root, (QLineEdit, QComboBox)):
        controls.append(root)
    controls.extend(root.findChildren(QLineEdit))
    controls.extend(root.findChildren(QComboBox))
    for control in controls:
        _set_text_control_minimum_height(control, factor)
