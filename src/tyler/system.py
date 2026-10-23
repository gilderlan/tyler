"""Uso de recursos do Mac (CPU, RAM, temperatura) e modo econômico."""

import ctypes
import ctypes.util
import os
import subprocess
import time
from dataclasses import dataclass

import cv2
import psutil

# Limite de threads para OpenCV, ffmpeg e ONNX Runtime; None = usar todos os núcleos
THREADS: int | None = None
ECO = False

THERMAL_STATES = ("normal", "morno", "quente", "crítico")  # NSProcessInfoThermalState 0..3


@dataclass
class Sample:
    cpu: float  # % somado do processo e dos filhos (100% = 1 núcleo)
    ram: int  # bytes
    cores: int
    thermal: str | None


class Monitor:
    """Mede CPU e RAM do Tyler e dos processos filhos (ffmpeg), no máximo 1 vez por segundo."""

    INTERVAL = 1.0

    def __init__(self):
        self._me = psutil.Process()
        self._procs: dict[int, psutil.Process] = {}
        self._cached: Sample | None = None
        self._at = 0.0
        self.cores = psutil.cpu_count() or 1

    def sample(self) -> Sample:
        now = time.monotonic()
        if self._cached is not None and now - self._at < self.INTERVAL:
            return self._cached
        self._at = now
        cpu = 0.0
        ram = 0
        alive = set()
        for proc in [self._me, *self._me.children(recursive=True)]:
            tracked = self._procs.setdefault(proc.pid, proc)  # cpu_percent compara com a leitura anterior
            try:
                cpu += tracked.cpu_percent(None)
                ram += tracked.memory_info().rss
                alive.add(proc.pid)
            except psutil.Error:
                pass
        self._procs = {pid: p for pid, p in self._procs.items() if pid in alive}
        self._cached = Sample(cpu, ram, self.cores, thermal_state())
        return self._cached


def thermal_state() -> str | None:
    """Estado térmico do macOS (o mesmo que o sistema usa para reduzir a velocidade quando esquenta)."""
    global _thermal
    try:
        if _thermal is None:
            _thermal = _thermal_reader()
        return THERMAL_STATES[_thermal()]
    except Exception:
        return None


_thermal = None


def _thermal_reader():
    objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
    ctypes.cdll.LoadLibrary("/System/Library/Frameworks/Foundation.framework/Foundation")
    objc.objc_getClass.restype = ctypes.c_void_p
    objc.objc_getClass.argtypes = [ctypes.c_char_p]
    objc.sel_registerName.restype = ctypes.c_void_p
    objc.sel_registerName.argtypes = [ctypes.c_char_p]
    addr = ctypes.cast(objc.objc_msgSend, ctypes.c_void_p).value
    send_ptr = ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p)(addr)
    send_long = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p)(addr)
    info = send_ptr(objc.objc_getClass(b"NSProcessInfo"), objc.sel_registerName(b"processInfo"))
    selector = objc.sel_registerName(b"thermalState")
    return lambda: send_long(info, selector)


def efficiency_cores() -> int:
    """Número de núcleos de eficiência (Apple Silicon); metade dos núcleos em outros Macs."""
    try:
        out = subprocess.run(["sysctl", "-n", "hw.perflevel1.physicalcpu"], capture_output=True, text=True, check=True)
        return max(1, int(out.stdout))
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError):
        return max(1, (os.cpu_count() or 2) // 2)


def enable_eco() -> None:
    """Roda em segundo plano nos núcleos de eficiência, com menos threads: mais lento, mas esquenta menos.

    A política de segundo plano do macOS é herdada pelos processos filhos (ffmpeg).
    """
    global THREADS, ECO
    ECO = True
    THREADS = efficiency_cores()
    cv2.setNumThreads(THREADS)
    try:
        os.setpriority(os.PRIO_DARWIN_PROCESS, 0, os.PRIO_DARWIN_BG)
    except (AttributeError, OSError):
        os.nice(10)  # fora do macOS: só baixa a prioridade
