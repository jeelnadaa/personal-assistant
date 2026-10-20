"""Hardware and GPU diagnostic inspection for Jarvis."""

import os
from typing import Any
import psutil

from jarvis.logger import logger


def get_hardware_diagnostics() -> dict[str, Any]:
    """Inspects host hardware: GPU, VRAM, RAM, CPU, and CUDA execution readiness.

    Returns:
        Dictionary containing hardware capability flags, descriptions, and diagnostics.
    """
    diag: dict[str, Any] = {
        "has_cuda": False,
        "cuda_device_name": "None",
        "cuda_device_count": 0,
        "vram_gb": 0.0,
        "system_ram_gb": 0.0,
        "cpu_count": os.cpu_count() or 1,
        "cpu_percent": 0.0,
        "status_summary": "CPU Only",
    }

    # 1. System RAM
    try:
        mem = psutil.virtual_memory()
        diag["system_ram_gb"] = round(mem.total / (1024 ** 3), 1)
        diag["cpu_percent"] = psutil.cpu_percent(interval=None)
    except Exception as exc:
        logger.debug("Failed querying system RAM: %s", exc)

    # 2. CUDA detection via ctranslate2 (used by faster-whisper)
    try:
        import ctranslate2
        cuda_count = ctranslate2.get_cuda_device_count()
        if cuda_count > 0:
            diag["has_cuda"] = True
            diag["cuda_device_count"] = cuda_count
    except Exception as exc:
        logger.debug("ctranslate2 CUDA query exception: %s", exc)

    # 3. GPU details via Windows WMI or torch if available
    gpu_name = ""
    vram_mb = 0

    try:
        import wmi
        w = wmi.WMI()
        for controller in w.Win32_VideoController():
            name = getattr(controller, "Name", "")
            if name and any(brand in name.lower() for brand in ("nvidia", "geforce", "quadro", "rtx", "gtx")):
                gpu_name = name
                ram = getattr(controller, "AdapterRAM", 0)
                if ram:
                    vram_mb = int(ram) // (1024 * 1024)
                break
            elif not gpu_name and name:
                gpu_name = name
    except Exception as exc:
        logger.debug("WMI GPU query error: %s", exc)

    if gpu_name:
        diag["cuda_device_name"] = gpu_name
        if vram_mb > 0:
            diag["vram_gb"] = round(vram_mb / 1024, 1)

    # Status summary
    if diag["has_cuda"]:
        name_str = diag["cuda_device_name"] if diag["cuda_device_name"] != "None" else "NVIDIA GPU"
        vram_str = f" ({diag['vram_gb']} GB VRAM)" if diag["vram_gb"] > 0 else ""
        diag["status_summary"] = f"Active - {name_str}{vram_str}"
    elif gpu_name:
        diag["status_summary"] = f"Detected ({gpu_name}) - CPU Fallback"
    else:
        diag["status_summary"] = "CPU Only (No dedicated GPU detected)"

    return diag


def is_cuda_available() -> bool:
    """Returns True if CUDA GPU acceleration is available."""
    diag = get_hardware_diagnostics()
    return bool(diag.get("has_cuda", False))


def get_gpu_info() -> dict[str, Any]:
    """Returns GPU details dict."""
    diag = get_hardware_diagnostics()
    return {
        "cuda_available": diag.get("has_cuda", False),
        "name": diag.get("cuda_device_name", "None"),
        "vram_gb": diag.get("vram_gb", 0.0),
        "device_count": diag.get("cuda_device_count", 0),
        "summary": diag.get("status_summary", "CPU Only"),
    }


def get_system_specs() -> dict[str, Any]:
    """Returns CPU and RAM specification dict."""
    diag = get_hardware_diagnostics()
    return {
        "ram_total_gb": diag.get("system_ram_gb", 0.0),
        "cpu_cores": diag.get("cpu_count", 1),
        "cpu_percent": diag.get("cpu_percent", 0.0),
    }
