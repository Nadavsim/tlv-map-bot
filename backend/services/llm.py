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
                "matched_dietary_tag": {
                    "type": "string",
                    "description": (
                        "The single dietary requirement the user mentioned (e.g. kosher, "
                        "vegan, vegetarian, gluten-free), copied exactly from the provided "
                        "list of known dietary tags. Empty string if no dietary requirement "
                        "was mentioned, or if none of the known tags match it."
                    ),
                },
                "is_followup": {
                    "type": "boolean",
                    "description": (
                        "True ONLY if the message does not name any specific category or "
                        "dietary tag on its own and is clearly building on the previous "
                        "request mentioned below - e.g. 'something else', 'another one', "
                        "'what else do you have', 'closer', 'cheaper' (even if a quality "
                        "like price can't actually be filtered on). False if there's no "
                        "previous request, or if the message names or clearly implies any "
                        "category or dietary tag from the lists - even a brief one like "
                        "'pizza' or 'actually sushi' or 'kosher' - since that's a new, "
                        "distinct request, not a continuation, regardless of how it's phrased."
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
            "required": [
                "any_category",
                "matched_category",
                "matched_dietary_tag",
                "is_followup",
                "clarifying_question",
            ],
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
    dietary_tags: list[str] | None = None,
    previous_category: str | None = None,
    previous_dietary_tag: str | None = None,
    has_previous_context: bool = False,
) -> dict:
    """Ask Claude to match free text against the known categories (and,
    optionally, a dietary tag).

    Returns {"category": str|None, "dietary_tag": str|None,
    "clarifying_question": str|None, "any_category": bool, "is_followup":
    bool}. "any_category" True means "surprise me" - ignore "category" and
    search all places. On any API failure, degrades to a clarifying-question
    response instead of raising - a chat turn failing outright is worse
    than asking the user to retry.

    `language` only affects the free-text clarifying_question Claude writes -
    matched_category/matched_dietary_tag are always copied verbatim from the
    given lists (which stay in their original, e.g. English, form regardless
    of language).

    `has_previous_context`/`previous_category`/`previous_dietary_tag` carry
    just enough of the prior turn for Claude to recognize a refinement
    ("something else", "another one") without needing real conversation
    history - previous_category=None with has_previous_context=True means
    the previous turn was "any category" (surprise me), not "no previous
    turn at all".
    """
    dietary_tags = dietary_tags or []
    language_name = _LANGUAGE_NAMES.get(language, _LANGUAGE_NAMES["en"])
    dietary_tags_sentence = (
        f" Known dietary tags: {', '.join(dietary_tags)}." if dietary_tags else ""
    )
    context_sentence = ""
    if has_previous_context:
        previous_bits = [f"category {previous_category or 'any category (surprise me)'}"]
        if previous_dietary_tag:
            previous_bits.append(f"dietary tag {previous_dietary_tag}")
        context_sentence = (
            f" The user's previous request in this conversation was {' with '.join(previous_bits)}. "
            "Set is_followup to true only when the message doesn't name a category or dietary tag "
            "itself and is just building on that previous request. The moment the message names a "
            "different category or dietary tag, even briefly, that overrides the previous request - "
            "it is not a followup."
        )
    try:
        response = await _get_client().messages.create(
            model=MODEL,
            max_tokens=256,
            system=(
                "You help match a user's food craving to one category from this "
                f"list of known categories: {', '.join(categories)}."
                f"{dietary_tags_sentence} "
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
        return {
            "category": None,
            "dietary_tag": None,
            "clarifying_question": fallback,
            "any_category": False,
            "is_followup": False,
        }

    any_category = bool(result.get("any_category"))
    category = None if any_category else (result.get("matched_category") or None)
    dietary_tag = result.get("matched_dietary_tag") or None
    question = result.get("clarifying_question") or None
    is_followup = bool(result.get("is_followup")) and has_previous_context
    # Deterministic safety net: matched_category/matched_dietary_tag only
    # ever come from the known lists (never freeform), so if the model
    # extracted an explicit category or tag that differs from the one being
    # followed up on, that's unambiguous evidence of a genuinely new
    # request - don't rely on the model to have self-corrected is_followup
    # to match (it doesn't always, e.g. "actually, pizza" after "coffee").
    if category is not None and category != previous_category:
        is_followup = False
    if dietary_tag is not None and dietary_tag != previous_dietary_tag:
        is_followup = False
    return {
        "category": category,
        "dietary_tag": dietary_tag,
        "clarifying_question": question,
        "any_category": any_category,
        "is_followup": is_followup,
    }
