"""System control and information tools for Windows 11.

Includes volume, brightness, power state, network settings, and hardware metrics.
"""

from datetime import datetime
import os
import shutil
import subprocess
from typing import Any
import psutil

try:
    from pycaw.pycaw import AudioUtilities
except ImportError:
    AudioUtilities = None

try:
    import screen_brightness_control as sbc
except ImportError:
    sbc = None

from jarvis.logger import logger
from jarvis.tools.base import ToolResult, tool

SETTINGS_PAGE_MAP = {
    "wifi": "ms-settings:network-wifi",
    "network": "ms-settings:network",
    "bluetooth": "ms-settings:bluetooth",
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "volume": "ms-settings:sound",
    "apps": "ms-settings:appsfeatures",
    "installed apps": "ms-settings:appsfeatures",
    "update": "ms-settings:windowsupdate",
    "windows update": "ms-settings:windowsupdate",
    "battery": "ms-settings:powersleep",
    "power": "ms-settings:powersleep",
    "storage": "ms-settings:storagesense",
    "notifications": "ms-settings:notifications",
    "personalization": "ms-settings:personalization",
    "background": "ms-settings:personalization-background",
    "themes": "ms-settings:themes",
    "printers": "ms-settings:printers",
    "privacy": "ms-settings:privacy",
    "gaming": "ms-settings:gaming-gamebar",
    "default apps": "ms-settings:defaultapps",
    "taskbar": "ms-settings:taskbar",
    "date and time": "ms-settings:dateandtime",
    "mouse": "ms-settings:mousetouchpad",
}


def _get_audio_endpoint():
    """Retrieves the default audio endpoint volume interface."""
    if not AudioUtilities:
        return None
    try:
        device = AudioUtilities.GetSpeakers()
        if hasattr(device, "EndpointVolume"):
            return device.EndpointVolume
    except Exception as e:
        logger.warning("Could not obtain audio endpoint: %s", e)
    return None


@tool(
    name="set_volume",
    description="Sets the master system audio volume to a percentage between 0 and 100.",
    input_schema={
        "type": "object",
        "properties": {
            "percent": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Target volume percentage from 0 to 100.",
            }
        },
        "required": ["percent"],
    },
    dangerous=False,
    category="system",
)
def set_volume(percent: int) -> ToolResult:
    """Sets system master volume percentage."""
    vol = _get_audio_endpoint()
    if not vol:
        return ToolResult(ok=False, output="Audio control is unavailable.")

    clamped = max(0, min(100, int(percent)))
    scalar = clamped / 100.0
    try:
        vol.SetMasterVolumeLevelScalar(scalar, None)
        return ToolResult(ok=True, output=f"Volume set to {clamped}%.")
    except Exception as e:
        logger.error("Failed to set volume: %s", e)
        return ToolResult(ok=False, output=f"Failed to set volume: {str(e)}")


@tool(
    name="get_volume",
    description="Returns the current master system audio volume percentage and mute status.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="system",
)
def get_volume() -> ToolResult:
    """Retrieves current volume percentage and mute state."""
    vol = _get_audio_endpoint()
    if not vol:
        return ToolResult(ok=False, output="Audio control is unavailable.")

    try:
        scalar = vol.GetMasterVolumeLevelScalar()
        muted = bool(vol.GetMute())
        pct = int(round(scalar * 100))
        mute_str = " (Muted)" if muted else ""
        return ToolResult(ok=True, output=f"Current volume is {pct}%{mute_str}.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to read volume: {str(e)}")


@tool(
    name="mute",
    description="Mutes or unmutes the master system audio.",
    input_schema={
        "type": "object",
        "properties": {
            "state": {
                "type": "boolean",
                "description": "True to mute, False to unmute.",
            }
        },
        "required": ["state"],
    },
    dangerous=False,
    category="system",
)
def mute(state: bool) -> ToolResult:
    """Mutes or unmutes system audio."""
    vol = _get_audio_endpoint()
    if not vol:
        return ToolResult(ok=False, output="Audio control is unavailable.")

    try:
        vol.SetMute(int(state), None)
        action = "Muted" if state else "Unmuted"
        return ToolResult(ok=True, output=f"System audio {action}.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to toggle mute: {str(e)}")


