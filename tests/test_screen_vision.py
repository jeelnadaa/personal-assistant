"""Unit tests for Phase 6 Screen Vision, Scaling Math, UIA Automation, and Screenshot Pruning."""

import base64
import io
from pathlib import Path
from unittest.mock import MagicMock, patch
import numpy as np
from PIL import Image
import pytest

from jarvis.brain.agent import _encode_image_b64, _prune_older_screenshots
from jarvis.brain.providers.base import Msg, ToolResultMsg
from jarvis.tools.screen import (
    calculate_downscale_dimensions,
    click_ui_element,
    find_and_click,
    get_screen_size,
    get_ui_elements,
    read_screen_text,
    scale_coordinates,
    take_screenshot,
)


def test_dpi_scaling_simulated_displays():
    """Verifies coordinate scaling and aspect ratio on 100%, 125%, and 150% simulated displays."""
    # 1. 1080p display (1920x1080)
    w1, h1, s1 = calculate_downscale_dimensions(1920, 1080, max_side=1568)
    assert w1 == 1568
    assert h1 == 882
    assert abs(s1 - (1920 / 1568)) < 1e-4
    # Round-trip coordinate translation (e.g. center click)
    orig_x1, orig_y1 = 960, 540
    sent_x1 = int(round(orig_x1 / s1))
    sent_y1 = int(round(orig_y1 / s1))
    recov_x1, recov_y1 = scale_coordinates(sent_x1, sent_y1, s1)
    assert abs(recov_x1 - orig_x1) <= 1
    assert abs(recov_y1 - orig_y1) <= 1

    # 2. Simulated 125% DPI display (1440p physical 2560x1440 -> logical 2048x1152)
    w2, h2, s2 = calculate_downscale_dimensions(2048, 1152, max_side=1568)
    assert w2 == 1568
    assert h2 == 882
    orig_x2, orig_y2 = 1024, 576
    sent_x2 = int(round(orig_x2 / s2))
    sent_y2 = int(round(orig_y2 / s2))
    recov_x2, recov_y2 = scale_coordinates(sent_x2, sent_y2, s2)
    assert abs(recov_x2 - orig_x2) <= 1
    assert abs(recov_y2 - orig_y2) <= 1

    # 3. Simulated 150% DPI display (4K physical 3840x2160 -> logical 2560x1440)
    w3, h3, s3 = calculate_downscale_dimensions(2560, 1440, max_side=1568)
    assert w3 == 1568
    assert h3 == 882
    orig_x3, orig_y3 = 1280, 720
    sent_x3 = int(round(orig_x3 / s3))
    sent_y3 = int(round(orig_y3 / s3))
    recov_x3, recov_y3 = scale_coordinates(sent_x3, sent_y3, s3)
    assert abs(recov_x3 - orig_x3) <= 1
    assert abs(recov_y3 - orig_y3) <= 1

    # 4. Display smaller than max_side (1280x720) - no scaling required
    w4, h4, s4 = calculate_downscale_dimensions(1280, 720, max_side=1568)
    assert w4 == 1280
    assert h4 == 720
    assert s4 == 1.0


def test_screenshot_pruning():
    """Verifies that older screenshots in conversation messages are pruned, keeping latest 3."""
    messages = []
    for i in range(5):
        tr = ToolResultMsg(
            call_id=f"c_{i}",
            name="take_screenshot",
            output=f"Screenshot {i}",
            image_b64=f"fake_b64_data_{i}",
        )
        messages.append(Msg(role="tool", tool_results=[tr]))

    _prune_older_screenshots(messages, keep_count=3)

    # First two should have their image_b64 pruned
    assert messages[0].tool_results[0].image_b64 is None
    assert "[old screenshot removed]" in messages[0].tool_results[0].output

    assert messages[1].tool_results[0].image_b64 is None
    assert "[old screenshot removed]" in messages[1].tool_results[0].output

    # Last three should retain image_b64
    assert messages[2].tool_results[0].image_b64 == "fake_b64_data_2"
    assert messages[3].tool_results[0].image_b64 == "fake_b64_data_3"
    assert messages[4].tool_results[0].image_b64 == "fake_b64_data_4"


def test_encode_image_b64_downscaling(tmp_path):
    """Verifies that _encode_image_b64 downscales large images to max 1568px."""
    # Create large image (2500 x 2000)
    large_img = Image.new("RGB", (2500, 2000), color=(100, 150, 200))
    test_path = tmp_path / "large_test.png"
    large_img.save(test_path)

    b64_str = _encode_image_b64(str(test_path))
    assert b64_str is not None

    # Decode and check dimensions
    raw_bytes = base64.b64decode(b64_str)
    decoded_img = Image.open(io.BytesIO(raw_bytes))
    assert max(decoded_img.size) <= 1568


def test_uia_get_ui_elements_mock():
    """Verifies get_ui_elements finds and lists clickable elements."""
    mock_ctrl = MagicMock()
    mock_ctrl.element_info.name = "File"
    mock_ctrl.element_info.control_type = "MenuItem"
    mock_ctrl.element_info.rectangle.left = 100
    mock_ctrl.element_info.rectangle.top = 50

    mock_win = MagicMock()
    mock_win.window_text.return_value = "Untitled - Notepad"
    mock_win.descendants.return_value = [mock_ctrl]

    mock_desktop = MagicMock()
    mock_desktop.windows.return_value = [mock_win]

    with patch("jarvis.tools.screen.Desktop", return_value=mock_desktop):
        res = get_ui_elements("Notepad")
        assert res.ok is True
        assert "File" in res.output
        assert "MenuItem" in res.output


def test_uia_click_ui_element_mock():
    """Verifies click_ui_element locates and triggers target control."""
    mock_ctrl = MagicMock()
    mock_ctrl.element_info.name = "Edit"
    mock_ctrl.element_info.rectangle.left = 200
    mock_ctrl.element_info.rectangle.top = 50
    mock_ctrl.element_info.rectangle.right = 240
    mock_ctrl.element_info.rectangle.bottom = 70

    mock_win = MagicMock()
    mock_win.window_text.return_value = "Untitled - Notepad"
    mock_win.descendants.return_value = [mock_ctrl]

    mock_desktop = MagicMock()
    mock_desktop.windows.return_value = [mock_win]

    with patch("jarvis.tools.screen.Desktop", return_value=mock_desktop):
        res = click_ui_element("Notepad", "Edit")
        assert res.ok is True
        assert "Clicked UI element 'Edit'" in res.output
        assert mock_ctrl.click_input.called


def test_find_and_click_vision_mock(tmp_path):
    """Verifies find_and_click coordinates parsing and scaling."""
    test_img = Image.new("RGB", (1920, 1080), color=(20, 20, 20))
    test_path = tmp_path / "screen.png"
    test_img.save(test_path)

    mock_provider = MagicMock()
    mock_provider.supports_vision = True
    # LLM returns coordinates in downscaled 1568x882 image: center at 784, 441
    mock_provider.chat.return_value.text = '{"x": 784, "y": 441, "found": true}'

    with patch("jarvis.tools.screen.take_screenshot") as mock_shot:
        mock_shot.return_value.ok = True
        mock_shot.return_value.image_path = str(test_path)

        with patch("jarvis.tools.screen.get_vision_provider", return_value=mock_provider):
            with patch("pyautogui.click") as mock_click:
                res = find_and_click("search button")
                assert res.ok is True
                assert mock_click.called
                # Verify scaled coordinates near 960, 540
                args = mock_click.call_args[0]
                assert abs(args[0] - 960) <= 2
                assert abs(args[1] - 540) <= 2
