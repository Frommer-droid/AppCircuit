from __future__ import annotations

from dataclasses import dataclass

BASE_LOGICAL_DPI = 96.0
REFERENCE_WIDTH = 2560
REFERENCE_HEIGHT = 1440
MIN_MANUAL_SCALE_REFERENCE_PERCENT = 100


@dataclass(frozen=True, slots=True)
class UIScaleState:
    auto_percent: int
    delta_percent: int
    final_percent: int
    scale_factor: float


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _round_to_step(value: float, step: int) -> int:
    return int(round(value / step) * step)


def normalize_ui_scale_mode(value: object) -> str:
    return "auto"


def normalize_ui_scale_delta_percent(value: object) -> int:
    try:
        delta = int(value)
    except (TypeError, ValueError):
        return 0
    clamped = _clamp(delta, -50, 50)
    return _round_to_step(clamped, 10)


def normalize_ui_scale_percent(value: object) -> int:
    try:
        percent = int(value)
    except (TypeError, ValueError):
        return 100
    clamped = _clamp(percent, 35, 300)
    return _round_to_step(clamped, 5)


def calculate_auto_percent(
    available_width: int,
    available_height: int,
    logical_dpi: float,
) -> int:
    width = max(1, int(available_width))
    height = max(1, int(available_height))
    dpi = float(logical_dpi) if logical_dpi and logical_dpi > 0 else BASE_LOGICAL_DPI
    normalized_width = width * dpi / BASE_LOGICAL_DPI
    normalized_height = height * dpi / BASE_LOGICAL_DPI
    ratio_w = normalized_width / REFERENCE_WIDTH
    ratio_h = normalized_height / REFERENCE_HEIGHT
    ratio = min(ratio_w, ratio_h)
    raw_auto = ratio * 100.0
    auto = _round_to_step(raw_auto, 10)
    return _clamp(auto, 70, 200)


def calculate_final_percent(auto_percent: int, delta_percent: int) -> int:
    auto = _clamp(int(auto_percent), 70, 200)
    delta = normalize_ui_scale_delta_percent(delta_percent)
    delta_reference = max(auto, MIN_MANUAL_SCALE_REFERENCE_PERCENT)
    raw_final = auto + delta_reference * delta / 100.0
    final = _round_to_step(raw_final, 5)
    return _clamp(final, 35, 300)


def calculate_scale_factor(final_percent: int) -> float:
    return normalize_ui_scale_percent(final_percent) / 100.0


def calculate_target_window_height(base_height: int, scale_factor: float) -> int:
    try:
        base = int(base_height)
    except (TypeError, ValueError):
        base = 560
    factor = float(scale_factor) if scale_factor and scale_factor > 0 else 1.0
    return max(300, int(round(base * factor)))


def scale_px(value: int, scale_factor: float) -> int:
    try:
        base = int(value)
    except (TypeError, ValueError):
        return 0
    factor = float(scale_factor) if scale_factor and scale_factor > 0 else 1.0
    return max(0, int(round(base * factor)))


def scale_point_size(value: float, scale_factor: float) -> float:
    try:
        base = float(value)
    except (TypeError, ValueError):
        return 10.0
    factor = float(scale_factor) if scale_factor and scale_factor > 0 else 1.0
    return max(6.0, round(base * factor, 2))


def resolve_ui_scale_from_screen(
    available_width: int,
    available_height: int,
    logical_dpi: float,
    delta_percent: int,
) -> UIScaleState:
    auto = calculate_auto_percent(available_width, available_height, logical_dpi)
    delta = normalize_ui_scale_delta_percent(delta_percent)
    final = calculate_final_percent(auto, delta)
    factor = calculate_scale_factor(final)
    return UIScaleState(
        auto_percent=auto,
        delta_percent=delta,
        final_percent=final,
        scale_factor=factor,
    )
