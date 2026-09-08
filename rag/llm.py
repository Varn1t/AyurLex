"""Ollama client: the local LLM, always on.

"Always on" is taken literally. This module does not assume a running server --
it finds the ollama binary, starts it detached if the API is unreachable, waits
for it, and reconnects if the server dies mid-session. A demo must not fail
because someone forgot to run `ollama serve` in another window.

Running the model locally is not a convenience here, it is the product's answer
to its first industry objection. A manufacturer will not paste a proprietary
formulation into a hosted API. With Ollama the formulation never leaves the
machine, and the whole stack -- corpus, retrieval, rules, generation -- runs
air-gapped.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")

# Preference order updated to use your local qwen3.5:4b model first.
PREFERRED = [
    "qwen3.5-small:latest",
    "qwen3.5-small",
    "qwen3.5:4b",
    "qwen2.5:1.5b",
    "llama3.2:latest",
    "llama3.1:latest",
    "llama3:latest",
    "mistral:latest",
]

WINDOWS_PATHS = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
    Path("C:/Program Files/Ollama/ollama.exe"),
]


class OllamaUnavailable(RuntimeError):
    pass


@dataclass
class OllamaStatus:
    running: bool
    model: str = ""
    models: tuple[str, ...] = ()
    started_by_us: bool = False
    detail: str = ""


def _get(path: str, timeout: float = 3.0) -> dict:
    with urllib.request.urlopen(f"{HOST}{path}", timeout=timeout) as r:
        return json.load(r)


def is_up(timeout: float = 2.0) -> bool:
    try:
        _get("/api/tags", timeout=timeout)
        return True
    except Exception:
        return False


def find_binary() -> str | None:
    exe = shutil.which("ollama")
    if exe:
        return exe
    for p in WINDOWS_PATHS:
        if p.exists():
            return str(p)
    return None


def start_server(wait: float = 25.0) -> bool:
    """Spawn `ollama serve` detached and wait for the API to answer."""
    exe = find_binary()
    if not exe:
        return False
    try:
        kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008 | 0x00000200
        else:
            kwargs["start_new_session"] = True
        subprocess.Popen([exe, "serve"], **kwargs)
    except Exception:
        return False

    deadline = time.time() + wait
    while time.time() < deadline:
        if is_up(timeout=1.5):
            return True
        time.sleep(0.6)
    return False


def installed_models() -> list[str]:
    try:
        return [m["name"] for m in _get("/api/tags").get("models", [])]
    except Exception:
        return []


def choose_model(preferred: str | None = None) -> str:
    have = installed_models()
    if preferred and preferred in have:
        return preferred
    if preferred and not have:
        return preferred
    for name in PREFERRED:
        if name in have:
            return name
    return have[0] if have else ""


def ensure(model: str | None = None, *, autostart: bool = True) -> OllamaStatus:
    """Make Ollama available. Starts the server if it is not already up."""
    started = False
    if not is_up():
        if not autostart:
            return OllamaStatus(False, detail="ollama is not running")
        if not find_binary():
            return OllamaStatus(
                False,
                detail="ollama is not installed — get it from https://ollama.com",
            )
        started = start_server()
        if not started:
            return OllamaStatus(
                False, detail="could not start the ollama server", started_by_us=False
            )

    models = tuple(installed_models())
    chosen = choose_model(model or os.environ.get("SAKTI_MODEL"))
    if not chosen:
        return OllamaStatus(
            True, models=models, started_by_us=started,
            detail="ollama is running but no model is pulled — "
                   "run:  ollama pull qwen3.5:4b",
        )
    return OllamaStatus(True, model=chosen, models=models, started_by_us=started)


class Ollama:
    """Thin generate client with one reconnect attempt."""

    def __init__(self, model: str | None = None, *, autostart: bool = True,
                 timeout: float = 180.0):
        self.status = ensure(model, autostart=autostart)
        if not self.status.running or not self.status.model:
            raise OllamaUnavailable(self.status.detail or "ollama unavailable")
        self.model = self.status.model
        self.timeout = timeout

    def _body(self, prompt: str, system: str, temperature: float,
            num_predict: int, stream: bool) -> bytes:
        return json.dumps({
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "top_p": 0.9,
                "num_predict": num_predict,
                # Reduced context to 2048 to prevent RAM out-of-memory errors
                "num_ctx": 2048,
            },
        }).encode()

    def stream(self, prompt: str, system: str, *, temperature: float = 0.1,
               num_predict: int = 500):
        req = urllib.request.Request(
            f"{HOST}/api/generate",
            data=self._body(prompt, system, temperature, num_predict, True),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            for line in r:
                if not line.strip():
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if chunk.get("response"):
                    yield chunk["response"]
                if chunk.get("done"):
                    return

    def warm(self) -> float:
        t = time.time()
        try:
            self.generate("ok", "Reply with one word.", num_predict=2)
        except Exception:
            pass
        return time.time() - t

    def generate(self, prompt: str, system: str, *, temperature: float = 0.1,
                 num_predict: int = 700) -> str:
        body = json.dumps({
            "model": self.model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": temperature,
                "top_p": 0.9,
                "num_predict": num_predict,
                # Reduced context to 2048 to prevent RAM out-of-memory errors
                "num_ctx": 2048,
            },
        }).encode()

        for attempt in (1, 2):
            try:
                req = urllib.request.Request(
                    f"{HOST}/api/generate", data=body,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.load(r).get("response", "").strip()
            except (urllib.error.URLError, TimeoutError, OSError):
                if attempt == 2:
                    raise
                ensure(self.model)
                time.sleep(1.0)
        return ""