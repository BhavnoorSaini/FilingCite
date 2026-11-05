"""The HTTP endpoint, with a fake model and no database."""

from contextlib import nullcontext

import httpx
import openai
import pytest
from conftest import PASSAGES, reply
from fastapi.testclient import TestClient

import answer
import main


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "connect", lambda: nullcontext())
    monkeypatch.setattr(answer, "search", lambda conn, q, k: PASSAGES)
    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


def use_model(model):
    main.app.dependency_overrides[main.get_model] = lambda: model


def test_answer(client):
    use_model(lambda prompt: reply("Cost of sales was $139,156 million.", numbers=[("139,156", 1)]))
    body = client.post("/svc/api/ask", json={"question": "Amazon cost of sales?"}).json()
    assert body["answered"] and body["citations"][0]["page"] == 38


def test_blank_questions_are_rejected(client):
    use_model(lambda prompt: "")
    assert client.post("/svc/api/ask", json={"question": "   "}).status_code == 422


def test_model_outage_is_503_not_i_dont_know(client):
    def model(prompt):
        request = httpx.Request("POST", "https://api.example.com")
        raise openai.APIConnectionError(request=request)

    use_model(model)
    assert (
        client.post("/svc/api/ask", json={"question": "Amazon cost of sales?"}).status_code == 503
    )