@tool(
    name="set_brightness",
    description="Sets the primary display brightness percentage from 0 to 100.",
    input_schema={
        "type": "object",
        "properties": {
            "percent": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Brightness percentage from 0 to 100.",
            }
        },
        "required": ["percent"],
    },
    dangerous=False,
    category="system",
)
def set_brightness(percent: int) -> ToolResult:
    """Sets screen brightness percentage."""
    if not sbc:
        return ToolResult(ok=False, output="Screen brightness control is not available.")

    clamped = max(0, min(100, int(percent)))
    try:
        sbc.set_brightness(clamped)
        return ToolResult(ok=True, output=f"Display brightness set to {clamped}%.")
    except Exception as e:
        logger.error("Failed to set brightness: %s", e)
        return ToolResult(ok=False, output=f"Failed to set brightness: {str(e)}")


@tool(
    name="get_brightness",
    description="Gets the current primary display brightness percentage.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="system",
)
def get_brightness() -> ToolResult:
    """Retrieves current display brightness."""
    if not sbc:
        return ToolResult(ok=False, output="Screen brightness control is not available.")

    try:
        levels = sbc.get_brightness()
        val = levels[0] if isinstance(levels, list) and levels else levels
        return ToolResult(ok=True, output=f"Current display brightness is {val}%.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to get brightness: {str(e)}")


@tool(
    name="get_system_info",
    description=(
        "Returns current system metrics: CPU usage %, RAM usage %, disk free space, "
        "battery percentage & charging state, and current local date and time."
    ),
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="system",
)
def get_system_info() -> ToolResult:
    """Collects CPU, RAM, disk, battery, and timestamp information."""
    now = datetime.now()
    date_str = now.strftime("%A, %B %d, %Y")
    time_str = now.strftime("%I:%M %p")

    cpu_pct = psutil.cpu_percent(interval=0.1)
    ram = psutil.virtual_memory()
    ram_pct = ram.percent
    ram_avail_gb = ram.available / (1024**3)

    disk = shutil.disk_usage("C:\\")
    disk_free_gb = disk.free / (1024**3)
    disk_total_gb = disk.total / (1024**3)

    battery = psutil.sensors_battery()
    if battery:
        plugged = "plugged in" if battery.power_plugged else "on battery"
        battery_str = f"{battery.percent:.0f}% ({plugged})"
    else:
        battery_str = "No battery detected (Desktop/AC)"

    info = (
        f"Date: {date_str}\n"
        f"Time: {time_str}\n"
        f"CPU Usage: {cpu_pct}%\n"
        f"RAM Usage: {ram_pct}% (Available: {ram_avail_gb:.1f} GB)\n"
        f"C: Drive Free: {disk_free_gb:.1f} GB / {disk_total_gb:.1f} GB\n"
        f"Battery: {battery_str}"
    )
    return ToolResult(ok=True, output=info)


@tool(
    name="lock_screen",
    description="Locks the Windows workstation immediately.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="system",
)
def lock_screen() -> ToolResult:
    """Locks the workstation using user32.dll LockWorkStation."""
    try:
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True)
        return ToolResult(ok=True, output="Workstation locked.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to lock workstation: {str(e)}")


