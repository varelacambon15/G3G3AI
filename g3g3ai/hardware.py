"""Detección del hardware y recomendación de modelo y ajustes locales.

detect(): procesador, RAM y gráficas (con su memoria). Funciona en Windows, Linux x86 y Linux ARM.
recommend(hw): qué tamaño de modelo encaja, si va en la gráfica o en el procesador, qué motor
instalar y qué ajustes usar. Es una función pura (fácil de probar con equipos inventados).

Regla general: la velocidad al generar depende de la memoria por la que pasa el modelo.
- Si el modelo cabe entero en la memoria de una gráfica dedicada, va mucho más rápido.
- En procesador, cuanto más pequeño el modelo, más rápido; los modelos MoE («A3B»: ~30B en total
  pero sólo ~3B activos por palabra) van casi tan rápido como uno de 4B con calidad de uno mayor,
  si hay RAM para cargarlos.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
GB = 1024 ** 3


def _run(cmd: list[str], timeout: int = 10) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=timeout,
                           creationflags=NO_WINDOW, stdin=subprocess.DEVNULL)
        return r.stdout if r.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _ps_json(command: str):
    """Ejecuta PowerShell y devuelve su salida JSON (siempre como lista)."""
    out = _run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command + " | ConvertTo-Json -Compress"], 20)
    try:
        data = json.loads(out) if out.strip() else []
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else [data]


# --- Procesador y RAM ----------------------------------------------------------------------
def _cpu_linux() -> dict:
    info = {"name": "", "cores": os.cpu_count() or 1, "threads": os.cpu_count() or 1, "flags": []}
    try:
        text = Path("/proc/cpuinfo").read_text(errors="replace")
    except OSError:
        return info
    names = re.findall(r"^(?:model name|Model|Hardware)\s*:\s*(.+)$", text, re.M)
    info["name"] = names[0].strip() if names else ""
    flags = re.findall(r"^(?:flags|Features)\s*:\s*(.+)$", text, re.M)
    info["flags"] = sorted(set(flags[0].split())) if flags else []
    # Núcleos físicos (x86): pares (physical id, core id) únicos
    pairs = set(re.findall(r"physical id\s*:\s*(\d+)[\s\S]*?core id\s*:\s*(\d+)", text))
    if pairs:
        info["cores"] = len(pairs)
    return info


def _cpu_windows() -> dict:
    info = {"name": platform.processor(), "cores": os.cpu_count() or 1, "threads": os.cpu_count() or 1, "flags": []}
    rows = _ps_json("Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors")
    if rows:
        info["name"] = str(rows[0].get("Name") or info["name"]).strip()
        info["cores"] = sum(int(r.get("NumberOfCores") or 0) for r in rows) or info["cores"]
        info["threads"] = sum(int(r.get("NumberOfLogicalProcessors") or 0) for r in rows) or info["threads"]
    try:  # IsProcessorFeaturePresent: 40 = AVX2, 41 = AVX-512F (Windows 10+)
        k32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        if k32.IsProcessorFeaturePresent(40):
            info["flags"].append("avx2")
        if k32.IsProcessorFeaturePresent(41):
            info["flags"].append("avx512f")
    except (AttributeError, OSError):
        pass
    return info


def _ram() -> int:
    if sys.platform == "win32":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        try:
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))  # type: ignore[attr-defined]
            return int(st.ullTotalPhys)
        except (AttributeError, OSError):
            return 0
    if sys.platform == "darwin":
        out = _run(["sysctl", "-n", "hw.memsize"])
        return int(out.strip() or 0)
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


# --- Gráficas --------------------------------------------------------------------------------
def _gpu_kind(name: str, vendor: str = "") -> tuple[str, bool]:
    """(fabricante, dedicada)."""
    n = (name + " " + vendor).lower()
    if "nvidia" in n or "geforce" in n or "quadro" in n or "rtx" in n:
        return "nvidia", True
    if "adreno" in n or "qualcomm" in n or "msm" in n:
        return "qualcomm", False
    if "intel" in n or "iris" in n or "uhd" in n:
        return "intel", "arc" in n and "graphics" not in n.split("arc")[-1][:3]
    if "amd" in n or "radeon" in n or " rx " in f" {n} " or "ati" in n:
        integrated = bool(re.search(r"radeon\(tm\) graphics|vega \d+ graphics|radeon graphics", n))
        return "amd", not integrated
    return "otra", False


def _gpus_windows() -> list[dict]:
    gpus = []
    rows = _ps_json("Get-CimInstance Win32_VideoController | Select-Object Name,AdapterRAM")
    # AdapterRAM es de 32 bits (máx. 4 GB): el registro da la cifra real
    reg = _ps_json("Get-ItemProperty -Path 'HKLM:\\SYSTEM\\ControlSet001\\Control\\Class\\"
                   "{4d36e968-e325-11ce-bfc1-08002be10318}\\0*' -ErrorAction SilentlyContinue | "
                   "Select-Object DriverDesc,'HardwareInformation.qwMemorySize'")
    real = {str(r.get("DriverDesc", "")).strip(): int(r.get("HardwareInformation.qwMemorySize") or 0) for r in reg}
    for r in rows:
        name = str(r.get("Name") or "").strip()
        if not name or "basic display" in name.lower() or "remote" in name.lower():
            continue
        vendor, dedicated = _gpu_kind(name)
        vram = real.get(name) or int(r.get("AdapterRAM") or 0)
        gpus.append({"name": name, "vendor": vendor, "dedicated": dedicated, "vram": vram if dedicated else 0})
    return gpus


def _gpus_linux() -> list[dict]:
    gpus = []
    smi = _run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"]) if shutil.which("nvidia-smi") else ""
    for line in smi.strip().splitlines():
        name, _, mem = line.rpartition(",")
        gpus.append({"name": name.strip(), "vendor": "nvidia", "dedicated": True, "vram": int(float(mem) * 1024 * 1024)})
    lspci = _run(["lspci"]) if shutil.which("lspci") else ""
    names = [l.split(": ", 1)[-1] for l in lspci.splitlines() if re.search(r"VGA|3D|Display", l)]
    for card in sorted(Path("/sys/class/drm").glob("card[0-9]")):
        dev = card / "device"
        try:
            uevent = (dev / "uevent").read_text()
        except OSError:
            continue
        driver = re.search(r"DRIVER=(\S+)", uevent)
        driver = driver.group(1) if driver else ""
        if driver == "nvidia":
            continue  # ya contada con nvidia-smi
        vendor_id = (dev / "vendor").read_text().strip() if (dev / "vendor").exists() else ""
        vram = 0
        if (dev / "mem_info_vram_total").exists():
            try:
                vram = int((dev / "mem_info_vram_total").read_text().strip())
            except ValueError:
                vram = 0
        if driver == "msm" or "adreno" in uevent.lower():
            name = "Qualcomm Adreno"
        elif vendor_id == "0x1002" or driver == "amdgpu" or driver == "radeon":
            name = next((n for n in names if re.search(r"AMD|ATI|Radeon", n)), "AMD Radeon")
        elif vendor_id == "0x8086" or driver in ("i915", "xe"):
            name = next((n for n in names if "Intel" in n), "Intel Graphics")
        else:
            continue
        vendor, dedicated = _gpu_kind(name)
        if vendor == "amd":
            dedicated = vram >= 2 * GB  # las APU tienen poca VRAM reservada
        gpus.append({"name": name, "vendor": vendor, "dedicated": dedicated, "vram": vram if dedicated else 0})
    return gpus


def _soc() -> str:
    for p in ("/proc/device-tree/model", "/sys/devices/soc0/machine"):
        try:
            v = Path(p).read_bytes().replace(b"\0", b"").decode(errors="replace").strip()
            if v:
                return v
        except OSError:
            continue
    return ""


def detect() -> dict:
    arch = platform.machine().lower()
    cpu = _cpu_windows() if sys.platform == "win32" else _cpu_linux()
    gpus = _gpus_windows() if sys.platform == "win32" else (_gpus_linux() if sys.platform.startswith("linux") else [])
    return {
        "os": sys.platform, "arch": "arm64" if arch in ("aarch64", "arm64") else ("x64" if arch in ("x86_64", "amd64") else arch),
        "cpu": cpu, "ram": _ram(), "gpus": gpus, "soc": _soc() if sys.platform.startswith("linux") else "",
        "steamos": Path("/usr/bin/steamos-readonly").exists() or "steamos" in _os_release().lower(),
    }


def _os_release() -> str:
    try:
        return Path("/etc/os-release").read_text()
    except OSError:
        return ""


# --- Recomendación -------------------------------------------------------------------------
# Tamaños orientativos en Q4_K_M (modelo + algo de margen para el contexto)
TIERS = [
    # (clave, nombre, memoria necesaria en GB, búsquedas sugeridas)
    ("4b", "3–4B", 3.5, ["qwen 4b gguf", "gemma 4b gguf"]),
    ("8b", "7–8B", 6.0, ["qwen 8b gguf", "llama 8b instruct gguf"]),
    ("14b", "12–14B", 10.0, ["qwen 14b gguf", "gemma 12b gguf"]),
    ("moe", "MoE ~30B-A3B", 19.0, ["qwen 30b a3b gguf", "qwen a3b gguf"]),
    ("32b", "27–32B", 21.0, ["qwen 32b gguf", "gemma 27b gguf"]),
]


def _gb(n: int) -> float:
    return round(n / GB, 1)


def recommend(hw: dict) -> dict:
    ram = _gb(hw.get("ram", 0))
    cpu = hw.get("cpu", {})
    flags = set(cpu.get("flags", []))
    arm = hw.get("arch") == "arm64"
    dedicated = sorted([g for g in hw.get("gpus", []) if g.get("dedicated") and g.get("vram")],
                       key=lambda g: g["vram"], reverse=True)
    gpu = dedicated[0] if dedicated else None
    vram = _gb(gpu["vram"]) if gpu else 0.0
    integrated = next((g for g in hw.get("gpus", []) if not g.get("dedicated")), None)
    notes: list[str] = []

    # Memoria disponible para el modelo en el procesador: lo que deja el sistema (y SteamOS si es una consola)
    reserve = 3.0 if hw.get("steamos") else 4.0
    ram_free = max(ram - reserve, 0)
    cpu_tier = None
    for t in TIERS:
        if t[0] == "32b":
            continue  # un 32B denso en procesador es demasiado lento
        if t[2] <= ram_free + (1.0 if t[0] == "moe" else 0):
            cpu_tier = t
    gpu_tier = None
    for t in TIERS:
        if t[0] != "moe" and t[2] <= vram:
            gpu_tier = t

    engine = "cpu"
    if gpu_tier and (not cpu_tier or TIERS.index(gpu_tier) >= TIERS.index(cpu_tier) or gpu_tier[0] in ("8b", "14b", "32b")):
        main, where, gpu_layers = gpu_tier, "gpu", 99
        engine = "vulkan"  # funciona con NVIDIA, AMD e Intel; es la variante que ofrece el instalador del motor
    elif gpu and cpu_tier and cpu_tier[0] in ("8b", "14b") and vram >= 3.5:
        main, where = cpu_tier, "mixto"
        gpu_layers = max(1, int(32 * min(1.0, (vram - 1.0) / cpu_tier[2])))
        engine = "vulkan"
    else:
        main, where, gpu_layers = cpu_tier or TIERS[0], "cpu", 0
        if not cpu_tier:
            notes.append("Hay poca RAM libre: usa modelos de 1–3B o una API.")

    fast = None  # segundo modelo rápido en gráfica cuando el principal va en procesador
    if where != "gpu" and gpu_tier:
        fast = gpu_tier

    ctx = 8192
    extra = ""
    if where == "gpu" and gpu_tier and vram - gpu_tier[2] < 1.0:
        extra = "--cache-type-k q8_0 --cache-type-v q8_0"
        ctx = 4096 if vram < 5 else 8192
    if main[0] == "moe":
        notes.append("Los modelos MoE caben justos: cierra el navegador y otros programas pesados al usarlos.")

    threads = max(1, int(cpu.get("cores") or 1))
    if not arm and "avx2" not in flags and flags:
        notes.append("El procesador no tiene AVX2 (Xeon/Core antiguo): lo que vaya por CPU será lento; "
                     "mejor que el modelo quepa entero en la gráfica o usar una API.")
    if "avx512f" in flags:
        notes.append("El procesador tiene AVX-512, que llama.cpp aprovecha.")
    if arm and {"asimddp", "i8mm"} & flags:
        notes.append("CPU ARM con dotprod/i8mm: compila llama.cpp en el propio equipo (./install.sh) para aprovecharlas.")
    if integrated and integrated["vendor"] == "intel" and where == "cpu" and not arm:
        notes.append("Tiene gráfica Intel integrada: prueba también el motor Vulkan; puede acelerar la lectura del texto.")
    if integrated and integrated["vendor"] == "qualcomm":
        notes.append("Gráfica Adreno: el motor Vulkan (./install.sh --vulkan) es experimental; mide antes de cambiar.")
    if gpu and gpu["vendor"] == "amd":
        notes.append("Gráfica AMD: usa el motor Vulkan (las Radeon antiguas como la RX 580 no tienen ROCm).")

    images = None
    if gpu and vram >= 4:
        images = "Esta gráfica puede generar imágenes en local con SD Turbo / SD 1.5 a 512 px (motor de imágenes Vulkan/CUDA)."
    elif arm or ram < 12:
        images = "Generar imágenes en local será muy lento aquí: mejor por API o desde un equipo con gráfica."

    vision = ("gemma 4b gguf" if main[0] == "4b" else "qwen vl gguf")
    return {
        "summary": {
            "cpu": cpu.get("name") or hw.get("soc") or "Procesador", "cores": cpu.get("cores"), "threads": cpu.get("threads"),
            "ram_gb": ram, "gpu": gpu["name"] if gpu else (integrated["name"] if integrated else "ninguna"),
            "vram_gb": vram, "arch": hw.get("arch"), "soc": hw.get("soc"),
            # memoria que puede ocupar un modelo: la de la gráfica dedicada o la RAM que deja libre el sistema
            "budget_gb": round(max(vram - 0.5, ram_free), 1),
        },
        "main": {"tier": main[1], "where": where, "searches": main[3]},
        "fast": {"tier": fast[1], "searches": fast[3]} if fast else None,
        "engine": engine,
        "settings": {"llama_ctx": ctx, "llama_threads": threads, "llama_gpu_layers": gpu_layers, "llama_extra_args": extra},
        "quant": "Q4_K_M",
        "vision_search": vision,
        "images": images,
        "notes": notes,
    }
