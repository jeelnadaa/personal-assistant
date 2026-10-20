"""Comprehensive unit tests for all Jarvis tools implemented in Phase 2."""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from jarvis.tools import get_tool, get_tool_schemas, run_tool
from jarvis.tools.base import ToolResult
from jarvis.tools.clipboard import get_clipboard, set_clipboard
from jarvis.tools.files import (
    copy_file,
    create_folder,
    delete_file,
    list_folder,
    move_file,
    read_text_file,
    search_files,
    write_text_file,
)
from jarvis.tools.input_control import click, hotkey, move_mouse, press_key, scroll, type_text, wait
from jarvis.tools.screen import (
    calculate_downscale_dimensions,
    get_screen_size,
    scale_coordinates,
    take_screenshot,
)
from jarvis.tools.shell import run_command
from jarvis.tools.system import (
    get_brightness,
    get_llm_info,
    get_system_info,
    get_volume,
    mute,
    set_brightness,
    set_volume,
    switch_llm_provider,
)
from jarvis.tools.web import browser_get_page_text, open_url, web_search
from jarvis.tools.windows_mgmt import get_active_window, list_windows, snap_window


# =========================================================================
# File System Tools (Using Safe Temp Directories)
# =========================================================================
def test_files_crud_operations(tmp_path: Path):
    """Tests file writing, reading, listing, copying, moving, and deletion."""
    test_file = tmp_path / "hello.txt"

    # Write file
    w_res = write_text_file(path=str(test_file), content="Hello Jarvis World!")
    assert w_res.ok is True
    assert test_file.exists()

    # Overwrite protection
    w_res_dup = write_text_file(path=str(test_file), content="Overwritten", overwrite=False)
    assert w_res_dup.ok is False
    assert "already exists" in w_res_dup.output

    # Read file
    r_res = read_text_file(path=str(test_file))
    assert r_res.ok is True
    assert "Hello Jarvis World!" in r_res.output

    # List folder
    l_res = list_folder(path=str(tmp_path))
    assert l_res.ok is True
    assert "hello.txt" in l_res.output

    # Search file
    s_res = search_files(query="hello", folder=str(tmp_path))
    assert s_res.ok is True
    assert "hello.txt" in s_res.output

    # Copy file
    copy_dest = tmp_path / "hello_copy.txt"
    c_res = copy_file(src=str(test_file), dst=str(copy_dest))
    assert c_res.ok is True
    assert copy_dest.exists()

    # Move file
    move_dest = tmp_path / "hello_moved.txt"
    m_res = move_file(src=str(copy_dest), dst=str(move_dest))
    assert m_res.ok is True
    assert not copy_dest.exists()
    assert move_dest.exists()

    # Create folder
    new_dir = tmp_path / "subfolder" / "nested"
    f_res = create_folder(path=str(new_dir))
    assert f_res.ok is True
    assert new_dir.exists()

    # Delete file via send2trash (mocked to prevent touching user recycle bin in test)
    with patch("send2trash.send2trash") as mock_trash:
        d_res = delete_file(path=str(move_dest))
        assert d_res.ok is True
        mock_trash.assert_called_once_with(str(move_dest))


# =========================================================================
# Screen & DPI Scaling Math
# =========================================================================
def test_screen_dpi_scaling_math():
    """Unit test verifying screenshot downscale dimensions and coordinate un-scaling.

    Tests standard 1080p, 1440p, 4K, and simulated 125% and 150% Windows display scaling.
    """
    # 1. 1920x1080 (100% scaling, longest side 1920 > 1568)
    sent_w, sent_h, scale = calculate_downscale_dimensions(1920, 1080, max_side=1568)
    assert sent_w == 1568
    assert sent_h == 882
    # Verify coordinate translation
    click_x, click_y = scale_coordinates(784, 441, scale)
    assert abs(click_x - 960) <= 2
    assert abs(click_y - 540) <= 2

    # 2. 2560x1440 (125% simulated display resolution: 2560x1440 physical)
    sent_w2, sent_h2, scale2 = calculate_downscale_dimensions(2560, 1440, max_side=1568)
    assert sent_w2 == 1568
    assert sent_h2 == 882
    click_x2, click_y2 = scale_coordinates(784, 441, scale2)
    assert abs(click_x2 - 1280) <= 2
    assert abs(click_y2 - 720) <= 2

    # 3. 3840x2160 (4K display at 150% scaling)
    sent_w3, sent_h3, scale3 = calculate_downscale_dimensions(3840, 2160, max_side=1568)
    assert sent_w3 == 1568
    assert sent_h3 == 882
    click_x3, click_y3 = scale_coordinates(784, 441, scale3)
    assert abs(click_x3 - 1920) <= 2
    assert abs(click_y3 - 1080) <= 2

    # 4. Small display (under 1568): no downscaling needed
    w_small, h_small, scale_small = calculate_downscale_dimensions(1280, 720, max_side=1568)
    assert w_small == 1280
    assert h_small == 720
    assert scale_small == 1.0