@tool(
    name="shutdown_pc",
    description="Shuts down, restarts, or puts the PC into sleep mode. Requires explicit user confirmation.",
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["shutdown", "restart", "sleep"],
                "description": "The power operation to perform: shutdown, restart, or sleep.",
            }
        },
        "required": ["action"],
    },
    dangerous=True,
    category="system",
)
def shutdown_pc(action: str) -> ToolResult:
    """Initiates shutdown, reboot, or suspend on the local machine."""
    act = action.strip().lower()
    try:
        if act == "shutdown":
            subprocess.run(["shutdown", "/s", "/t", "15", "/c", "Jarvis initiated shutdown in 15 seconds."], check=True)
            return ToolResult(ok=True, output="PC shutdown initiated in 15 seconds.")
        elif act == "restart":
            subprocess.run(["shutdown", "/r", "/t", "15", "/c", "Jarvis initiated restart in 15 seconds."], check=True)
            return ToolResult(ok=True, output="PC restart initiated in 15 seconds.")
        elif act == "sleep":
            subprocess.run(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"], check=True)
            return ToolResult(ok=True, output="PC placed in sleep mode.")
        else:
            return ToolResult(ok=False, output=f"Invalid shutdown action: '{action}'.")
    except Exception as e:
        logger.error("Failed to execute power action '%s': %s", action, e)
        return ToolResult(ok=False, output=f"Failed to {act} PC: {str(e)}")


@tool(
    name="toggle_wifi",
    description="Toggles Wi-Fi adapter state. Opens Settings page if direct adapter control is restricted.",
    input_schema={
        "type": "object",
        "properties": {
            "state": {"type": "boolean", "description": "True to enable, False to disable."}
        },
        "required": ["state"],
    },
    dangerous=False,
    category="system",
)
def toggle_wifi(state: bool) -> ToolResult:
    """Attempts to toggle Wi-Fi via netsh, falling back to opening Settings."""
    cmd_state = "ENABLED" if state else "DISABLED"
    try:
        res = subprocess.run(
            ["netsh", "interface", "set", "interface", 'name="Wi-Fi"', f"admin={cmd_state}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            return ToolResult(ok=True, output=f"Wi-Fi adapter {cmd_state.lower()}.")
    except Exception:
        pass

    # Fallback to ms-settings:network-wifi
    try:
        os.startfile("ms-settings:network-wifi")
        status = "enable" if state else "disable"
        return ToolResult(
            ok=True,
            output=f"Opened Wi-Fi Settings. Direct adapter toggle requires elevated privileges; please {status} Wi-Fi here.",
        )
    except Exception as e:
        return ToolResult(ok=False, output=f"Could not open Wi-Fi settings: {str(e)}")


@tool(
    name="toggle_bluetooth",
    description="Opens Bluetooth settings to manage device connections.",
    input_schema={
        "type": "object",
        "properties": {
            "state": {"type": "boolean", "description": "Desired state (True=on, False=off)."}
        },
        "required": ["state"],
    },
    dangerous=False,
    category="system",
)
def toggle_bluetooth(state: bool) -> ToolResult:
    """Opens Bluetooth settings since Windows does not provide unprivileged CLI bluetooth toggle."""
    try:
        os.startfile("ms-settings:bluetooth")
        desired = "on" if state else "off"
        return ToolResult(
            ok=True,
            output=f"Opened Bluetooth settings to turn Bluetooth {desired}.",
        )
    except Exception as e:
        return ToolResult(ok=False, output=f"Failed to open Bluetooth settings: {str(e)}")


@tool(
    name="open_settings_page",
    description="Opens a specific Windows Settings page (e.g. 'wifi', 'bluetooth', 'display', 'sound', 'update').",
    input_schema={
        "type": "object",
        "properties": {
            "page": {
                "type": "string",
                "description": "Friendly name of the settings page to open.",
            }
        },
        "required": ["page"],
    },
    dangerous=False,
    category="system",
)
def open_settings_page(page: str) -> ToolResult:
    """Opens a Windows 11 ms-settings page."""
    clean = page.strip().lower()
    uri = SETTINGS_PAGE_MAP.get(clean, "ms-settings:")
    try:
        os.startfile(uri)
        return ToolResult(ok=True, output=f"Opened Windows Settings for '{page}' ({uri}).")
    except Exception as e:
        logger.error("Failed to open settings page '%s': %s", page, e)
        return ToolResult(ok=False, output=f"Failed to open settings page: {str(e)}")


@tool(
    name="switch_llm_provider",
    description=(
        "Switches the active LLM brain provider at runtime (e.g. 'anthropic', 'gemini', 'groq'). "
        "Fails if the target provider has no API key configured. Changes memory state only."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "provider": {
                "type": "string",
                "enum": ["anthropic", "gemini", "groq"],
                "description": "Provider name to switch to.",
            }
        },
        "required": ["provider"],
    },
    dangerous=False,
    category="system",
)
def switch_llm_provider(provider: str) -> ToolResult:
    """Switches active LLM provider in environment without altering .env file."""
    p = provider.strip().lower()
    key_vars = {
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
    }
    if p not in key_vars:
        return ToolResult(ok=False, output=f"Unknown provider '{provider}'. Must be anthropic, gemini, or groq.")

    key = os.getenv(key_vars[p], "").strip()
    if not key:
        return ToolResult(ok=False, output=f"Cannot switch to '{p}': {key_vars[p]} is not configured.")

    os.environ["LLM_PROVIDER"] = p
    logger.info("Switched active LLM provider to %s", p)
    return ToolResult(ok=True, output=f"Successfully switched active brain provider to '{p}'.")


@tool(
    name="get_llm_info",
    description="Returns the currently active LLM provider and configured model name.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="system",
)
def get_llm_info() -> ToolResult:
    """Returns active LLM provider and model name."""
    provider = os.getenv("LLM_PROVIDER", "anthropic").strip().lower()
    model_vars = {
        "anthropic": "ANTHROPIC_MODEL",
        "gemini": "GEMINI_MODEL",
        "groq": "GROQ_MODEL",
    }
    model = os.getenv(model_vars.get(provider, "ANTHROPIC_MODEL"), "default")
    return ToolResult(ok=True, output=f"Active LLM Provider: {provider}\nActive Model: {model}")


@tool(
    name="media_control",
    description="Controls media playback across Windows (Spotify, YouTube, media players): play/pause, next track, previous track, or stop.",
    input_schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["play_pause", "next", "previous", "stop"],
                "description": "Media command: 'play_pause', 'next', 'previous', or 'stop'.",
            }
        },
        "required": ["action"],
    },
    dangerous=False,
    category="system",
)
def media_control(action: str) -> ToolResult:
    """Sends Windows virtual media key events."""
    import ctypes

    key_map = {
        "play_pause": 0xB3,  # VK_MEDIA_PLAY_PAUSE
        "next": 0xB0,        # VK_MEDIA_NEXT_TRACK
        "previous": 0xB1,    # VK_MEDIA_PREV_TRACK
        "stop": 0xB2,        # VK_MEDIA_STOP
    }
    act = action.strip().lower()
    vk_code = key_map.get(act)

    if not vk_code:
        return ToolResult(ok=False, output=f"Unknown media action '{action}'.")

    try:
        user32 = ctypes.windll.user32
        # Key down then key up
        user32.keybd_event(vk_code, 0, 0, 0)
        user32.keybd_event(vk_code, 0, 2, 0)  # KEYEVENTF_KEYUP = 2
        return ToolResult(ok=True, output=f"Triggered media action '{action}'.")
    except Exception as e:
        logger.error("Media key event failed: %s", e)
        return ToolResult(ok=False, output=f"Failed to execute media action '{action}': {str(e)}")


