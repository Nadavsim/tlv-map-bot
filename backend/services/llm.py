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
                "is_followup": {
                    "type": "boolean",
                    "description": (
                        "True ONLY if the message does not name any specific category "
                        "on its own and is clearly building on the previous request "
                        "mentioned below - e.g. 'something else', 'another one', 'what "
                        "else do you have', 'closer', 'cheaper' (even if a quality like "
                        "price can't actually be filtered on). False if there's no "
                        "previous request, or if the message names or clearly implies "
                        "any category from the list - even a brief one like 'pizza' or "
                        "'actually sushi' - since that's a new, distinct request, not a "
                        "continuation, regardless of how it's phrased."
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
            "required": ["any_category", "matched_category", "is_followup", "clarifying_question"],
        },
    }
]

_FALLBACK_QUESTIONS = {
    "en": "I'm having trouble understanding right now - could you try again in a moment?",
    "he": "אני מתקשה להבין כרגע - תוכל לנסות שוב בעוד רגע?",
}

_LANGUAGE_NAMES = {"en": "English", "he": "Hebrew"}

_client: anthropic.AsyncAnthropic | None = None


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic()
    return _client


async def parse_food_request(
    message: str,
    categories: list[str],
    language: str = "en",
    previous_category: str | None = None,
    has_previous_context: bool = False,
) -> dict:
    """Ask Claude to match free text against the known categories.

    Returns {"category": str|None, "clarifying_question": str|None,
    "any_category": bool, "is_followup": bool}. "any_category" True means
    "surprise me" - ignore "category" and search all places. On any API
    failure, degrades to a clarifying-question response instead of raising -
    a chat turn failing outright is worse than asking the user to retry.

    `language` only affects the free-text clarifying_question Claude writes -
    matched_category is always copied verbatim from the given category list
    (which stays in its original, e.g. English, form regardless of language).

    `has_previous_context`/`previous_category` carry just enough of the prior
    turn for Claude to recognize a refinement ("something else", "another
    one") without needing real conversation history - previous_category=None
    with has_previous_context=True means the previous turn was "any category"
    (surprise me), not "no previous turn at all".
    """
    language_name = _LANGUAGE_NAMES.get(language, _LANGUAGE_NAMES["en"])
    context_sentence = ""
    if has_previous_context:
        context_sentence = (
            " The user's previous request in this conversation was categorized as "
            f"{previous_category or 'any category (surprise me)'}. Set is_followup to true only "
            "when the message doesn't name a category itself and is just building on that "
            "previous request. The moment the message names a different category, even briefly, "
            "that overrides any previous request - it is not a followup."
        )
    try:
        response = await _get_client().messages.create(
            model=MODEL,
            max_tokens=256,
            system=(
                "You help match a user's food craving to one category from this "
                f"list of known categories: {', '.join(categories)}. "
                f"Write any clarifying_question in {language_name}."
                f"{context_sentence} "
                "Always call the extract_food_request tool."
            ),
            tools=_TOOLS,
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[{"role": "user", "content": message}],
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        result = tool_use.input
    except (anthropic.APIError, StopIteration):
        fallback = _FALLBACK_QUESTIONS.get(language, _FALLBACK_QUESTIONS["en"])
        return {"category": None, "clarifying_question": fallback, "any_category": False, "is_followup": False}

    any_category = bool(result.get("any_category"))
    category = None if any_category else (result.get("matched_category") or None)
    question = result.get("clarifying_question") or None
    is_followup = bool(result.get("is_followup")) and has_previous_context
    # Deterministic safety net: matched_category only ever comes from the
    # known category list (never freeform), so if the model both extracted
    # an explicit category AND that category differs from the one being
    # followed up on, that's unambiguous evidence of a genuinely new
    # request - don't rely on the model to have self-corrected is_followup
    # to match (it doesn't always, e.g. "actually, pizza" after "coffee").
    if category is not None and category != previous_category:
        is_followup = False
    return {
        "category": category,
        "clarifying_question": question,
        "any_category": any_category,
        "is_followup": is_followup,
    }
