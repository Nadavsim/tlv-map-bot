import logging
import re

import anthropic

logger = logging.getLogger(__name__)

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
                        "closest', 'I don't care' - or only states a price or one of the "
                        "KNOWN tags with no food type, e.g. 'something cheap', 'anything "
                        "kosher'. False otherwise - in particular False when the user asks "
                        "for an occasion or quality that is not in the known tags (e.g. 'a "
                        "date spot' when no such tag exists): put that in "
                        "unsupported_requirement instead."
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
                        "The single tag the user asked for - a dietary requirement (kosher, "
                        "vegan, vegetarian, gluten-free) or an occasion/vibe (e.g. a date "
                        "spot, a group dinner, late night) - copied exactly from the "
                        "provided list of known tags. Empty string if the user didn't ask "
                        "for anything like that, or if none of the known tags match it."
                    ),
                },
                "matched_price_tier": {
                    "type": "string",
                    "enum": ["", "$", "$$", "$$$"],
                    "description": (
                        "The price level the user explicitly asked for - only when they talk "
                        "about price, cost or budget; never infer it from an occasion or mood "
                        "(a 'romantic dinner' is not a price request). '$' for cheap/budget/inexpensive, "
                        "'$$' for mid-range/moderately priced, '$$$' for expensive/fancy/"
                        "upscale/splurge. Empty string if they didn't mention price, or if "
                        "it isn't clearly one of these (e.g. 'not too expensive')."
                    ),
                },
                "is_followup": {
                    "type": "boolean",
                    "description": (
                        "True ONLY if the message does not name any specific category or "
                        "tag on its own and is clearly building on the previous "
                        "request mentioned below - e.g. 'something else', 'another one', "
                        "'what else do you have', 'closer', or a message that only changes "
                        "the price of the previous request like 'cheaper' or 'something "
                        "fancier' (set matched_price_tier too). False if there's no "
                        "previous request, or if the message names or clearly implies any "
                        "category or tag from the lists - even a brief one like "
                        "'pizza' or 'actually sushi' or 'kosher' - since that's a new, "
                        "distinct request, not a continuation, regardless of how it's phrased."
                    ),
                },
                "unsupported_requirement": {
                    "type": "string",
                    "description": (
                        "A specific requirement the user stated that is NOT one of the "
                        "known categories, NOT one of the known tags and NOT a price level - "
                        "e.g. 'vegan', 'kosher', 'open now', 'outdoor seating', 'a date spot', "
                        "'good for kids' when those are not in the known tags. One to three "
                        "words, in the user's own language, copied from their message. Empty "
                        "string if there is no such requirement. Never put a category, a "
                        "known tag or a price word here."
                    ),
                },
                "outside_food_scope": {
                    "type": "boolean",
                    "description": (
                        "True ONLY if the request is not about food, drink or a place to eat "
                        "or drink at all - e.g. a night club, a pharmacy, a hotel, a taxi, "
                        "directions. False for anything food, coffee, bar or restaurant "
                        "related, including vague ones ('tasty food', 'hearty', 'breakfast')."
                    ),
                },
                "mentioned_place": {
                    "type": "string",
                    "description": (
                        "A place, street, neighbourhood or landmark the user wants to be "
                        "near, if they named one - e.g. 'Allenby', 'Florentin', 'the beach'. "
                        "Copied from their message, one to four words. Empty string if they "
                        "named none; 'near me' and 'nearby' are not places."
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
                "matched_price_tier",
                "is_followup",
                "unsupported_requirement",
                "outside_food_scope",
                "mentioned_place",
                "clarifying_question",
            ],
        },
    }
]

_PRICE_TIERS = ("$", "$$", "$$$")

_MAX_UNSUPPORTED_CHARS = 40
# Anything that could be markup, a format placeholder or invisible/control
# text: the requirement is echoed back to the visitor inside a reply sentence
# and is written to the curator's unmatched log.
_UNSAFE_REQUIREMENT_CHARS = re.compile(r"[<>{}\\\"`\u0000-\u001f\u007f\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060\ufeff\u2066-\u2069]")