@tool(
    name="get_network_info",
    description="Returns active network interfaces, IP addresses, and tests internet connectivity.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="system",
)
def get_network_info() -> ToolResult:
    """Collects network adapters and tests internet connectivity."""
    import socket

    interfaces = psutil.net_if_addrs()
    active_ips = []
    for iface, addrs in interfaces.items():
        for addr in addrs:
            if addr.family == socket.AF_INET and not addr.address.startswith("127."):
                active_ips.append(f"{iface}: {addr.address}")

    # Check internet connectivity
    connected = False
    try:
        sock = socket.create_connection(("1.1.1.1", 53), timeout=2.0)
        sock.close()
        connected = True
    except Exception:
        pass

    conn_str = "Online (Connected to Internet)" if connected else "Offline (No Internet Connection)"
    ip_list = "\n".join(f"- {ip}" for ip in active_ips) if active_ips else "No active IPv4 addresses"

    return ToolResult(
        ok=True,
        output=f"Network Status: {conn_str}\n\nActive IP Addresses:\n{ip_list}",
    )


@tool(
    name="cancel_shutdown",
    description="Aborts and cancels any pending system shutdown or restart.",
    input_schema={"type": "object", "properties": {}},
    dangerous=False,
    category="system",
)
def cancel_shutdown() -> ToolResult:
    """Aborts Windows shutdown using shutdown /a."""
    try:
        subprocess.run(["shutdown", "/a"], check=True)
        return ToolResult(ok=True, output="Pending system shutdown or restart has been cancelled.")
    except Exception as e:
        return ToolResult(ok=False, output=f"Could not cancel shutdown: {str(e)}")
