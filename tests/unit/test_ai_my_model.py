"""Use your own model: GGUF files copied in and run by the private service."""

from __future__ import annotations

import struct
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from audit.ai import custom
from audit.ai.downloader import file_path, model_present
from audit.ai.state import AIConfig


@pytest.fixture(autouse=True)
def _no_disk_reserve(monkeypatch: pytest.MonkeyPatch) -> None:
    """The copy keeps 3 GB of disk free; test files are tiny and /tmp may be small."""
    monkeypatch.setattr(custom, "DISK_MARGIN", 0)


def _string(value: str) -> bytes:
    data = value.encode()
    return struct.pack("<Q", len(data)) + data


def gguf(architecture: str = "qwen35", name: str | None = "Tiny Model", body: bytes = b"") -> bytes:
    """A minimal GGUF v3 header with string metadata, then ``body``."""
    kvs = [("general.architecture", architecture)]
    if name is not None:
        kvs.append(("general.name", name))
    out = b"GGUF" + struct.pack("<IQQ", 3, 0, len(kvs))
    for key, value in kvs:
        out += _string(key) + struct.pack("<I", 8) + _string(value)
    return out + body


async def _chunks(data: bytes, size: int = 7) -> AsyncIterator[bytes]:
    for start in range(0, len(data), size):
        yield data[start : start + size]


async def _receive(models: Path, data: bytes, **kw) -> custom.MyModelFile:  # type: ignore[no-untyped-def]
    kw.setdefault("file_name", "Tiny Model Q4.gguf")
    kw.setdefault("kind", "model")
    kw.setdefault("declared_size", len(data))
    return await custom.receive(models, _chunks(data), **kw)


def test_header_gives_architecture_and_name() -> None:
    header = custom.read_header(gguf("clip", "Projector"))
    assert header == {"general.architecture": "clip", "general.name": "Projector"}
    assert custom.read_header(b"not a gguf file at all.....") == {}
    # A broken length never reads past the header or raises.
    assert custom.read_header(b"GGUF" + struct.pack("<IQQ", 3, 0, 1) + b"\xff" * 16) == {}


def test_file_names_become_safe() -> None:
    assert custom.safe_file_name("C:\\models\\My Model (Q4).GGUF") == "My-Model-Q4.gguf"
    assert custom.safe_file_name("../../etc/passwd") == "passwd.gguf"
    assert custom.safe_file_name("....gguf") == "model.gguf"


async def test_a_copied_model_is_stored_checked_and_listed(tmp_path: Path) -> None:
    data = gguf(body=b"weights" * 100)
    info = await _receive(tmp_path, data)
    assert info.kind == "model" and info.name == "Tiny Model" and info.size == len(data)
    assert info.file == "Tiny-Model-Q4.gguf"
    entry = custom.model_entry(info, None)
    # Stored where the private service's sandbox reads models, with the
    # checksum marker a catalogue download gets.
    assert file_path(tmp_path, entry.gguf).read_bytes() == data
    assert model_present(tmp_path, entry)
    assert custom.list_files(tmp_path) == [info]
    assert not list((tmp_path / custom.FOLDER / ".incoming").iterdir())
    # The same file twice is kept once.
    again = await _receive(tmp_path, data, file_name="Tiny Model Q4.gguf")
    assert again.sha256 == info.sha256 and len(custom.list_files(tmp_path)) == 1


async def test_a_model_with_an_image_addon_reads_images(tmp_path: Path) -> None:
    model = await _receive(tmp_path, gguf(body=b"w" * 50))
    addon = await _receive(
        tmp_path,
        gguf("clip", "Projector", b"p" * 30),
        file_name="mmproj-F16.gguf",
        kind="image_addon",
        for_model=model.sha256,
    )
    assert addon.for_model == model.sha256
    entry = custom.model_entry(model, addon)
    assert entry.mmproj is not None and entry.size == model.size + addon.size
    # Its name has no colon: llama-server renames a model whose name has one.
    assert ":" not in entry.served_name and entry.served_name.startswith("my-tiny-model-")
    assert custom.find(tmp_path, addon.sha256, "image_addon") == addon
    with pytest.raises(custom.MyModelError):
        custom.find(tmp_path, addon.sha256, "model")


