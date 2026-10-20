"""System control and information tools for Windows 11."""

from datetime import datetime
import os
import shutil
import subprocess
from typing import Any
import psutil

from jarvis.tools.base import tool, ToolResult
from jarvis.logger import logger

SETTINGS_PAGE_MAP = {
    "wifi": "ms-settings:network-wifi",
    "network": "ms-settings:network",
    "bluetooth": "ms-settings:bluetooth",
    "display": "ms-settings:display",
    "sound": "ms-settings:sound",
    "volume": "ms-settings:sound",
    "apps": "ms-settings:appsfeatures",
    "update": "ms-settings:windowsupdate",
    "windows update": "ms-settings:windowsupdate",
    "battery": "ms-settings:powersleep",
    "power": "ms-settings:powersleep",
    "storage": "ms-settings:storagesense",
    "notifications": "ms-settings:notifications",
}


@tool(
    name="get_system_info",
    description=(
        "Returns current system metrics: CPU usage %, RAM usage %, disk free space, "
        "battery percentage & charging state, and current local date and time."
    ),
    input_schema={
        "type": "object",
        "properties": {},
    },
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
    name="lock_screen",
    description="Locks the Windows workstation immediately.",
    input_schema={
        "type": "object",
        "properties": {},
    },
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
    input_schema={
        "type": "object",
        "properties": {},
    },
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
