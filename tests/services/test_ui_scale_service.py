import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.services.ui_scale_service import (
    calculate_auto_percent,
    calculate_final_percent,
    calculate_scale_factor,
    calculate_target_window_height,
    normalize_ui_scale_delta_percent,
    resolve_ui_scale_from_screen,
    scale_point_size,
    scale_px,
)


def test_calculate_auto_percent_reference() -> None:
    assert calculate_auto_percent(2560, 1440, 96.0) == 100


def test_calculate_auto_percent_clamps() -> None:
    # very small screen -> clamp to 70
    assert calculate_auto_percent(800, 600, 96.0) == 70
    # very large screen -> clamp to 200
    assert calculate_auto_percent(7680, 4320, 96.0) == 200


def test_calculate_auto_percent_dpi_scaling() -> None:
    # 1920x1080 @ 144 DPI (1.5x) normalized = 2880x1620 => ratio >1 => ~110
    auto = calculate_auto_percent(1920, 1080, 144.0)
    assert 70 <= auto <= 200
    assert auto % 10 == 0


def test_normalize_delta_clamp_and_step() -> None:
    assert normalize_ui_scale_delta_percent(100) == 50
    assert normalize_ui_scale_delta_percent(-100) == -50
    assert normalize_ui_scale_delta_percent(3) == 0
    assert normalize_ui_scale_delta_percent(7) == 10


def test_calculate_final_percent() -> None:
    # auto 100, delta 0 => 100
    assert calculate_final_percent(100, 0) == 100
    # auto 100, delta 50 => 150
    assert calculate_final_percent(100, 50) == 150
    # auto 70, delta 50 => 70 + 100*0.5=120
    assert calculate_final_percent(70, 50) == 120
    # clamp final (минимум 35 для самого малого поддерживаемого масштаба)
    assert calculate_final_percent(200, 50) == 300
    assert calculate_final_percent(70, -50) == 35


def test_calculate_scale_factor() -> None:
    assert calculate_scale_factor(100) == 1.0
    assert calculate_scale_factor(150) == 1.5
    assert calculate_scale_factor(70) == 0.7


def test_scale_px_and_point() -> None:
    assert scale_px(10, 1.5) == 15
    assert scale_px(7, 1.5) == 10  # round
    assert scale_point_size(10.0, 1.5) == 15.0


def test_resolve_ui_scale_from_screen() -> None:
    state = resolve_ui_scale_from_screen(2560, 1440, 96.0, 0)
    assert state.auto_percent == 100
    assert state.delta_percent == 0
    assert state.final_percent == 100
    assert state.scale_factor == 1.0

    state2 = resolve_ui_scale_from_screen(2560, 1440, 96.0, 20)
    assert state2.delta_percent == 20
    assert state2.final_percent == 120


def test_calculate_target_window_height() -> None:
    assert calculate_target_window_height(560, 1.0) == 560
    assert calculate_target_window_height(560, 1.5) == 840
    assert calculate_target_window_height(560, 0.7) == 392
