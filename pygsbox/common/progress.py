"""Progress reporting callbacks for long-running operations.

Usage:
    from pygsbox.common.progress import Progress, PHASE_READ, PHASE_WRITE

    def my_cb(phase: int, current: int, total: int) -> None:
        pct = current / max(total, 1) * 100
        phases = {0: 'Read', 2: 'Write', 3: 'K-Means', 4: 'Cut'}
        print(f'[{phases.get(phase, str(phase))}] {pct:.0f}%', end='\r')

    progress = Progress(callback=my_cb)
    with progress:
        data = spz.read_spz('file.spz')
"""
import sys
import time
from typing import Callable, Optional

PHASE_JOIN = -1
PHASE_READ = 0
PHASE_WRITE = 2
PHASE_KMEANS = 3
PHASE_CUT = 4

_PHASE_NAMES = {
    PHASE_JOIN: "Join",
    PHASE_READ: "Read",
    PHASE_WRITE: "Write",
    PHASE_KMEANS: "K-Means",
    PHASE_CUT: "Cut",
}

ProgressCallback = Callable[[int, int, int], None]


class Progress:
    """Manages progress reporting via an optional callback."""

    _instance: Optional['Progress'] = None

    def __init__(self, callback: Optional[ProgressCallback] = None,
                 throttle_ms: int = 100):
        self.callback = callback
        self.throttle_ms = throttle_ms
        self._last_report = 0.0
        self._entered = False
        self._prev_instance: Optional['Progress'] = None

    def __enter__(self) -> 'Progress':
        self._prev_instance = Progress._instance
        Progress._instance = self
        self._entered = True
        return self

    def __exit__(self, *args):
        Progress._instance = self._prev_instance
        self._entered = False

    @staticmethod
    def report(phase: int, current: int, total: int):
        inst = Progress._instance
        if inst is None or inst.callback is None:
            return
        now = time.perf_counter()
        if now - inst._last_report < inst.throttle_ms / 1000.0:
            return
        inst._last_report = now
        try:
            inst.callback(phase, current, total)
        except Exception:
            pass

    @staticmethod
    def done(phase: int, total: int):
        Progress.report(phase, total, total)


def default_callback(phase: int, current: int, total: int) -> None:
    """A simple text progress callback suitable for CLI use."""
    pct = current / max(total, 1) * 100
    name = _PHASE_NAMES.get(phase, f"P{phase}")
    bar_len = 30
    filled = int(bar_len * current / max(total, 1))
    bar = '#' * filled + '-' * (bar_len - filled)
    sys.stderr.write(f'\r  [{name:<6}] [{bar}] {pct:5.1f}%')
    if current >= total:
        sys.stderr.write('\n')
    sys.stderr.flush()
