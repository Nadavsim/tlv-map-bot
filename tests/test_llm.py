from types import SimpleNamespace
from unittest.mock import AsyncMock

import anthropic
import pytest

import llm


def make_fake_client(tool_input: dict):
    fake_response = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", input=tool_input)]
    )
    fake_client = AsyncMock()
    fake_client.messages.create.return_value = fake_response
    return fake_client


@pytest.mark.asyncio
async def test_returns_matched_category(monkeypatch):
    monkeypatch.setattr(
        llm,
        "_get_client",
        lambda: make_fake_client(
            {"any_category": False, "matched_category": "coffee", "clarifying_question": ""}
        ),
    )

    result = await llm.parse_food_request("I want a flat white", ["coffee", "burger"])

    assert result == {"category": "coffee", "clarifying_question": None, "any_category": False}


@pytest.mark.asyncio
async def test_returns_clarifying_question_when_no_match(monkeypatch):
    monkeypatch.setattr(
        llm,
        "_get_client",
        lambda: make_fake_client(
            {
                "any_category": False,
                "matched_category": "",
                "clarifying_question": "What kind of food are you in the mood for?",
            }
        ),
    )

    result = await llm.parse_food_request("surprise me maybe", ["coffee", "burger"])

    assert result["category"] is None
    assert result["any_category"] is False
    assert result["clarifying_question"] == "What kind of food are you in the mood for?"


@pytest.mark.asyncio
async def test_any_category_true_ignores_matched_category(monkeypatch):
    monkeypatch.setattr(
        llm,
        "_get_client",
        lambda: make_fake_client(
            {"any_category": True, "matched_category": "coffee", "clarifying_question": ""}
        ),
    )

    result = await llm.parse_food_request("surprise me", ["coffee", "burger"])

    assert result == {"category": None, "clarifying_question": None, "any_category": True}


@pytest.mark.asyncio
async def test_forces_the_extraction_tool_and_passes_categories(monkeypatch):
    fake_client = make_fake_client(
        {"any_category": False, "matched_category": "burger", "clarifying_question": ""}
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    await llm.parse_food_request("something with meat", ["coffee", "burger", "pizza"])

    _, kwargs = fake_client.messages.create.call_args
    assert kwargs["tool_choice"] == {"type": "tool", "name": "extract_food_request"}
    assert "coffee, burger, pizza" in kwargs["system"]


@pytest.mark.asyncio
async def test_degrades_gracefully_on_api_error(monkeypatch):
    fake_client = AsyncMock()
    fake_client.messages.create.side_effect = anthropic.APIConnectionError(request=object())
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request("burger", ["coffee", "burger"])

    assert result["category"] is None
    assert result["any_category"] is False
    assert result["clarifying_question"]


@pytest.mark.asyncio
async def test_degrades_gracefully_when_no_tool_use_block_returned(monkeypatch):
    fake_client = AsyncMock()
    fake_client.messages.create.return_value = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="I'm not sure")]
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request("burger", ["coffee", "burger"])

    assert result["category"] is None
    assert result["clarifying_question"]
