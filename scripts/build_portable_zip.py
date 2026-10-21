"""Build script to create the fully portable Jarvis Windows distribution and ZIP archive.

Usage:
    python scripts/build_portable_zip.py
    python scripts/build_portable_zip.py --clean
"""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zipfile

ROOT_DIR = Path(__file__).resolve().parent.parent
SPEC_FILE = ROOT_DIR / "jarvis.spec"
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"
RELEASE_DIR = DIST_DIR / "Jarvis-Portable-Windows"
ZIP_FILE = DIST_DIR / "Jarvis-Portable-Windows.zip"


def check_prerequisites() -> None:
    """Verifies build environment and required tools."""
    try:
        import PyInstaller
        print(f"[OK] PyInstaller {PyInstaller.__version__} detected.")
    except ImportError:
        print("[ERROR] PyInstaller is not installed. Run: python -m pip install pyinstaller")
        sys.exit(1)

    if not SPEC_FILE.exists():
        print(f"[ERROR] Spec file not found at: {SPEC_FILE}")
        sys.exit(1)


def clean_build_artifacts() -> None:
    """Cleans temporary build files."""
    print("Cleaning previous build artifacts...")
    for directory in (BUILD_DIR, RELEASE_DIR):
        if directory.exists():
            try:
                shutil.rmtree(directory)
                print(f" - Removed: {directory}")
            except Exception as e:
                print(f" - Warning: Could not remove {directory}: {e}")
    if ZIP_FILE.exists():
        try:
            ZIP_FILE.unlink()
            print(f" - Removed: {ZIP_FILE}")
        except Exception as e:
            print(f" - Warning: Could not remove {ZIP_FILE}: {e}")


