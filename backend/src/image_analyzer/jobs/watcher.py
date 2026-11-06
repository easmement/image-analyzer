"""Watch mode: when files in a watched library change, queue an incremental scan.

Events are debounced: a copy of 500 photos fires thousands of events, and we want one scan
after it settles, not one per file. If a scan is already running when the timer fires, the
timer re-arms and tries again later.

Uses inotify (via watchdog). inotify events don't cross WSL's 9P bridge, so folders on Windows
drives (/mnt/<letter>/...) can't be watched; rescan those manually.
"""

import threading
from pathlib import Path, PurePosixPath

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer
from watchdog.observers.api import BaseObserver

from image_analyzer.jobs.runner import JobConflict, jobs
from image_analyzer.pipeline.decode import SUPPORTED_EXTS

DEBOUNCE_S = 5.0


def can_watch(root: Path) -> str | None:
    """None if root can be watched, else the reason it can't."""
    parts = root.resolve().parts
    if len(parts) >= 3 and parts[1] == "mnt" and len(parts[2]) == 1:
        return "Windows drives (/mnt/…) can't be watched under WSL: file events don't cross the 9P bridge."
    return None


class _Handler(FileSystemEventHandler):
    def __init__(self, on_change):
        self.on_change = on_change

    def on_any_event(self, event: FileSystemEvent) -> None:
        if event.event_type in ("opened", "closed_no_write"):
            return  # reads don't change anything
        paths = [event.src_path, getattr(event, "dest_path", "")]
        for p in paths:
            name = PurePosixPath(str(p)).name
            if name and not name.startswith(".") and (event.is_directory or PurePosixPath(name).suffix.lower() in SUPPORTED_EXTS):
                self.on_change()
                return


class Watcher:
    def __init__(self, start_scan, is_running) -> None:
        self._start_scan = start_scan  # (library_id, root) -> None
        self._is_running = is_running  # (library_id) -> bool
        self._observer: BaseObserver | None = None
        self._watches: dict[int, object] = {}
        self._timers: dict[int, threading.Timer] = {}
        self._lock = threading.Lock()

    def _ensure_observer(self) -> BaseObserver:
        if self._observer is None:
            observer = Observer()
            observer.daemon = True
            observer.start()
            self._observer = observer
        return self._observer

    def watch(self, library_id: int, root: Path) -> None:
        with self._lock:
            if library_id in self._watches:
                return
            handler = _Handler(lambda: self._changed(library_id, root))
            self._watches[library_id] = self._ensure_observer().schedule(handler, str(root), recursive=True)

    def unwatch(self, library_id: int) -> None:
        with self._lock:
            if (w := self._watches.pop(library_id, None)) is not None and self._observer:
                self._observer.unschedule(w)  # type: ignore[arg-type]
            if (t := self._timers.pop(library_id, None)) is not None:
                t.cancel()

    def watching(self, library_id: int) -> bool:
        return library_id in self._watches

    def _changed(self, library_id: int, root: Path) -> None:
        with self._lock:
            if (t := self._timers.get(library_id)) is not None:
                t.cancel()  # still changing: restart the quiet period
            t = threading.Timer(DEBOUNCE_S, self._fire, args=(library_id, root))
            t.daemon = True
            self._timers[library_id] = t
            t.start()

    def _fire(self, library_id: int, root: Path) -> None:
        with self._lock:
            self._timers.pop(library_id, None)
            if library_id not in self._watches:
                return
        if self._is_running(library_id):
            self._changed(library_id, root)  # a scan is running; check again after it
        else:
            self._start_scan(library_id, root)

    def stop(self) -> None:
        with self._lock:
            for t in self._timers.values():
                t.cancel()
            self._timers.clear()
            self._watches.clear()
            if self._observer:
                self._observer.stop()
                self._observer = None


def _start_scan(library_id: int, root: Path) -> None:
    try:
        jobs.start_scan(library_id, root)
    except JobConflict:
        pass  # a scan started in the meantime; it'll see these changes


watcher = Watcher(start_scan=_start_scan, is_running=lambda lib: jobs.running_for(lib) is not None)
