"""Build script to compile Jarvis into a standalone Windows executable.

Usage:
    python scripts/build_exe.py
    python scripts/build_exe.py --clean
"""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT_DIR = Path(__file__).resolve().parent.parent
SPEC_FILE = ROOT_DIR / "jarvis.spec"
DIST_DIR = ROOT_DIR / "dist"
BUILD_DIR = ROOT_DIR / "build"


def check_prerequisites() -> None:
    """Verifies that required build tools are installed."""
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
    """Removes previous build and dist directories."""
    print("Cleaning previous build artifacts...")
    for directory in (BUILD_DIR, DIST_DIR):
        if directory.exists():
            try:
                shutil.rmtree(directory)
                print(f" - Removed: {directory}")
            except Exception as e:
                print(f" - Warning: Could not remove {directory}: {e}")


def copy_runtime_assets() -> None:
    """Copies configuration and voice models adjacent to the executable."""
    DIST_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Copy config.yaml
    cfg_src = ROOT_DIR / "config.yaml"
    cfg_dst = DIST_DIR / "config.yaml"
    if cfg_src.exists() and not cfg_dst.exists():
        shutil.copy2(cfg_src, cfg_dst)
        print(f" - Copied default config.yaml -> {cfg_dst}")

    # 2. Copy .env.example
    env_ex_src = ROOT_DIR / ".env.example"
    env_ex_dst = DIST_DIR / ".env.example"
    if env_ex_src.exists() and not env_ex_dst.exists():
        shutil.copy2(env_ex_src, env_ex_dst)
        print(f" - Copied .env.example -> {env_ex_dst}")


    # 4. Copy data/piper_voices if downloaded
    voices_src = ROOT_DIR / "data" / "piper_voices"
    voices_dst = DIST_DIR / "data" / "piper_voices"
    if voices_src.exists() and not voices_dst.exists():
        shutil.copytree(voices_src, voices_dst)
        print(f" - Copied local Piper neural voice models -> {voices_dst}")


def build_executable() -> None:
    """Invokes PyInstaller using jarvis.spec."""
    print(f"\nBuilding standalone executable with PyInstaller from {SPEC_FILE.name}...")
    t0 = time.perf_counter()

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", str(SPEC_FILE)]
    result = subprocess.run(cmd, cwd=str(ROOT_DIR))

    elapsed = time.perf_counter() - t0
    if result.returncode != 0:
        print(f"\n[FAIL] PyInstaller build failed with exit code {result.returncode}")
        sys.exit(result.returncode)

    print(f"[OK] Build completed in {elapsed:.1f}s")


def verify_executable() -> None:
    """Verifies that the generated executable runs and outputs configuration."""
    exe_path = DIST_DIR / "jarvis.exe"
    if not exe_path.exists():
        print(f"[ERROR] Expected executable not found at: {exe_path}")
        sys.exit(1)

    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"\n[OK] Generated executable: {exe_path} ({size_mb:.1f} MB)")

    # Run quick test verification
    print("\nRunning test verification (dist/jarvis.exe --config)...")
    try:
        test_run = subprocess.run(
            [str(exe_path), "--config"],
            cwd=str(DIST_DIR),
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
    parser = argparse.ArgumentParser(description="Build standalone Jarvis Windows executable.")
    parser.add_argument("--clean", action="store_true", help="Clean build directories before compiling.")
    args = parser.parse_args()

    print("=" * 60)
    print(" Jarvis AI Assistant - Executable Builder")
    print("=" * 60)

    check_prerequisites()

    if args.clean:
        clean_build_artifacts()

    build_executable()
    copy_runtime_assets()
    verify_executable()

    print("\n" + "=" * 60)
    print(" Build Complete!")
    print(" Your standalone assistant is located at:")
    print(f"   {DIST_DIR / 'jarvis.exe'}")
    print("\n Usage:")
    print("   1. Run in background / system tray: dist\\jarvis.exe")
    print("   2. Run in CLI text mode:           dist\\jarvis.exe --text")
    print("   3. Run diagnostics:                dist\\jarvis.exe --check-setup")
    print("   4. Rebuild anytime with:           python scripts/build_exe.py")
    print("=" * 60)


if __name__ == "__main__":
    main()
