"""Screen capture, UI Automation (pywinauto UIA), and vision inspection tools."""

import base64
import json
from pathlib import Path
import re
from typing import Any
import mss
from PIL import Image
import pyautogui

try:
    from pywinauto import Desktop
except ImportError:
    Desktop = None

from jarvis.brain.llm import get_vision_provider
from jarvis.brain.providers.base import Msg
from jarvis.logger import logger
from jarvis.tools.base import ToolResult, tool

SCREEN_DIR = Path("data/screens")


def calculate_downscale_dimensions(orig_w: int, orig_h: int, max_side: int = 1568) -> tuple[int, int, float]:
    """Calculates downscaled dimensions keeping aspect ratio, and returns scale factor (s = orig_w / sent_w)."""
    longest = max(orig_w, orig_h)
    if longest <= max_side:
        return orig_w, orig_h, 1.0
    ratio = longest / max_side
    sent_w = int(round(orig_w / ratio))
    sent_h = int(round(orig_h / ratio))
    s = orig_w / sent_w
    return sent_w, sent_h, s


def scale_coordinates(x: int, y: int, scale_factor: float) -> tuple[int, int]:
    """Scales vision coordinates back to original physical screen pixels."""
    return int(round(x * scale_factor)), int(round(y * scale_factor))


@tool(
    name="get_screen_size",
    description="Returns the logical desktop resolution and primary monitor dimensions for coordinate planning.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="screen",
)
def get_screen_size() -> ToolResult:
    """Returns primary monitor dimensions."""
    try:
        w, h = pyautogui.size()
        return ToolResult(ok=True, output=f"Primary monitor resolution: {w}x{h} pixels.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to get screen size: {str(e)}")


@tool(
    name="take_screenshot",
    description="Captures the primary monitor screenshot, saves it to data/screens/latest.png, and returns it.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="screen",
)
def take_screenshot() -> ToolResult:
    """Takes a screenshot of primary monitor."""
    SCREEN_DIR.mkdir(parents=True, exist_ok=True)
    out_file = SCREEN_DIR / "latest.png"

    try:
        with mss.MSS() as sct:
            mon = sct.monitors[1]  # primary monitor
            shot = sct.grab(mon)
            img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
            img.save(out_file, format="PNG")

        return ToolResult(
            ok=True,
            output=f"Screenshot captured ({shot.width}x{shot.height}) and saved to {out_file}.",
            image_path=str(out_file),
        )
    except Exception as e:
        logger.error("Screenshot capture failed: %s", e)
        return ToolResult(ok=False, output=f"Failed to take screenshot: {str(e)}")


@tool(
    name="get_ui_elements",
    description=(
        "Uses Windows UI Automation (pywinauto UIA) to list clickable controls (name, type, bounding rectangle) "
        "inside a window. Prefer this over vision whenever possible as it is exact and instant."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "window_title_contains": {
                "type": "string",
                "description": "Substring of the window title to inspect.",
            }
        },
        "required": ["window_title_contains"],
    },
    dangerous=False,
    category="screen",
)
def get_ui_elements(window_title_contains: str) -> ToolResult:
    """Inspects window hierarchy using UIA and returns clickable elements."""
    if not Desktop:
        return ToolResult(ok=False, output="pywinauto is not available.")

    clean = window_title_contains.strip()
    try:
        desktop = Desktop(backend="uia")
        pattern = re.compile(f".*{re.escape(clean)}.*", re.IGNORECASE)
        windows = desktop.windows(title_re=pattern, visible_only=True)
        if not windows:
            return ToolResult(ok=False, output=f"No visible window found matching '{clean}'.")

        target_win = windows[0]
        elements = []
        for ctrl in target_win.descendants():
            info = ctrl.element_info
            name = info.name.strip() if info.name else ""
            c_type = info.control_type or "Unknown"
            rect = info.rectangle
            if name and c_type in ("Button", "MenuItem", "TabItem", "Hyperlink", "CheckBox", "ListItem"):
                elements.append(f"[{c_type}] '{name}' at ({rect.left}, {rect.top})")
            if len(elements) >= 30:
                break

        if not elements:
            return ToolResult(ok=True, output=f"Found window '{target_win.window_text()}', but no standard clickable UIA controls were identified.")

        return ToolResult(ok=True, output=f"UIA Elements in '{target_win.window_text()}':\n" + "\n".join(elements))
    except Exception as e:
        logger.error("Error inspecting UI elements for '%s': %s", clean, e)
        return ToolResult(ok=False, output=f"UIA inspection error: {str(e)}")


