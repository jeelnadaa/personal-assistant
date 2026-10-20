"""Universal Windows Application Discovery, Resolution, and Launching Service.

Scans Start Menu shortcuts, Desktop links, Windows App Paths registry,
and installed application registries with persistent caching and fuzzy matching.
"""

from dataclasses import asdict, dataclass, field
import difflib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from jarvis.logger import logger

APPS_CACHE_FILE = Path("data/apps_cache.json")


@dataclass
class AppInfo:
    name: str
    target: str
    source: str
    aliases: list[str] = field(default_factory=list)


BUILTIN_APPS = {
    "notepad": AppInfo("Notepad", "notepad.exe", "builtin", ["notepad", "editor", "text editor"]),
    "calculator": AppInfo("Calculator", "calc.exe", "builtin", ["calc", "calculator"]),
    "file explorer": AppInfo("File Explorer", "explorer.exe", "builtin", ["explorer", "file explorer", "files"]),
    "command prompt": AppInfo("Command Prompt", "cmd.exe", "builtin", ["cmd", "command prompt", "terminal"]),
    "windows terminal": AppInfo("Windows Terminal", "wt.exe", "builtin", ["wt", "windows terminal", "terminal"]),
    "task manager": AppInfo("Task Manager", "taskmgr.exe", "builtin", ["task manager", "taskmgr"]),
    "paint": AppInfo("Paint", "mspaint.exe", "builtin", ["paint", "mspaint"]),
    "settings": AppInfo("Windows Settings", "ms-settings:", "builtin", ["settings", "windows settings"]),
    "spotify": AppInfo("Spotify", "spotify:", "builtin", ["spotify", "music"]),
    "edge": AppInfo("Microsoft Edge", "msedge.exe", "builtin", ["edge", "microsoft edge", "browser"]),
    "chrome": AppInfo("Google Chrome", "chrome.exe", "builtin", ["chrome", "google chrome"]),
    "vscode": AppInfo("Visual Studio Code", "code.cmd", "builtin", ["vscode", "code", "vs code"]),
}


def normalize_app_name(name: str) -> str:
    """Normalizes an application name or query for matching."""
    cleaned = re.sub(r"\.exe$", "", name, flags=re.IGNORECASE)
    cleaned = re.sub(r"\(.*?\)", "", cleaned)
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", " ", cleaned)
    return " ".join(cleaned.lower().split())


