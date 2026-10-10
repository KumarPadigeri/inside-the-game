"""Tests for the tracing switch (no Azure calls)."""

import asyncio

import pytest

from inside_the_game import tracing


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "_configured", False)
    monkeypatch.delenv("TRACING", raising=False)
    monkeypatch.delenv("CONTAINER_APP_NAME", raising=False)


class FakeClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, object]] = []

    async def configure_azure_monitor(self, **kwargs: object) -> None:
        self.calls.append(kwargs)
        if self.error:
            raise self.error


def test_off_by_default_locally(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "make_client", lambda: pytest.fail("should not connect"))
    assert asyncio.run(tracing.setup_tracing()) is False


def test_on_in_azure_without_recording_prompts(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeClient()
    monkeypatch.setattr(tracing, "make_client", lambda: client)
    monkeypatch.setenv("CONTAINER_APP_NAME", "inside-the-game-api")
    assert asyncio.run(tracing.setup_tracing()) is True
    assert client.calls[0]["enable_sensitive_data"] is False
    # Configured once per process, however often it is called.
    assert asyncio.run(tracing.setup_tracing()) is True
    assert len(client.calls) == 1


def test_failure_to_connect_never_breaks_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tracing, "make_client", lambda: FakeClient(RuntimeError("no App Insights")))
    monkeypatch.setenv("TRACING", "1")
    assert asyncio.run(tracing.setup_tracing()) is False
