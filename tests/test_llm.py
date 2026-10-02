from types import SimpleNamespace
from unittest.mock import AsyncMock

import anthropic
import pytest

from backend.services import llm


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

    assert result == {
        "category": "coffee",
        "dietary_tag": None,
        "price_tier": None,
        "clarifying_question": None,
        "any_category": False,
        "is_followup": False,
    }


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

    assert result == {
        "category": None,
        "dietary_tag": None,
        "price_tier": None,
        "clarifying_question": None,
        "any_category": True,
        "is_followup": False,
    }


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
async def test_instructs_the_model_to_write_hebrew_when_language_is_he(monkeypatch):
    fake_client = make_fake_client(
        {"any_category": False, "matched_category": "burger", "clarifying_question": ""}
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    await llm.parse_food_request("something with meat", ["coffee", "burger"], language="he")

    _, kwargs = fake_client.messages.create.call_args
    assert "Hebrew" in kwargs["system"]


@pytest.mark.asyncio
async def test_degrades_gracefully_on_api_error_with_hebrew_fallback(monkeypatch):
    fake_client = AsyncMock()
    fake_client.messages.create.side_effect = anthropic.APIConnectionError(request=object())
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request("burger", ["coffee", "burger"], language="he")

    assert result["clarifying_question"] == llm._FALLBACK_QUESTIONS["he"]


@pytest.mark.asyncio
async def test_mentions_previous_category_in_system_prompt_when_context_given(monkeypatch):
    fake_client = make_fake_client(
        {"any_category": False, "matched_category": "coffee", "is_followup": True, "clarifying_question": ""}
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    await llm.parse_food_request(
        "something else",
        ["coffee", "burger"],
        previous_category="coffee",
        has_previous_context=True,
    )

    _, kwargs = fake_client.messages.create.call_args
    assert "coffee" in kwargs["system"]
    assert "is_followup" in kwargs["system"]


@pytest.mark.asyncio
async def test_is_followup_true_passes_through_when_context_was_given(monkeypatch):
    fake_client = make_fake_client(
        {"any_category": False, "matched_category": "coffee", "is_followup": True, "clarifying_question": ""}
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request(
        "something else", ["coffee", "burger"], previous_category="coffee", has_previous_context=True
    )

    assert result["is_followup"] is True


@pytest.mark.asyncio
async def test_is_followup_forced_false_when_no_previous_context_was_given(monkeypatch):
    # Defense in depth: even if the model somehow returns is_followup=true
    # without being given any previous-turn context, there's nothing to
    # follow up on, so the result must not claim otherwise.
    fake_client = make_fake_client(
        {"any_category": False, "matched_category": "coffee", "is_followup": True, "clarifying_question": ""}
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request("something else", ["coffee", "burger"], has_previous_context=False)

    assert result["is_followup"] is False


@pytest.mark.asyncio
async def test_is_followup_forced_false_when_model_names_a_different_category(monkeypatch):
    # Regression guard: the model doesn't always self-correct is_followup
    # when it extracts an explicit new category after a previous one (seen
    # live with "actually, pizza" after a "coffee" context) - matched_category
    # only ever comes from the known list, so a differing one is treated as
    # decisive regardless of what is_followup says.
    fake_client = make_fake_client(
        {"any_category": False, "matched_category": "pizza", "is_followup": True, "clarifying_question": ""}
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request(
        "actually, pizza",
        ["coffee", "pizza"],
        previous_category="coffee",
        has_previous_context=True,
    )

    assert result == {
        "category": "pizza",
        "dietary_tag": None,
        "price_tier": None,
        "clarifying_question": None,
        "any_category": False,
        "is_followup": False,
    }


@pytest.mark.asyncio
async def test_is_followup_stays_true_when_model_repeats_the_same_previous_category(monkeypatch):
    # A model that (redundantly but harmlessly) echoes the same category
    # back on a genuine followup shouldn't get overridden.
    fake_client = make_fake_client(
        {"any_category": False, "matched_category": "coffee", "is_followup": True, "clarifying_question": ""}
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request(
        "something else",
        ["coffee", "pizza"],
        previous_category="coffee",
        has_previous_context=True,
    )

    assert result["is_followup"] is True


@pytest.mark.asyncio
async def test_no_previous_category_mention_in_system_prompt_without_context(monkeypatch):
    fake_client = make_fake_client(
        {"any_category": False, "matched_category": "burger", "is_followup": False, "clarifying_question": ""}
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    await llm.parse_food_request("burger", ["coffee", "burger"])

    _, kwargs = fake_client.messages.create.call_args
    assert "previous request" not in kwargs["system"]


@pytest.mark.asyncio
async def test_returns_matched_dietary_tag(monkeypatch):
    monkeypatch.setattr(
        llm,
        "_get_client",
        lambda: make_fake_client(
            {
                "any_category": False,
                "matched_category": "burger",
                "matched_dietary_tag": "vegan",
                "is_followup": False,
                "clarifying_question": "",
            }
        ),
    )

    result = await llm.parse_food_request("vegan burger", ["coffee", "burger"], dietary_tags=["vegan", "kosher"])

    assert result["category"] == "burger"
    assert result["dietary_tag"] == "vegan"


@pytest.mark.asyncio
async def test_dietary_tags_mentioned_in_system_prompt_when_present(monkeypatch):
    fake_client = make_fake_client(
        {
            "any_category": False,
            "matched_category": "burger",
            "matched_dietary_tag": "",
            "is_followup": False,
            "clarifying_question": "",
        }
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    await llm.parse_food_request("burger", ["coffee", "burger"], dietary_tags=["vegan", "kosher"])

    _, kwargs = fake_client.messages.create.call_args
    assert "vegan, kosher" in kwargs["system"]


@pytest.mark.asyncio
async def test_no_dietary_tags_mention_in_system_prompt_when_none_exist(monkeypatch):
    fake_client = make_fake_client(
        {"any_category": False, "matched_category": "burger", "is_followup": False, "clarifying_question": ""}
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    await llm.parse_food_request("burger", ["coffee", "burger"])

    _, kwargs = fake_client.messages.create.call_args
    assert "dietary tags" not in kwargs["system"]


@pytest.mark.asyncio
async def test_is_followup_forced_false_when_model_names_a_different_dietary_tag(monkeypatch):
    fake_client = make_fake_client(
        {
            "any_category": False,
            "matched_category": "burger",
            "matched_dietary_tag": "vegan",
            "is_followup": True,
            "clarifying_question": "",
        }
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request(
        "actually make it vegan",
        ["burger"],
        dietary_tags=["vegan", "kosher"],
        previous_category="burger",
        previous_dietary_tag="kosher",
        has_previous_context=True,
    )

    assert result["dietary_tag"] == "vegan"
    assert result["is_followup"] is False


@pytest.mark.asyncio
async def test_is_followup_stays_true_when_dietary_tag_matches_previous(monkeypatch):
    fake_client = make_fake_client(
        {
            "any_category": False,
            "matched_category": "burger",
            "matched_dietary_tag": "kosher",
            "is_followup": True,
            "clarifying_question": "",
        }
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request(
        "something else",
        ["burger"],
        dietary_tags=["vegan", "kosher"],
        previous_category="burger",
        previous_dietary_tag="kosher",
        has_previous_context=True,
    )

    assert result["is_followup"] is True


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


@pytest.mark.asyncio
async def test_extracts_price_tier_alongside_category(monkeypatch):
    fake_client = make_fake_client(
        {
            "any_category": False,
            "matched_category": "pizza",
            "matched_price_tier": "$",
            "is_followup": False,
            "clarifying_question": "",
        }
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request("cheap pizza", ["coffee", "pizza"])

    assert result["category"] == "pizza"
    assert result["price_tier"] == "$"


@pytest.mark.asyncio
async def test_price_only_request_is_any_category_with_a_price(monkeypatch):
    fake_client = make_fake_client(
        {
            "any_category": True,
            "matched_category": "",
            "matched_price_tier": "$$$",
            "is_followup": False,
            "clarifying_question": "",
        }
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request("somewhere fancy", ["coffee", "pizza"])

    assert result["any_category"] is True
    assert result["category"] is None
    assert result["price_tier"] == "$$$"


@pytest.mark.asyncio
@pytest.mark.parametrize("bogus", ["", None, "$$$$", "cheap", "€", 2])
async def test_price_tier_outside_the_known_set_is_dropped(monkeypatch, bogus):
    # The enum in the tool schema isn't a guarantee on the response side; an
    # unknown value reaching the Mongo query would silently match nothing.
    fake_client = make_fake_client(
        {
            "any_category": False,
            "matched_category": "pizza",
            "matched_price_tier": bogus,
            "is_followup": False,
            "clarifying_question": "",
        }
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request("pizza", ["coffee", "pizza"])

    assert result["price_tier"] is None


@pytest.mark.asyncio
async def test_missing_price_field_means_no_price(monkeypatch):
    fake_client = make_fake_client({"any_category": False, "matched_category": "pizza", "clarifying_question": ""})
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request("pizza", ["coffee", "pizza"])

    assert result["price_tier"] is None


@pytest.mark.asyncio
async def test_naming_only_a_different_price_stays_a_followup(monkeypatch):
    # "cheaper" after coffee: unlike a different category or tag, a price
    # change refines the previous search instead of replacing it.
    fake_client = make_fake_client(
        {
            "any_category": False,
            "matched_category": "",
            "matched_price_tier": "$",
            "is_followup": True,
            "clarifying_question": "",
        }
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request(
        "cheaper",
        ["coffee", "pizza"],
        previous_category="coffee",
        previous_price_tier="$$",
        has_previous_context=True,
    )

    assert result["is_followup"] is True
    assert result["price_tier"] == "$"


@pytest.mark.asyncio
async def test_previous_price_is_described_in_the_system_prompt(monkeypatch):
    fake_client = make_fake_client(
        {
            "any_category": False,
            "matched_category": "",
            "matched_price_tier": "",
            "is_followup": True,
            "clarifying_question": "",
        }
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    await llm.parse_food_request(
        "something else", ["coffee"], previous_category="coffee", previous_price_tier="$$", has_previous_context=True
    )

    _, kwargs = fake_client.messages.create.call_args
    assert "price $$" in kwargs["system"]


@pytest.mark.asyncio
async def test_tool_schema_offers_exactly_the_three_tiers_and_an_empty_value(monkeypatch):
    fake_client = make_fake_client({"any_category": False, "matched_category": "pizza", "clarifying_question": ""})
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    await llm.parse_food_request("pizza", ["pizza"])

    _, kwargs = fake_client.messages.create.call_args
    schema = kwargs["tools"][0]["input_schema"]
    assert schema["properties"]["matched_price_tier"]["enum"] == ["", "$", "$$", "$$$"]
    assert "matched_price_tier" in schema["required"]


@pytest.mark.asyncio
async def test_tag_not_in_the_known_list_is_dropped(monkeypatch):
    # Seen live: with no tag fitting "a date spot", the model echoed the
    # user's own words back as the tag, filtering on a value no place has.
    fake_client = make_fake_client(
        {
            "any_category": False,
            "matched_category": "",
            "matched_dietary_tag": "a date spot",
            "clarifying_question": "What cuisine?",
        }
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request("a date spot", ["coffee"], dietary_tags=["vegan", "kosher"])

    assert result["dietary_tag"] is None
    # Nothing usable was extracted, so it stays a clarifying question (and so
    # gets logged as unmatched) rather than becoming a fake "surprise me".
    assert result["any_category"] is False
    assert result["clarifying_question"] == "What cuisine?"


@pytest.mark.asyncio
async def test_known_tag_passes_through(monkeypatch):
    fake_client = make_fake_client(
        {"any_category": False, "matched_category": "", "matched_dietary_tag": "date", "clarifying_question": ""}
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request("a date spot", ["coffee"], dietary_tags=["date"])

    assert result["dietary_tag"] == "date"


@pytest.mark.asyncio
async def test_system_prompt_says_when_there_are_no_known_tags(monkeypatch):
    fake_client = make_fake_client({"any_category": False, "matched_category": "coffee", "clarifying_question": ""})
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    await llm.parse_food_request("coffee", ["coffee"])

    _, kwargs = fake_client.messages.create.call_args
    assert "no known tags" in kwargs["system"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "extra",
    [{"matched_dietary_tag": "date"}, {"matched_price_tier": "$"}],
    ids=["tag only", "price only"],
)
async def test_a_filter_with_no_category_is_a_search_not_a_question(monkeypatch, extra):
    # The model often asks "what cuisine?" for "a date spot" / "something
    # cheap"; a filter alone is a complete request, so any_category is set
    # here and the question dropped.
    fake_client = make_fake_client(
        {
            "any_category": False,
            "matched_category": "",
            "clarifying_question": "What cuisine would you like?",
            **extra,
        }
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request("x", ["coffee"], dietary_tags=["date"])

    assert result["any_category"] is True
    assert result["clarifying_question"] is None


@pytest.mark.asyncio
async def test_a_price_followup_is_not_turned_into_an_any_category_search(monkeypatch):
    fake_client = make_fake_client(
        {
            "any_category": False,
            "matched_category": "",
            "matched_price_tier": "$",
            "is_followup": True,
            "clarifying_question": "",
        }
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request(
        "cheaper", ["coffee"], previous_category="coffee", has_previous_context=True
    )

    assert result["is_followup"] is True
    assert result["any_category"] is False


@pytest.mark.asyncio
async def test_no_filter_and_no_category_still_asks_a_question(monkeypatch):
    fake_client = make_fake_client(
        {"any_category": False, "matched_category": "", "clarifying_question": "What are you craving?"}
    )
    monkeypatch.setattr(llm, "_get_client", lambda: fake_client)

    result = await llm.parse_food_request("hmm", ["coffee"])

    assert result["any_category"] is False
    assert result["clarifying_question"] == "What are you craving?"