@pytest.mark.parametrize(
    ("data", "kind", "message"),
    [
        (b"PK\x03\x04 a zip file, not a model", "model", "not a GGUF model file"),
        (gguf("clip", "Projector"), "model", "image add-on"),
        (gguf("qwen35", "Model"), "image_addon", "is a model, not an image add-on"),
    ],
)
async def test_wrong_files_are_refused_and_nothing_is_kept(
    tmp_path: Path, data: bytes, kind: custom.FileKind, message: str
) -> None:
    with pytest.raises(custom.MyModelError, match=message):
        await _receive(tmp_path, data, kind=kind)
    assert custom.list_files(tmp_path) == []
    assert not list((tmp_path / custom.FOLDER / ".incoming").iterdir())


async def test_a_file_that_did_not_arrive_whole_is_refused(tmp_path: Path) -> None:
    data = gguf(body=b"x" * 40)
    with pytest.raises(custom.MyModelError, match="did not arrive whole"):
        await _receive(tmp_path, data, declared_size=len(data) + 1)
    assert custom.list_files(tmp_path) == []


def test_a_setup_with_your_own_model_is_saved_with_it() -> None:
    entry = custom.model_entry(
        custom.MyModelFile(sha256="a" * 64, file="m.gguf", size=10, kind="model", name="M"),
        None,
    )
    config = AIConfig(
        source="private",
        base_url="http://localhost",
        backend="llama_cpp",
        tier="custom",
        text_model=entry.served_name,
        vision_model="",
        custom_model=entry,
    )
    assert AIConfig.model_validate_json(config.model_dump_json()) == config


def test_a_model_without_an_image_addon_answers_image_questions_from_text() -> None:
    """Before, the image went to an empty model name and failed (HTTP 400)."""
    from types import SimpleNamespace

    from audit.suggest.provider import choose_model

    bundle = SimpleNamespace(image_bytes=b"png")
    choice = choose_model(bundle, text_model="my-text", vision_model="")  # type: ignore[arg-type]
    assert (choice.model, choice.uses_vision) == ("my-text", False)
    choice = choose_model(bundle, text_model="t", vision_model="v")  # type: ignore[arg-type]
    assert (choice.model, choice.uses_vision) == ("v", True)


def test_answer_settings_out_of_range_are_refused() -> None:
    from pydantic import ValidationError

    from audit.web.ai_api import UseMyModelRequest

    ok = UseMyModelRequest(
        model="a" * 64, sampling={"temp": 0.7, "top-p": 0.8, "top-k": 20}, confirm=True
    )
    assert ok.sampling == {"temp": 0.7, "top-p": 0.8, "top-k": 20}
    for bad in ({"temp": 3.0}, {"top-p": 1.5}, {"top-k": 20.5}, {"presence-penalty": -3.0}):
        with pytest.raises(ValidationError):
            UseMyModelRequest(model="a" * 64, sampling=bad, confirm=True)


def test_start_ai_service_works_with_your_own_model(tmp_path: Path) -> None:
    """Start AI service raised KeyError('custom') with your own model in use."""
    from unittest.mock import Mock

    from audit.ai.manager import AIManager
    from audit.ai.state import AIPreferences, save_config, save_preferences
    from audit.config import Settings

    settings = Settings(data_dir=tmp_path, desktop=True)
    entry = custom.model_entry(
        custom.MyModelFile(sha256="b" * 64, file="m.gguf", size=10, kind="model", name="M"), None
    )
    save_preferences(settings, AIPreferences(enabled=True, choice_recorded=True))
    save_config(
        settings,
        AIConfig(
            source="private",
            base_url="http://localhost",
            backend="llama_cpp",
            tier="custom",
            text_model=entry.served_name,
            vision_model="",
            custom_model=entry,
        ),
    )
    runtime = Mock()
    runtime.running.return_value = False
    runtime.installed.return_value = True
    runtime.has_model.return_value = True
    runtime.service_fields.return_value = {"socket_path": str(tmp_path / "s.sock"), "routes": None}
    manager = AIManager(settings, lambda _c: None, runtime=runtime)
    assert manager.start_runtime().state == "started"
    runtime.start.assert_called_once_with((entry,))
