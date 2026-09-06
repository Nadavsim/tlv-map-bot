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
                "matched_category": {
                    "type": "string",
                    "description": (
                        "The single best-matching category from the provided list, "
                        "copied exactly as given. Empty string if nothing matches well."
                    ),
                },
                "clarifying_question": {
                    "type": "string",
                    "description": (
                        "A short, friendly follow-up question to ask the user if their "
                        "request was ambiguous or didn't match any category. "
                        "Empty string if matched_category is set."
                    ),
                },
            },
            "required": ["matched_category", "clarifying_question"],
        },
    }
]

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def parse_food_request(message: str, categories: list[str]) -> dict:
    """Ask Claude to match free text against the known categories.

    Returns {"category": str|None, "clarifying_question": str|None}.
    """
    response = _get_client().messages.create(
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

    category = result.get("matched_category") or None
    question = result.get("clarifying_question") or None
    return {"category": category, "clarifying_question": question}
