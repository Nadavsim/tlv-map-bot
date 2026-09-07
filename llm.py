import anthropic

MODEL = "claude-haiku-4-5"

_TOOL_NAME = "extract_food_request"
_TOOLS = [
    {
        "name": _TOOL_NAME,
        "description": (
            "Match the user's free-text food/place craving to one category from "
            "the provided list of known categories."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "any_category": {
                    "type": "boolean",
                    "description": (
                        "True if the user explicitly wants ANY nearby place regardless "
                        "of category - e.g. 'surprise me', 'anything', 'whatever is "
                        "closest', 'I don't care'. False otherwise."
                    ),
                },
                "matched_category": {
                    "type": "string",
                    "description": (
                        "The single best-matching category from the provided list, "
                        "copied exactly as given. Empty string if any_category is true "
                        "or if nothing matches well."
                    ),
                },
                "clarifying_question": {
                    "type": "string",
                    "description": (
                        "A short, friendly follow-up question to ask the user if their "
                        "request was ambiguous and didn't match any category and isn't "
                        "an any_category request. Empty string otherwise."
                    ),
                },
            },
            "required": ["any_category", "matched_category", "clarifying_question"],
        },
    }
]

_FALLBACK_QUESTION = "I'm having trouble understanding right now - could you try again in a moment?"

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


async def parse_food_request(message: str, categories: list[str]) -> dict:
    """Ask Claude to match free text against the known categories.

    Returns {"category": str|None, "clarifying_question": str|None, "any_category": bool}.
    "any_category" True means "surprise me" - ignore "category" and search all places.
    On any API failure, degrades to a clarifying-question response instead of raising -
    a chat turn failing outright is worse than asking the user to retry.
    """
    try:
        response = await _get_client().messages.create(
            model=MODEL,
            max_tokens=256,
            system=(
                "You help match a user's food craving to one category from this "
                f"list of known categories: {', '.join(categories)}. "
                "Always call the extract_food_request tool."
            ),
            tools=_TOOLS,
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[{"role": "user", "content": message}],
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        result = tool_use.input
    except (anthropic.APIError, StopIteration):
        return {"category": None, "clarifying_question": _FALLBACK_QUESTION, "any_category": False}

    any_category = bool(result.get("any_category"))
    category = None if any_category else (result.get("matched_category") or None)
    question = result.get("clarifying_question") or None
    return {"category": category, "clarifying_question": question, "any_category": any_category}
