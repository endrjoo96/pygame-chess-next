import pytest

from web.build import _set_canvas_viewport_scale


def test_web_build_uses_full_browser_viewport():
    html = "config = { gui_divider : 2, gui_debug : 2 }"

    assert _set_canvas_viewport_scale(html) == (
        "config = { gui_divider : 1, gui_debug : 2 }")


def test_web_build_fails_if_pygbag_template_has_no_canvas_scale_setting():
    with pytest.raises(RuntimeError, match="gui_divider"):
        _set_canvas_viewport_scale("config = { gui_debug : 2 }")
