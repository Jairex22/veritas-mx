"""Sesión HTTP simulada para autoevaluar la resiliencia del conector sin tocar FactoryLogix real."""
from __future__ import annotations

from typing import Any

import requests


class SimulatedResponse:
    def __init__(self, status_code: int, payload: Any = None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> Any:
        return self._payload


class SimulatedSession:
    """Devuelve respuestas predefinidas; `mode` puede ser ok, offline, timeout o un código HTTP."""

    def __init__(self, mode: str | int = "ok", payload: Any = None):
        self.mode = mode
        self.payload = payload or {"value": [{"SerialNumber": "DEMO-SN-0001", "Status": "In Process"}]}
        self.calls = 0
        self.methods: list[str] = []
        self.trust_env = False

    def get(self, url: str, **_kwargs: Any) -> SimulatedResponse:
        self.calls += 1
        self.methods.append("GET")
        if self.mode == "offline":
            raise requests.ConnectionError("simulated offline")
        if self.mode == "timeout":
            raise requests.Timeout("simulated timeout")
        if self.mode == "ok":
            return SimulatedResponse(200, self.payload)
        return SimulatedResponse(int(self.mode))
