"""Pure coordinate tests; no graphical display or pygame import required."""
import pytest

from experiments.catchup_dashboard import (
    W, H, fit_viewport, initial_window_size, mouse_to_canvas
)


def test_desktop_auto_sizes_leave_room_for_dock():
    assert initial_window_size((1440, 900)) == (1280, 740)
    assert initial_window_size((1280, 800)) == (1200, 640)
    assert initial_window_size((1920, 1080)) == (1280, 865)


@pytest.mark.parametrize("window_size", [(1280, 865), (1280, 740), (1000, 650), (720, 460), (1600, 900)])
def test_aspect_ratio_and_roundtrip(window_size):
    left, top, sw, sh = fit_viewport(window_size)
    assert 0 <= left and 0 <= top
    assert left + sw <= window_size[0] and top + sh <= window_size[1]
    assert abs(sw / sh - W / H) < 0.01
    for virtual in [(50, 90), (300, 200), (1000, 600), (640, 430), (1130, 750)]:
        point = (left + int((virtual[0] + 0.5) * sw / W),
                 top + int((virtual[1] + 0.5) * sh / H))
        mapped = mouse_to_canvas(point, window_size)
        assert mapped is not None
        # Pixel-quantization may shift a hit by about one virtual pixel.
        assert abs(mapped[0] - virtual[0]) <= 2
        assert abs(mapped[1] - virtual[1]) <= 2


def test_letterbox_click_does_not_activate_buttons():
    assert mouse_to_canvas((0, 0), (1600, 900)) is None
    assert mouse_to_canvas((1599, 899), (1600, 900)) is None


def test_bottom_bar_is_present_in_fit():
    window_size = (1000, 650)
    left, top, sw, sh = fit_viewport(window_size)
    # Physical location of bottom footer (virtual centre 850).
    pt = (left + sw // 2, top + int(850 * sh / H))
    hit = mouse_to_canvas(pt, window_size)
    assert hit is not None and 845 <= hit[1] <= 852


def test_invalid_sizes():
    with pytest.raises(ValueError):
        fit_viewport((1280, 0))
    with pytest.raises(ValueError):
        initial_window_size((0, 900))