class AppResolver:
    """Discovers, indexes, resolves, and launches applications installed on Windows."""

    def __init__(self, cache_file: Path = APPS_CACHE_FILE) -> None:
        self.cache_file = cache_file
        self.apps: dict[str, AppInfo] = {}
        self.load_cache_or_scan()

    def load_cache_or_scan(self) -> None:
        """Loads cached app index from disk if present; otherwise performs full scan."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    raw_data = json.load(f)
                    for key, val in raw_data.items():
                        self.apps[key] = AppInfo(**val)
                logger.info("Loaded %d applications from cache: %s", len(self.apps), self.cache_file)
                return
            except Exception as e:
                logger.warning("Could not read apps cache (%s), running full scan...", e)

        self.refresh(force=True)

    def scan_start_menu_and_desktops(self) -> dict[str, AppInfo]:
        """Collects .lnk shortcuts from user and system Start Menus and Desktops."""
        found: dict[str, AppInfo] = {}
        scan_dirs: list[Path] = []

        # System Start Menu
        prog_data = os.environ.get("ProgramData")
        if prog_data:
            scan_dirs.append(Path(prog_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

        # User Start Menu
        app_data = os.environ.get("APPDATA")
        if app_data:
            scan_dirs.append(Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

        # User Desktop
        user_prof = os.environ.get("USERPROFILE")
        if user_prof:
            scan_dirs.append(Path(user_prof) / "Desktop")

        # Public Desktop
        pub_desktop = Path("C:/Users/Public/Desktop")
        if pub_desktop.exists():
            scan_dirs.append(pub_desktop)

        for s_dir in scan_dirs:
            if not s_dir.exists():
                continue
            try:
                for link in s_dir.rglob("*.lnk"):
                    # Ignore uninstall shortcuts
                    stem = link.stem
                    norm = normalize_app_name(stem)
                    if not norm or "uninstall" in norm or "remove" in norm or "help" in norm:
                        continue
                    found[norm] = AppInfo(
                        name=stem,
                        target=str(link.resolve()),
                        source="shortcut",
                        aliases=[norm, stem.lower()],
                    )
            except Exception as e:
                logger.debug("Error scanning directory '%s': %s", s_dir, e)

        return found

    def scan_registry_app_paths(self) -> dict[str, AppInfo]:
        """Discovers executables registered in Windows App Paths registry."""
        found: dict[str, AppInfo] = {}
        if sys.platform != "win32":
            return found

        import winreg

        subkeys = [
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths"),
        ]

        for root, subkey_path in subkeys:
            try:
                with winreg.OpenKey(root, subkey_path) as root_key:
                    count = winreg.QueryInfoKey(root_key)[0]
                    for i in range(count):
                        app_sub = winreg.EnumKey(root_key, i)
                        try:
                            with winreg.OpenKey(root_key, app_sub) as app_key:
                                exe_path, _ = winreg.QueryValueEx(app_key, "")
                                if exe_path and os.path.exists(exe_path.strip('"')):
                                    norm = normalize_app_name(app_sub)
                                    found[norm] = AppInfo(
                                        name=app_sub,
                                        target=exe_path.strip('"'),
                                        source="app_paths",
                                        aliases=[norm, app_sub.lower()],
                                    )
                        except Exception:
                            pass
            except Exception as e:
                logger.debug("Registry App Paths scan error: %s", e)

        return found

    def scan_registry_uninstall(self) -> dict[str, AppInfo]:
        """Discovers installed software from Windows Uninstall registry keys."""
        found: dict[str, AppInfo] = {}
        if sys.platform != "win32":
            return found

        import winreg

        subkeys = [
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]

        for root, subkey_path in subkeys:
            try:
                with winreg.OpenKey(root, subkey_path) as root_key:
                    count = winreg.QueryInfoKey(root_key)[0]
                    for i in range(count):
                        sub_name = winreg.EnumKey(root_key, i)
                        try:
                            with winreg.OpenKey(root_key, sub_name) as app_key:
                                display_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                display_icon, _ = winreg.QueryValueEx(app_key, "DisplayIcon")
                                if display_name and display_icon:
                                    icon_path = display_icon.split(",")[0].strip('"')
                                    if icon_path.lower().endswith(".exe") and os.path.exists(icon_path):
                                        norm = normalize_app_name(display_name)
                                        found[norm] = AppInfo(
                                            name=display_name,
                                            target=icon_path,
                                            source="uninstall_registry",
                                            aliases=[norm, display_name.lower()],
                                        )
                        except Exception:
                            pass
            except Exception as e:
                logger.debug("Uninstall registry scan error: %s", e)

        return found

    def refresh(self, force: bool = False) -> int:
        """Runs full discovery scan and updates the on-disk JSON cache."""
        logger.info("Refreshing Windows application index...")
        merged: dict[str, AppInfo] = {}

        # 1. Built-in defaults
        for k, v in BUILTIN_APPS.items():
            merged[k] = AppInfo(name=v.name, target=v.target, source=v.source, aliases=list(v.aliases))

        # Helper to merge items preserving existing aliases
        def merge_entry(k: str, new_info: AppInfo) -> None:
            if k in merged:
                merged[k].target = new_info.target
                combined_aliases = set(merged[k].aliases) | set(new_info.aliases)
                merged[k].aliases = list(combined_aliases)
            else:
                merged[k] = new_info

        # 2. Registry App Paths
        for k, v in self.scan_registry_app_paths().items():
            merge_entry(k, v)

        # 3. Uninstall registry
        for k, v in self.scan_registry_uninstall().items():
            merge_entry(k, v)

        # 4. Start Menu and Desktops (highest priority for user friendly names)
        for k, v in self.scan_start_menu_and_desktops().items():
            merge_entry(k, v)

        self.apps = merged

        # Save to disk
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_file, "w", encoding="utf-8") as f:
                serializable = {k: asdict(v) for k, v in self.apps.items()}
                json.dump(serializable, f, indent=2)
            logger.info("Saved %d applications to %s", len(self.apps), self.cache_file)
        except Exception as e:
            logger.warning("Could not persist apps cache: %s", e)

        return len(self.apps)

    def resolve(self, query: str) -> tuple[AppInfo | None, list[str]]:
        """Resolves an application query to a specific AppInfo or returns candidate matches.

        Returns:
            (matched_app, candidate_list)
            If matched_app is None and candidate_list is not empty, query is ambiguous.
        """
        clean = normalize_app_name(query)
        if not clean:
            return None, []

        # 1. Exact match on normalized key
        if clean in self.apps:
            return self.apps[clean], []

        # 2. Exact match in aliases
        for app in self.apps.values():
            if clean in app.aliases:
                return app, []

        # 3. Substring / Prefix match
        matches: list[AppInfo] = []
        for key, app in self.apps.items():
            if clean in key or any(clean in alias for alias in app.aliases):
                matches.append(app)

        if len(matches) == 1:
            return matches[0], []
        elif len(matches) > 1:
            # Check if one of them starts with the query exactly (e.g. "chrome" in "Google Chrome")
            exact_starts = [m for m in matches if normalize_app_name(m.name).startswith(clean)]
            if len(exact_starts) == 1:
                return exact_starts[0], []
            return None, [m.name for m in matches[:5]]

        # 4. Fuzzy matching via difflib
        keys = list(self.apps.keys())
        close_keys = difflib.get_close_matches(clean, keys, n=4, cutoff=0.55)
        if len(close_keys) == 1:
            return self.apps[close_keys[0]], []
        elif len(close_keys) > 1:
            return None, [self.apps[k].name for k in close_keys]

        return None, []

    def launch(self, query: str) -> tuple[bool, str]:
        """Resolves and launches the specified application.

        Returns:
            (success, message)
        """
        app, candidates = self.resolve(query)

        if app is None:
            if candidates:
                cand_str = ", ".join(f"'{c}'" for c in candidates)
                return False, f"Multiple applications matched '{query}': {cand_str}. Which one would you like to open?"
            return False, f"Could not find application '{query}'. Try refreshing the app index or opening by exact path."

        try:
            if app.target.startswith("ms-settings:") or app.target.startswith("spotify:"):
                os.startfile(app.target)
            elif app.target.endswith(".lnk") or os.path.isabs(app.target):
                os.startfile(app.target)
            else:
                try:
                    os.startfile(app.target)
                except Exception:
                    subprocess.Popen(app.target, shell=True)

            return True, f"Launched '{app.name}' via {app.source} ({app.target})."
        except Exception as e:
            logger.error("Failed to launch '%s' (%s): %s", app.name, app.target, e)
            return False, f"Failed to launch '{app.name}': {str(e)}"


_RESOLVER_INSTANCE: AppResolver | None = None


def get_app_resolver() -> AppResolver:
    """Returns singleton AppResolver instance."""
    global _RESOLVER_INSTANCE
    if _RESOLVER_INSTANCE is None:
        _RESOLVER_INSTANCE = AppResolver()
    return _RESOLVER_INSTANCE