def test_take_screenshot():
    """Verifies that take_screenshot creates a valid PNG file and returns its image_path."""
    mock_shot = MagicMock()
    mock_shot.size = (1920, 1080)
    mock_shot.width = 1920
    mock_shot.height = 1080
    mock_shot.bgra = b"\x00" * (1920 * 1080 * 4)

    with patch("mss.MSS") as mock_mss_cls:
        mock_instance = MagicMock()
        mock_instance.monitors = [{}, {"left": 0, "top": 0, "width": 1920, "height": 1080}]
        mock_instance.grab.return_value = mock_shot
        mock_mss_cls.return_value.__enter__.return_value = mock_instance

        res = take_screenshot()
        assert res.ok is True
        assert res.image_path is not None
        assert Path(res.image_path).exists()


def test_get_screen_size():
    """Verifies get_screen_size returns screen resolution."""
    res = get_screen_size()
    assert res.ok is True
    assert "resolution" in res.output.lower()


# =========================================================================
# Clipboard Tools
# =========================================================================
def test_clipboard_set_and_get():
    """Verifies copying and pasting text using pyperclip."""
    sample = "Jarvis test token 98765"
    set_res = set_clipboard(sample)
    assert set_res.ok is True

    get_res = get_clipboard()
    assert get_res.ok is True
    assert sample in get_res.output


# =========================================================================
# System & Hardware Controls (Mocked Hardware)
# =========================================================================
def test_volume_controls():
    """Verifies set_volume, get_volume, and mute."""
    mock_endpoint = MagicMock()
    mock_endpoint.GetMasterVolumeLevelScalar.return_value = 0.5
    mock_endpoint.GetMute.return_value = 0

    with patch("jarvis.tools.system._get_audio_endpoint", return_value=mock_endpoint):
        # Set volume
        sv_res = set_volume(30)
        assert sv_res.ok is True
        mock_endpoint.SetMasterVolumeLevelScalar.assert_called_once_with(0.3, None)

        # Get volume
        gv_res = get_volume()
        assert gv_res.ok is True
        assert "50%" in gv_res.output

        # Mute
        m_res = mute(True)
        assert m_res.ok is True
        mock_endpoint.SetMute.assert_called_once_with(1, None)


def test_brightness_controls():
    """Verifies brightness get and set."""
    with patch("screen_brightness_control.get_brightness", return_value=[75]) as mock_get, \
         patch("screen_brightness_control.set_brightness") as mock_set:
        gb_res = get_brightness()
        assert gb_res.ok is True
        assert "75%" in gb_res.output

        sb_res = set_brightness(60)
        assert sb_res.ok is True
        mock_set.assert_called_once_with(60)


def test_switch_llm_provider():
    """Verifies switching LLM provider in memory."""
    with patch.dict("os.environ", {"GROQ_API_KEY": "dummy_groq", "LLM_PROVIDER": "anthropic"}):
        res = switch_llm_provider("groq")
        assert res.ok is True
        assert "groq" in res.output

        info = get_llm_info()
        assert "groq" in info.output.lower()


# =========================================================================
# Input Control Tools (Mocked PyAutoGUI)
# =========================================================================
def test_input_control_operations():
    """Verifies typing, keypress, hotkey, mouse clicks, and wait."""
    with patch("pyautogui.write") as mock_write, \
         patch("pyautogui.press") as mock_press, \
         patch("pyautogui.hotkey") as mock_hotkey, \
         patch("pyautogui.click") as mock_click, \
         patch("pyautogui.moveTo") as mock_move:

        # Type short text
        t_res = type_text("short")
        assert t_res.ok is True
        mock_write.assert_called_once_with("short", interval=0.02)

        # Press key
        p_res = press_key("enter")
        assert p_res.ok is True
        mock_press.assert_called_once_with("enter")

        # Hotkey
        hk_res = hotkey(["ctrl", "c"])
        assert hk_res.ok is True
        mock_hotkey.assert_called_once_with("ctrl", "c")

        # Click
        c_res = click(x=100, y=200, button="left")
        assert c_res.ok is True
        mock_click.assert_called_once_with(x=100, y=200, button="left", clicks=1)

        # Move mouse
        m_res = move_mouse(x=300, y=400)
        assert m_res.ok is True
        mock_move.assert_called_once_with(x=300, y=400)

        # Wait
        w_res = wait(0.01)
        assert w_res.ok is True


# =========================================================================
# Shell Execution Tool
# =========================================================================
def test_shell_run_command():
    """Verifies powershell execution via run_command."""
    res = run_command('Write-Output "Jarvis Shell Test"')
    assert res.ok is True
    assert "Jarvis Shell Test" in res.output


# =========================================================================
# Web Tools
# =========================================================================
def test_web_search():
    """Verifies web_search URL encoding."""
    with patch("webbrowser.open") as mock_open:
        res = web_search("python tutorials 2026")
        assert res.ok is True
        mock_open.assert_called_once_with("https://www.google.com/search?q=python+tutorials+2026")


# =========================================================================
# Windows Management Tools
# =========================================================================
def test_windows_mgmt_basics():
    """Verifies listing windows and getting active window."""
    lw_res = list_windows()
    assert lw_res.ok is True

    gw_res = get_active_window()
    assert gw_res.ok is True
