"""The one background job that sets up the AI pack, with pause and resume.

Steps: download the private program and checksum-verified models on the host,
then start the offline sandboxed service. No system Ollama is managed.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from audit.ai.catalog import Catalog, Tier
from audit.ai.downloader import download_model
from audit.ai.runtime import OllamaRuntime, PausedError, RuntimeSetupError, system_ollama
from audit.ai.sandbox import IsolationError
from audit.ai.state import AIConfig

InstallState = Literal["idle", "running", "paused", "failed", "done"]
InstallStep = Literal["program", "starting", "text_model", "vision_model", "finishing"]


class InstallStatus(BaseModel):
    state: InstallState = "idle"
    tier: str | None = None
    step: InstallStep | None = None
    step_done_bytes: int = 0
    step_total_bytes: int = 0
    done_bytes: int = 0
    total_bytes: int = 0
    error: str | None = None


class Installer:
    def __init__(
        self,
        catalog: Catalog,
        runtime: OllamaRuntime,
        on_ready: Callable[[AIConfig], None],
        *,
        find_system: Callable[[], str | None] = system_ollama,
        pull: Callable[..., None] = download_model,
        on_stopped: Callable[[], None] = lambda: None,
    ) -> None:
        self.catalog = catalog
        self.runtime = runtime
        self.on_ready = on_ready
        self.find_system = find_system
        self.pull = pull
        self.on_stopped = on_stopped
        self.status = InstallStatus()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, tier: Tier) -> InstallStatus:
        with self._lock:
            if self.running:
                return self.status
            self.runtime.require_isolation()
            self._cancel = threading.Event()
            program = self.runtime.download_remaining()
            self.status = InstallStatus(
                state="running",
                tier=tier.id,
                total_bytes=program + tier.text.size + tier.vision.size,
            )
            self._thread = threading.Thread(
                target=self._run,
                args=(tier, self._cancel),
                daemon=True,
                name="axcess-ai-install",
            )
            self._thread.start()
            return self.status

    def pause(self) -> InstallStatus:
        self._cancel.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=15)
        return self.status

    def reset(self) -> None:
        self.pause()
        self.status = InstallStatus()

    def _run(self, tier: Tier, cancel: threading.Event) -> None:
        base = 0

        def step(name: InstallStep) -> Callable[[int, int], None]:
            self.status.step = name
            self.status.step_done_bytes = 0
            self.status.step_total_bytes = 0

            def report(done: int, total: int) -> None:
                self.status.step_done_bytes = done
                self.status.step_total_bytes = total
                self.status.done_bytes = min(base + done, self.status.total_bytes)

            return report

        try:
            report = step("program")
            before = self.runtime.download_remaining()
            self.runtime.download(report, cancel)
            base += before
            if cancel.is_set():
                raise PausedError
            for name, model in (("text_model", tier.text), ("vision_model", tier.vision)):
                report = step(name)  # type: ignore[arg-type]
                self.pull(self.runtime.models_dir, model.tag, report, cancel)
                base += model.size
                self.status.done_bytes = min(base, self.status.total_bytes)
            step("starting")
            base_url = self.runtime.start()
            step("finishing")
            config = AIConfig(
                source="private",
                base_url=base_url,
                tier=tier.id,
                text_model=tier.text.tag,
                vision_model=tier.vision.tag,
                ollama_version=self.catalog.ollama.version,
            )
            self.on_ready(config)
            self.status.done_bytes = self.status.total_bytes
            self.status.state = "done"
            self.status.step = None
        except PausedError:
            self.status.state = "paused"
        except (RuntimeSetupError, IsolationError) as exc:
            self.status.state = "failed"
            self.status.error = str(exc)
        except Exception as exc:
            self.status.state = "failed"
            self.status.error = f"AI setup stopped unexpectedly: {exc}"
        finally:
            if self.status.state in {"paused", "failed"}:
                self.on_stopped()
