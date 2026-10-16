"""Guards for frontend/src/styles/theme.css - the app has no frontend test
suite, so colour regressions would otherwise only show up on a real phone.

Checks WCAG 2.x contrast for every text/background and UI pair that really
occurs, in light and dark, and that the two dark blocks (the OS-preference one
and the explicit-toggle one) are identical - they are hand-copied."""

import re
from pathlib import Path

import pytest

THEME = (Path(__file__).resolve().parent.parent / "frontend" / "src" / "styles" / "theme.css").read_text(
    encoding="utf-8"
)


def _block(selector: str) -> str:
    """The body of the first rule whose selector text starts with `selector`
    (nested @media handled by brace counting)."""
    start = THEME.index(selector)
    open_i = THEME.index("{", start)
    depth, i = 1, open_i + 1
    while depth:
        depth += {"{": 1, "}": -1}.get(THEME[i], 0)
        i += 1
    return THEME[open_i + 1 : i - 1]


def _vars(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", block))


LIGHT = _vars(_block(":root {"))
# The OS-preference block sits inside a @media; its own rule is the inner braces.
_media = _block("@media (prefers-color-scheme: dark)")
DARK_OS = _vars(_media)
DARK_EXPLICIT = _vars(_block(":root[data-theme='dark']"))


def _hex(value: str) -> tuple[float, float, float]:
    value = value.strip().lstrip("#")
    return tuple(int(value[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _mix(value: str) -> str:
    """Resolve `color-mix(in srgb, #a N%, #b)` to a hex colour; pass hex through."""
    m = re.fullmatch(r"color-mix\(in srgb,\s*(#\w{6})\s+(\d+)%,\s*(#\w{6})\)", value.strip())
    if not m:
        return value.strip()
    a, pct, b = _hex(m.group(1)), int(m.group(2)) / 100, _hex(m.group(3))
    mixed = [round((x * pct + y * (1 - pct)) * 255) for x, y in zip(a, b)]
    return "#%02x%02x%02x" % tuple(mixed)


def _lum(value: str) -> float:
    def chan(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (chan(c) for c in _hex(_mix(value)))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def ratio(a: str, b: str) -> float:
    hi, lo = sorted((_lum(a), _lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# (foreground token, background token, minimum): text 4.5, UI/graphics 3.
PAIRS = [
    ("fg", "bg", 4.5),
    ("fg", "card-bg", 4.5),
    ("muted", "bg", 4.5),
    ("muted", "card-bg", 4.5),
    ("muted", "tint", 4.5),
    ("accent-fg", "accent", 4.5),
    ("fill-fg", "fill", 4.5),
    ("fill-chip-fg", "fill-chip", 4.5),
    ("fill", "bg", 3.0),
    ("fill", "card-bg", 2.2),
    ("accent", "bg", 4.5),
    ("accent", "card-bg", 4.5),
    ("chip-fg", "chip-bg", 4.5),
    ("bubble-user-fg", "bubble-user", 4.5),
    ("fg", "bubble-bot", 4.5),
    ("secondary", "card-bg", 4.5),
    ("secondary", "tint", 4.5),
    ("on-hl", "hl", 4.5),
    ("toast-fg", "toast-bg", 4.5),
    ("toast-act", "toast-bg", 4.5),
    ("fg", "overlay", 4.5),
    ("muted", "overlay", 4.5),
    ("edge", "bg", 3.0),
    ("accent", "tint", 3.0),
]


@pytest.mark.parametrize("name,theme", [("light", LIGHT), ("dark", DARK_EXPLICIT)])
@pytest.mark.parametrize("fg,bg,minimum", PAIRS)
def test_contrast_pairs(name, theme, fg, bg, minimum):
    got = ratio(theme[fg], theme[bg])
    assert got >= minimum, f"{name}: {fg} on {bg} is {got:.2f}:1, needs {minimum}:1"


def test_dark_blocks_do_not_drift():
    """Compared without color-scheme, which both set; every other token must match."""
    assert DARK_OS == DARK_EXPLICIT


def test_every_light_token_is_redefined_for_dark():
    missing = set(LIGHT) - set(DARK_EXPLICIT) - {"color-scheme"}
    # tokens that are the same in both themes by design
    assert missing <= {"hl-text"}, missing


def test_night_cards_separate_from_the_page():
    # was ~1.08:1 before the Enamel palette; the raised plane must read as a step up
    assert ratio(DARK_EXPLICIT["card-bg"], DARK_EXPLICIT["bg"]) >= 1.25