def build_onedir() -> None:
    """Runs PyInstaller using jarvis.spec to produce onedir distribution."""
    print(f"\nBuilding portable onedir application with PyInstaller from {SPEC_FILE.name}...")
    t0 = time.perf_counter()

    if RELEASE_DIR.exists():
        try:
            shutil.rmtree(RELEASE_DIR)
            time.sleep(1.0)
        except Exception as e:
            print(f" - Note during pre-clean: {e}")

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", str(SPEC_FILE)]
    result = subprocess.run(cmd, cwd=str(ROOT_DIR))

    elapsed = time.perf_counter() - t0
    if result.returncode != 0:
        print(f"\n[FAIL] PyInstaller build failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    print(f"[OK] PyInstaller build completed in {elapsed:.1f}s")


def add_release_documents() -> None:
    """Generates portable launch instructions and third-party license notices."""
    print("\nAdding release documents and metadata...")

    # 1. README_PORTABLE.txt
    readme_text = """======================================================================
 JARVIS - VOICE-CONTROLLED AI ASSISTANT FOR WINDOWS 11 (PORTABLE)
======================================================================

QUICK START:
1. Extract this entire ZIP to any folder on your PC (e.g. C:\\Tools\\Jarvis).
2. Double-click `jarvis.exe` to launch Jarvis.
   - You do NOT need Python, pip, or any virtual environment installed!
   - Everything needed to run is bundled right inside this folder.

FIRST RUN & CONFIGURATION:
- When launched, the Jarvis floating pill appears near the bottom of your screen.
- Right-click the floating pill or the system tray icon and click "Settings...".
- Or launch directly into settings: `jarvis.exe --settings`
- All settings and credentials (API keys) are securely stored in your personal
  Windows DPAPI vault at:
  %LOCALAPPDATA%\\Jarvis\\vault.bin
- No .env file editing is ever required.

AI MODEL LOCATIONS:
Your local models are kept safely in your Windows user profile so they persist
across application updates:
- Faster-Whisper STT: %LOCALAPPDATA%\\Jarvis\\models\\stt
- Piper Neural TTS:   %LOCALAPPDATA%\\Jarvis\\models\\piper
- Local LLMs (GGUF):  %LOCALAPPDATA%\\Jarvis\\models\\llm

CONTROLS & SHORTCUTS:
- Wake phrase: "Hey Jarvis"
- Emergency Kill Switch: Ctrl + Alt + J
- Move Pop-up Card / Floating Pill: Click and drag anywhere with your mouse
- Reset Position: Double-click the card or floating pill
- Close Answer Card: Esc
- Copy Answer: Ctrl + C

======================================================================
"""
    readme_dst = RELEASE_DIR / "README_PORTABLE.txt"
    readme_dst.write_text(readme_text, encoding="utf-8")
    print(f" - Created: {readme_dst}")

    # 2. LICENSE.txt
    license_text = """======================================================================
 JARVIS - THIRD-PARTY SOFTWARE LICENSES & ATTRIBUTIONS
======================================================================

Jarvis is distributed under the MIT License.
Copyright (c) 2026 Jarvis Assistant Contributors.

This distribution bundles software and models licensed under open-source terms:

1. Python Software Foundation License (Python Runtime)
   https://docs.python.org/3/license.html

2. PySide6 / Qt 6 (LGPLv3)
   https://www.qt.io/licensing/

3. CTranslate2 (MIT License)
   Copyright (c) 2020 OpenNMT

4. Faster-Whisper (MIT License)
   Copyright (c) 2023 Guillaume Klein

5. Piper TTS (MIT License)
   Copyright (c) 2023 Michael Hansen

6. OpenWakeWord (Apache License 2.0)
   Copyright (c) 2023 David Scripka

7. Satoshi Font Family (Indian Type Foundry / Fontshare Free License)
   https://www.fontshare.com/licenses/itf-free-font-license

8. PortAudio / SoundDevice (MIT License)
   Copyright (c) 2015 Matthias Geier

======================================================================
"""
    license_dst = RELEASE_DIR / "LICENSE.txt"
    license_dst.write_text(license_text, encoding="utf-8")
    print(f" - Created: {license_dst}")


def package_to_zip() -> None:
    """Packages the onedir release folder into a standalone ZIP archive."""
    print(f"\nCompressing release into {ZIP_FILE.name}...")
    t0 = time.perf_counter()

    if not RELEASE_DIR.exists():
        print(f"[ERROR] Release directory does not exist: {RELEASE_DIR}")
        sys.exit(1)

    # Purge any local .env file so portable distribution is purely in-app configured
    release_env = RELEASE_DIR / ".env"
    if release_env.exists():
        try:
            release_env.unlink()
            print(f" - Removed .env from release folder ({release_env})")
        except Exception as e:
            print(f" - Warning: Could not remove {release_env}: {e}")

    with zipfile.ZipFile(ZIP_FILE, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zip_out:
        for file_path in RELEASE_DIR.rglob("*"):
            if file_path.is_file():
                if file_path.name == ".env":
                    continue
                arcname = file_path.relative_to(DIST_DIR)
                zip_out.write(file_path, arcname)

    elapsed = time.perf_counter() - t0
    zip_size_mb = ZIP_FILE.stat().st_size / (1024 * 1024)
    print(f"[OK] ZIP archive created in {elapsed:.1f}s ({zip_size_mb:.1f} MB)")


def verify_release() -> None:
    """Runs verification on the generated executable."""
    exe_path = RELEASE_DIR / "jarvis.exe"
    if not exe_path.exists():
        print(f"[ERROR] Expected executable not found at: {exe_path}")
        sys.exit(1)

    print(f"\n[OK] Verifying executable: {exe_path}...")
    try:
        test_run = subprocess.run(
            [str(exe_path), "--config"],
            cwd=str(RELEASE_DIR),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if test_run.returncode == 0:
            print("[OK] Executable self-test passed successfully!")
            print(test_run.stdout.strip())
        else:
            print(f"[WARNING] Test verification exited with code {test_run.returncode}")
            if test_run.stderr:
                print(test_run.stderr.strip())
    except Exception as e:
        print(f"[WARNING] Could not run executable test verification: {e}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build portable Jarvis Windows ZIP distribution.")
    parser.add_argument("--clean", action="store_true", help="Clean build directories before compiling.")
    parser.add_argument("--skip-build", action="store_true", help="Skip PyInstaller build and package existing dist folder.")
    args = parser.parse_args()

    print("=" * 68)
    print(" Jarvis AI Assistant - Portable Windows Packaging Builder")
    print("=" * 68)

    check_prerequisites()

    if args.clean:
        clean_build_artifacts()

    if not args.skip_build:
        build_onedir()

    add_release_documents()
    package_to_zip()
    verify_release()

    print("\n" + "=" * 68)
    print(" Portable Distribution Packaging Complete!")
    print(f" Directory: {RELEASE_DIR}")
    print(f" Archive:   {ZIP_FILE}")
    print("=" * 68)


if __name__ == "__main__":
    main()
