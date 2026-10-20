"""Windows Startup Registration for Jarvis Desktop Assistant.

Configures Jarvis to run silently at user logon using pythonw.exe via:
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
"""

import argparse
from pathlib import Path
import sys

RUN_KEY_NAME = "JarvisAssistant"
REG_SUBKEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def get_command_path() -> tuple[Path, Path]:
    """Resolves the pythonw.exe interpreter and main.py paths."""
    repo_root = Path(__file__).resolve().parent.parent
    main_py = repo_root / "main.py"

    py_exe = Path(sys.executable)
    # Prefer pythonw.exe in the same directory as python.exe to prevent opening a console window
    pythonw = py_exe.parent / "pythonw.exe"
    if not pythonw.exists():
        pythonw = py_exe

    return pythonw, main_py


def install_to_startup(key_name: str = RUN_KEY_NAME) -> tuple[bool, str]:
    """Adds Jarvis command to HKCU Run key."""
    if sys.platform != "win32":
        return False, "Startup registration is only supported on Windows."

    import winreg

    pythonw, main_py = get_command_path()
    command = f'"{pythonw}" "{main_py}"'

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_SUBKEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, key_name, 0, winreg.REG_SZ, command)
        return True, f"Successfully registered Jarvis startup command:\n{command}"
    except Exception as e:
        return False, f"Failed to register startup key: {e}"


def uninstall_from_startup(key_name: str = RUN_KEY_NAME) -> tuple[bool, str]:
    """Removes Jarvis command from HKCU Run key."""
    if sys.platform != "win32":
        return False, "Startup registration is only supported on Windows."

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_SUBKEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            try:
                winreg.DeleteValue(key, key_name)
                return True, f"Successfully removed '{key_name}' from Windows startup."
            except FileNotFoundError:
                return True, f"'{key_name}' was not present in Windows startup."
    except Exception as e:
        return False, f"Failed to modify startup registry key: {e}"


def get_startup_status(key_name: str = RUN_KEY_NAME) -> tuple[bool, str | None]:
    """Checks if Jarvis is currently configured in HKCU Run key."""
    if sys.platform != "win32":
        return False, None

    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, REG_SUBKEY, 0, winreg.KEY_READ
        ) as key:
            value, _ = winreg.QueryValueEx(key, key_name)
            return True, value
    except FileNotFoundError:
        return False, None
    except Exception:
        return False, None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install or remove Jarvis from Windows Startup (HKCU Run)."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--install",
        action="store_true",
        default=True,
        help="Register Jarvis to run at Windows login (default action).",
    )
    group.add_argument(
        "--uninstall",
        "--remove",
        dest="uninstall",
        action="store_true",
        help="Remove Jarvis from Windows login startup.",
    )
    group.add_argument(
        "--status",
        action="store_true",
        help="Check current Windows startup registration status.",
    )
    parser.add_argument(
        "--silent",
        action="store_true",
        help="Suppress console output.",
    )

    args = parser.parse_args()

    if args.status:
        is_installed, command = get_startup_status()
        if not args.silent:
            if is_installed:
                print(f"[STATUS] Jarvis is REGISTERED in Windows startup:\n{command}")
            else:
                print("[STATUS] Jarvis is NOT currently registered in Windows startup.")
        return 0 if is_installed else 1

    if args.uninstall:
        ok, msg = uninstall_from_startup()
        if not args.silent:
            print(("[SUCCESS] " if ok else "[ERROR] ") + msg)
        return 0 if ok else 1

    ok, msg = install_to_startup()
    if not args.silent:
        print(("[SUCCESS] " if ok else "[ERROR] ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
