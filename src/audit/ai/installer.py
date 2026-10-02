"""The one background job that sets up the AI pack, with pause and resume.

Steps: get the Ollama program (unless one already runs on this computer),
start it, then download the tier's text and vision models through Ollama's
own ``/api/pull``. Pausing stops the transfer; both the program download and
Ollama keep what they already have, so starting again carries on.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from typing import Literal

import httpx
from pydantic import BaseModel

from audit.ai.catalog import Catalog, Tier
from audit.ai.runtime import OllamaRuntime, PausedError, RuntimeSetupError, system_ollama
from audit.ai.state import SYSTEM_OLLAMA_URL, AIConfig

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


def pull_model(
    base_url: str,
    tag: str,
    progress: Callable[[int, int], None],
    cancel: threading.Event,
    client: httpx.Client | None = None,
) -> None:
    """Stream ``/api/pull`` for one model, reporting summed layer progress."""
    layers: dict[str, tuple[int, int]] = {}
    own = client is None
    http = client or httpx.Client(timeout=httpx.Timeout(30.0, read=None))
    try:
        with http.stream(
            "POST", f"{base_url.rstrip('/')}/api/pull", json={"model": tag, "stream": True}
        ) as response:
            if response.status_code != 200:
                response.read()
                raise RuntimeSetupError(
                    f"Ollama could not download {tag} (HTTP {response.status_code})."
                )
            for line in response.iter_lines():
                if cancel.is_set():
                    raise PausedError
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("error"):
                    raise RuntimeSetupError(f"Ollama could not download {tag}: {event['error']}")
                digest = event.get("digest")
                if digest and event.get("total"):
                    layers[digest] = (int(event.get("completed") or 0), int(event["total"]))
                    progress(sum(d for d, _ in layers.values()), sum(t for _, t in layers.values()))
                if event.get("status") == "success":
                    return
        raise RuntimeSetupError(f"The download of {tag} ended before it finished.")
    except httpx.HTTPError as exc:
        raise RuntimeSetupError(f"The download of {tag} stopped: {exc}") from exc
    finally:
        if own:
            http.close()


class Installer:
    def __init__(
        self,
        catalog: Catalog,
        runtime: OllamaRuntime,
        on_ready: Callable[[AIConfig], None],
        *,
        find_system: Callable[[], str | None] = system_ollama,
        pull: Callable[..., None] = pull_model,
    ) -> None:
        self.catalog = catalog
        self.runtime = runtime
        self.on_ready = on_ready
        self.find_system = find_system
        self.pull = pull
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
            self._cancel = threading.Event()
            system = self.find_system()
            program = 0 if system else self.runtime.download_remaining()
            self.status = InstallStatus(
                state="running",
                tier=tier.id,
                total_bytes=program + tier.text.size + tier.vision.size,
            )
            self._thread = threading.Thread(
                target=self._run,
                args=(tier, system, self._cancel),
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

    def _run(self, tier: Tier, system: str | None, cancel: threading.Event) -> None:
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
            if system:
                source, base_url, version = "system", SYSTEM_OLLAMA_URL, system
            else:
                report = step("program")
                before = self.runtime.download_remaining()
                self.runtime.download(report, cancel)
                base += before
                if cancel.is_set():
                    raise PausedError
                step("starting")
                base_url = self.runtime.start()
                source, version = "private", self.catalog.ollama.version
            for name, model in (("text_model", tier.text), ("vision_model", tier.vision)):
                report = step(name)  # type: ignore[arg-type]
                self.pull(base_url, model.tag, report, cancel)
                base += model.size
                self.status.done_bytes = min(base, self.status.total_bytes)
            step("finishing")
            config = AIConfig(
                source=source,  # type: ignore[arg-type]
                base_url=base_url,
                tier=tier.id,
                text_model=tier.text.tag,
                vision_model=tier.vision.tag,
                ollama_version=version,
            )
            self.on_ready(config)
            self.status.done_bytes = self.status.total_bytes
            self.status.state = "done"
            self.status.step = None
        except PausedError:
            self.status.state = "paused"
        except RuntimeSetupError as exc:
            self.status.state = "failed"
            self.status.error = str(exc)
        except Exception as exc:
            self.status.state = "failed"
            self.status.error = f"AI setup stopped unexpectedly: {exc}"
