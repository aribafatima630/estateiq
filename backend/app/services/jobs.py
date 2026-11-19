from __future__ import annotations

import threading
from collections.abc import Callable


class JobRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.running = False

    def start(self, target: Callable[[], None]) -> bool:
        with self._lock:
            if self.running:
                return False
            self.running = True

        def wrap() -> None:
            try:
                target()
            finally:
                with self._lock:
                    self.running = False

        threading.Thread(target=wrap, daemon=True).start()
        return True