def _clean_requirement(raw, categories: list[str], dietary_tags: list[str]) -> str | None:
    """The model's `unsupported_requirement`, made safe to show: a short plain
    string, never a known category or tag (those are handled elsewhere)."""
    if not isinstance(raw, str):
        return None
    text = " ".join(_UNSAFE_REQUIREMENT_CHARS.sub(" ", raw).split())[:_MAX_UNSUPPORTED_CHARS].strip()
    if not text:
        return None
    known = {name.lower() for name in categories} | {tag.lower() for tag in dietary_tags}
    return None if text.lower() in known else text

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
    previous_price_tier: str | None = None,
) -> dict:
    """Ask Claude to match free text against the known categories (and,
    optionally, a tag and a price tier).

    Returns {"category": str|None, "dietary_tag": str|None, "price_tier":
    "$"|"$$"|"$$$"|None, "clarifying_question": str|None, "any_category":
    bool, "is_followup": bool}. "any_category" True means "surprise me" -
    ignore "category" and search all places. On any API failure, degrades to
    a clarifying-question response instead of raising - a chat turn failing
    outright is worse than asking the user to retry.

    Unlike category/tag, the price tier comes from a fixed enum rather than
    a live list, and naming a different one does NOT override is_followup:
    "cheaper" after "coffee" means cheap coffee, so the caller keeps the
    previous category and swaps in the new price.

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
        f" Known tags: {', '.join(dietary_tags)}."
        if dietary_tags
        else " There are no known tags yet, so matched_dietary_tag must be empty."
    )
    context_sentence = ""
    if has_previous_context:
        previous_bits = [f"category {previous_category or 'any category (surprise me)'}"]
        if previous_dietary_tag:
            previous_bits.append(f"tag {previous_dietary_tag}")
        if previous_price_tier:
            previous_bits.append(f"price {previous_price_tier}")
        context_sentence = (
            f" The user's previous request in this conversation was {' with '.join(previous_bits)}. "
            "A relative price word ('cheaper', 'fancier', 'more expensive') moves matched_price_tier "
            "exactly ONE step from the previous price ($ < $$ < $$$), and stays at the end of the "
            "scale if it is already there; with no previous price, 'cheaper' is $ and 'fancier' is $$$. "
            "Set is_followup to true only when the message doesn't name a category or tag "
            "itself and is just building on that previous request (including one that only "
            "changes the price). The moment the message names a "
            "different category or tag, even briefly, that overrides the previous request - "
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
                f"Write any clarifying_question in {language_name}. "
                "If the user states a requirement that is not a category, a known tag or "
                "a price level (for example vegan, kosher, open now, outdoor seating), put "
                "it in unsupported_requirement and do not turn it into a tag. "
                "The list only has food and coffee places: set outside_food_scope for a "
                "request about anything else. If the user names a place they want to be "
                "near, put it in mentioned_place - the search always runs from the "
                "location they have set, never from a place named in the message."
                f"{context_sentence} "
                "Always call the extract_food_request tool."
            ),
            tools=_TOOLS,
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[{"role": "user", "content": message}],
        )
        tool_use = next(b for b in response.content if b.type == "tool_use")
        result = tool_use.input
    except (anthropic.APIError, StopIteration) as error:
        # The model call itself failed (bad key, no credit, rate limit,
        # outage, a reply with no tool call) - not "the visitor asked for
        # something we don't have". It is flagged so the caller can tell the
        # two apart and so it is never counted as an unmatched craving. Only
        # the error type and HTTP status are logged, never the message text.
        status = getattr(error, "status_code", None)
        logger.warning("llm call failed: %s%s", type(error).__name__, f" (status {status})" if status else "")
        fallback = _FALLBACK_QUESTIONS.get(language, _FALLBACK_QUESTIONS["en"])
        return {
            "category": None,
            "dietary_tag": None,
            "price_tier": None,
            "clarifying_question": fallback,
            "any_category": False,
            "is_followup": False,
            "llm_failed": True,
        }

    any_category = bool(result.get("any_category"))
    category = None if any_category else (result.get("matched_category") or None)
    # Held to the known list here, not just in the prompt: left alone the
    # model echoes the user's own words as a "tag" ("a date spot") when none
    # of the real ones fit, which then filters on a value no place has.
    dietary_tag = result.get("matched_dietary_tag") or None
    if dietary_tag not in dietary_tags:
        dietary_tag = None
    # Re-validated here even though the schema has an enum: the API doesn't
    # guarantee tool input conforms to it, and an unknown value would reach
    # the Mongo query as a filter that silently matches nothing.
    price_tier = result.get("matched_price_tier")
    if price_tier not in _PRICE_TIERS:
        price_tier = None
    question = result.get("clarifying_question") or None
    unsupported = _clean_requirement(result.get("unsupported_requirement"), categories, dietary_tags)
    mentioned_place = _clean_requirement(result.get("mentioned_place"), [], [])
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
    # A filter with no category ("a date spot", "something cheap") is a
    # complete search, not a question to bounce back - the model often asks
    # "what cuisine?" anyway, so settle it here rather than in the prompt.
    # Skipped for a followup, which already carries its own category.
    # A request that is not about food at all ("a night club") is not a filter
    # to apologise for while showing restaurants: the caller says the list is
    # only food and coffee. Only when nothing food-related was matched.
    out_of_scope = (
        bool(result.get("outside_food_scope"))
        and category is None
        and not is_followup
        and not dietary_tag
        and not price_tier
    )
    if out_of_scope:
        any_category = False
        question = None
    elif not is_followup and category is None and (dietary_tag or price_tier or unsupported):
        any_category = True
        question = None
    return {
        "category": category,
        "dietary_tag": dietary_tag,
        "price_tier": price_tier,
        "clarifying_question": question,
        "any_category": any_category,
        "is_followup": is_followup,
        # Something the visitor asked for that the list can't honour (e.g.
        # "vegan" with no vegan tags yet). The caller says so in its reply.
        "unsupported": unsupported,
        # Out of scope for a food list (see above), and a place the visitor
        # named that the search does NOT use (it runs from the set location).
        "out_of_scope": out_of_scope,
        "mentioned_place": mentioned_place,
    }
