"""Interactive first-run pre-flight check script for Jarvis.

Checks LLM keys, microphone hardware, speech recognition, speech synthesis,
and browser automation, printing a clean diagnostic report.
"""

from pathlib import Path
import sys

# Ensure repository root is on sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from jarvis.setup_check import run_all_checks


def main() -> int:
    print("=" * 65)
    print(" Jarvis Desktop Assistant - Pre-Flight Setup Check")
    print("=" * 65)
    print("Running diagnostic tests...\n")

    results = run_all_checks()
    has_critical_failure = False

    for res in results:
        status_bracket = f"[{res.status}]"
        print(f"{status_bracket:<8} {res.name}")
        print(f"         {res.message}")
        if res.fix_hint:
            print(f"         Fix: {res.fix_hint}")
        print()

        if res.status == "FAIL":
            has_critical_failure = True

    print("=" * 65)
    if has_critical_failure:
        print("[!] Setup check detected one or more critical issues above.")
        print("    Please resolve them before running Jarvis.")
        return 1
    else:
        print("[*] All critical checks passed! Jarvis is ready to run.")
        print("    Launch with: python main.py")
        return 0


if __name__ == "__main__":
    sys.exit(main())
