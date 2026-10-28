"""Explicit virtual elapsed clock for async unit tests, never real measurements.

The Python 3.11 selector loop still executes every task and timeout. Only idle
timer waits advance instantly, so host scheduling/file I/O cannot invent missed
ticks in tests intended to exercise a particular publisher/collector scenario.
"""

import asyncio
import time


def install_clock_double(monkeypatch):
    clock = [0.0]

    class ClockLoop(asyncio.SelectorEventLoop):
        def time(self):
            return clock[0]

        def _run_once(self):
            if not self._ready:
                pending = [handle._when for handle in self._scheduled if not handle.cancelled()]
                if pending:
                    clock[0] = max(clock[0], min(pending))
            super()._run_once()

    def run(coroutine, *, debug=None):
        with asyncio.Runner(debug=debug, loop_factory=ClockLoop) as runner:
            return runner.run(coroutine)

    monkeypatch.setattr(time, "perf_counter", lambda: clock[0])
    monkeypatch.setattr(asyncio, "run", run)