@tool(
    name="click_ui_element",
    description="Finds a UI control by name within a window via Windows UI Automation and invokes/clicks it.",
    input_schema={
        "type": "object",
        "properties": {
            "window_title_contains": {"type": "string", "description": "Target window title substring."},
            "element_name": {"type": "string", "description": "The exact or partial text/name of the control to click."},
        },
        "required": ["window_title_contains", "element_name"],
    },
    dangerous=False,
    category="screen",
)
def click_ui_element(window_title_contains: str, element_name: str) -> ToolResult:
    """Clicks a control found via UIA."""
    if not Desktop:
        return ToolResult(ok=False, output="pywinauto is not available.")

    w_clean = window_title_contains.strip()
    e_clean = element_name.strip().lower()

    try:
        desktop = Desktop(backend="uia")
        windows = desktop.windows(title_re=re.compile(f".*{re.escape(w_clean)}.*", re.IGNORECASE), visible_only=True)
        if not windows:
            return ToolResult(ok=False, output=f"No window found matching '{w_clean}'.")

        win = windows[0]
        try:
            win.set_focus()
        except Exception:
            pass

        target_ctrl = None
        for ctrl in win.descendants():
            raw_name = ctrl.element_info.name or ""
            c_name = raw_name.replace("&", "").strip().lower()
            if e_clean == c_name or e_clean in c_name:
                target_ctrl = ctrl
                break

        if not target_ctrl:
            return ToolResult(ok=False, output=f"Control '{element_name}' not found in window '{win.window_text()}'.")

        try:
            target_ctrl.click_input()
        except Exception:
            rect = target_ctrl.element_info.rectangle
            mid_x = (rect.left + rect.right) // 2
            mid_y = (rect.top + rect.bottom) // 2
            pyautogui.click(mid_x, mid_y)

        return ToolResult(ok=True, output=f"Clicked UI element '{element_name}' in window '{win.window_text()}'.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to click UI element: {str(e)}")


@tool(
    name="read_screen_text",
    description="Takes a screenshot and uses the vision LLM to describe what is currently visible on the screen.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="screen",
)
def read_screen_text() -> ToolResult:
    """Transcribes screen contents using vision LLM or structural window inspection."""
    shot_res = take_screenshot()
    provider = get_vision_provider()

    if not shot_res.ok or not shot_res.image_path or not provider.supports_vision:
        from jarvis.tools.windows_mgmt import get_active_window, list_windows
        act = get_active_window()
        wins = list_windows()
        return ToolResult(
            ok=True,
            output=f"Current desktop state: Active window is {act.output}. {wins.output}",
            image_path=None,
        )

    try:
        with Image.open(shot_res.image_path) as im:
            orig_w, orig_h = im.size
            sent_w, sent_h, _ = calculate_downscale_dimensions(orig_w, orig_h, 1568)
            im_resized = im.resize((sent_w, sent_h), Image.Resampling.LANCZOS)
            temp_path = SCREEN_DIR / "vision_temp.png"
            im_resized.save(temp_path, format="PNG")

        with open(temp_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")

        prompt = "Describe the main applications, windows, and text visible on this screen in 2-3 concise sentences."
        resp = provider.chat(
            system="You are an expert PC screen reader.",
            messages=[Msg(role="user", text=prompt, images_b64=[b64_data])],
            tools=[],
            max_tokens=200,
            temperature=0.1,
        )
        return ToolResult(ok=True, output=resp.text.strip(), image_path=shot_res.image_path)
    except Exception as e:
        logger.error("Vision screen reading failed: %s", e)
        return ToolResult(ok=False, output=f"Vision inspection failed: {str(e)}")


@tool(
    name="find_and_click",
    description="Takes a screenshot, locates a described visual element using vision AI, and clicks its center.",
    input_schema={
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Visual description of the target element to click (e.g. 'the blue submit button').",
            }
        },
        "required": ["description"],
    },
    dangerous=False,
    category="screen",
)
def find_and_click(description: str) -> ToolResult:
    """Finds coordinates of element via vision LLM and clicks."""
    shot_res = take_screenshot()
    if not shot_res.ok or not shot_res.image_path:
        return ToolResult(ok=False, output="Failed to capture screenshot.")

    provider = get_vision_provider()
    if not provider.supports_vision:
        return ToolResult(ok=False, output="Configured LLM provider does not support vision required for find_and_click.")

    try:
        with Image.open(shot_res.image_path) as im:
            orig_w, orig_h = im.size
            sent_w, sent_h, scale = calculate_downscale_dimensions(orig_w, orig_h, 1568)
            im_resized = im.resize((sent_w, sent_h), Image.Resampling.LANCZOS)
            temp_path = SCREEN_DIR / "vision_click_temp.png"
            im_resized.save(temp_path, format="PNG")

        with open(temp_path, "rb") as f:
            b64_data = base64.b64encode(f.read()).decode("utf-8")

        prompt = (
            f"Locate the element: '{description}'. "
            f"The image resolution is {sent_w}x{sent_h}. "
            f'Reply ONLY with valid JSON in this exact format: {{"x": <integer>, "y": <integer>, "found": true|false}}'
        )

        resp = provider.chat(
            system="You return only JSON object with coordinates.",
            messages=[Msg(role="user", text=prompt, images_b64=[b64_data])],
            tools=[],
            max_tokens=60,
            temperature=0.0,
        )

        match = re.search(r"\{.*\}", resp.text, re.DOTALL)
        if not match:
            return ToolResult(ok=False, output=f"Vision model did not return coordinates: {resp.text}")

        data = json.loads(match.group(0))
        if not data.get("found", False):
            return ToolResult(ok=False, output=f"Visual element '{description}' not found on screen.")

        click_x, click_y = scale_coordinates(int(data["x"]), int(data["y"]), scale)
        pyautogui.click(click_x, click_y)
        return ToolResult(ok=True, output=f"Clicked '{description}' at ({click_x}, {click_y}).")
    except Exception as e:
        logger.error("find_and_click failed: %s", e)
        return ToolResult(ok=False, output=f"Failed to find and click element: {str(e)}")
