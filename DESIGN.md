---
name: TLV Bot
description: One person's trusted Tel Aviv food and coffee list, as an enamel-sign chat that answers "how far" first.
colors:
  primary: "#0b57a4"
  on-primary: "#ffffff"
  neutral-bg: "#edf2f0"
  neutral-fg: "#0c2237"
  neutral-muted: "#486074"
  surface: "#ffffff"
  tint: "#dfe8e5"
  divider: "#d2ddd9"
  chip-bg: "#dce9f7"
  chip-fg: "#0a3f78"
  watermelon: "#b91f47"
  lemon: "#ffcb3d"
  on-lemon: "#0c2237"
  primary-night: "#6fa3ec"
  on-primary-night: "#07223f"
  fill-night: "#2a64bd"
  on-fill-night: "#e6eef8"
  neutral-bg-night: "#091a2b"
  neutral-fg-night: "#d6e2ee"
  neutral-muted-night: "#94a9be"
  surface-night: "#16314d"
  tint-night: "#10263d"
  overlay-night: "#1c3a5a"
  divider-night: "#24496e"
  chip-bg-night: "#1e4268"
  chip-fg-night: "#c3daf9"
  watermelon-night: "#ff7c9c"
  lemon-night: "#ffd04a"
typography:
  display:
    fontFamily: "Rubik, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Noto Sans Hebrew, sans-serif"
    fontSize: "clamp(1.55rem, 7vw, 2rem)"
    fontWeight: 800
    lineHeight: 1.12
  headline:
    fontFamily: "Rubik, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Noto Sans Hebrew, sans-serif"
    fontSize: "2.1rem"
    fontWeight: 800
    lineHeight: 1.15
    letterSpacing: "-0.015em"
  title:
    fontFamily: "Rubik, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Noto Sans Hebrew, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: "Rubik, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Noto Sans Hebrew, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Rubik, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Noto Sans Hebrew, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 600
rounded:
  tag: "8px"
  plate: "12px"
  panel: "14px"
  bubble: "18px"
  card: "20px"
  pill: "999px"
spacing:
  gutter: "1.1rem"
  gap-sm: "0.4rem"
  gap-md: "0.6rem"
  gap-lg: "0.75rem"
  touch-target: "44px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.pill}"
    padding: "0.7rem 1.3rem"
  segmented-track:
    backgroundColor: "{colors.tint}"
    rounded: "{rounded.pill}"
    padding: "3px"
  segmented-thumb:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.pill}"
    height: "40px"
  sign-plate:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.plate}"
    padding: "0.45rem 0.7rem"
  hero-plate:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.card}"
    padding: "0.95rem 1.1rem"
  chip-category:
    backgroundColor: "{colors.chip-bg}"
    textColor: "{colors.chip-fg}"
    rounded: "{rounded.tag}"
    padding: "0.2rem 0.6rem"
  tag-info:
    backgroundColor: "{colors.tint}"
    textColor: "{colors.neutral-muted}"
    rounded: "{rounded.tag}"
    padding: "0.2rem 0.6rem"
  tag-outdoor:
    backgroundColor: "{colors.lemon}"
    textColor: "{colors.on-lemon}"
    rounded: "{rounded.tag}"
    padding: "0.2rem 0.6rem"
  card-place:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.neutral-fg}"
    rounded: "{rounded.card}"
    padding: "0.9rem 1rem"
  bubble-bot:
    backgroundColor: "{colors.tint}"
    textColor: "{colors.neutral-fg}"
    rounded: "{rounded.bubble}"
    padding: "0.65rem 0.95rem"
  bubble-user:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.bubble}"
    padding: "0.65rem 0.95rem"
  input-text:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.neutral-fg}"
    rounded: "{rounded.pill}"
    padding: "0.7rem 1rem"
---

# Design System: TLV Bot

## Overview

**Creative North Star: "The Friend's List"**

This is the list a friend who knows the city would hand you, not a review site. The interface is a chat, a single column that reads like messages from one person, and every surface is soft, rounded and unhurried. Warmth and trust come first: the product's whole claim is *one person's list, not crowd reviews*, so nothing here should feel like a dashboard, a marketplace or an ad.

The look is **Enamel**: Tel Aviv's street signs and plaster walls. By day the page is pale plaster-green (#edf2f0) with deep-ink text and one enamel blue; by night it is a deep sea blue (#091a2b), not near-black. The blue is used as a *sign*: a solid plate that carries the single most useful fact. On a result card that is the distance and travel time; on the start screen it is the greeting; in the drawer it is the wordmark. Everything else stays quiet so the plate can answer first. The two themes share one structure and are tuned separately, so night is a calmer set of blues with softened whites rather than an inverted day.

It is built thumb-first for a phone held in one hand on a street corner: big targets, pill-shaped controls, short bubbles, and a header that holds only a title and a menu. Hebrew (right-to-left) is a first-class language, so layout, motion and the segmented thumb all mirror and nothing depends on left or right.

**Key Characteristics:**
- Three roles for colour, nothing else: blue acts and answers; watermelon means "mine"; lemon is a rare fill.
- Surfaces are separated by fill and soft shadow, not outlines; only form fields keep a real edge.
- Everything pressable is a pill; everything you cannot press is a rectangle (8px tags, 12px plate, 20px cards).
- One signature moment of motion (results arriving in rank order); the rest is a response to touch.
- 44px minimum targets and WCAG AA contrast in both themes, enforced by a test.
- Logical (not physical) directions throughout, so right-to-left works for free.

## Colors

An enamel-blue-and-plaster day palette and a deep-sea night palette. The frontmatter holds day values under plain names and night values under `-night` names; at runtime both are CSS custom properties in `frontend/src/styles/theme.css` (`--bg`, `--fg`, `--muted`, `--accent`, `--fill`, `--card-bg`, `--tint`, `--secondary`, `--hl` ...) and components only read the variables. Night uses a **lighter blue for text and rings** (`--accent`) and a **deeper blue for solid blocks** (`--fill`) so a filled plate is never dark-on-light blue.

### Primary
- **Enamel Blue** (#0b57a4): the day accent and fill. Solid plates, the selected segment, the user's bubbles, Send/Set, links and rings. White text on it clears 7:1.
- **Sky Blue** (#6fa3ec): the night accent, used only for text, links and rings on dark.
- **Deep Night Blue** (#2a64bd, text #e6eef8): the night fill for solid blocks - plate, hero, segment, your bubbles. Deliberately not the light accent, and the text is a soft off-white, not pure white.

### Secondary
- **Watermelon** (#b91f47; night #ff7c9c): "mine" - the saved heart and delete. It marks a person's own things and nothing else.

### Tertiary
- **Lemon** (#ffcb3d; night #ffd04a): a fill only, at most one per card (the Outdoor tag) plus the queued-craving chip and toast action. Never body text on the page and never a button.

### Neutral
- **Plaster** (#edf2f0) / **Deep Sea** (#091a2b): the page.
- **Ink** (#0c2237) / **Mist Ink** (#d6e2ee): body text.
- **Slate** (#486074) / **Harbour Grey** (#94a9be): muted text - distances' labels, status, tags.
- **White** (#ffffff) / **Harbour Card** (#16314d): cards.
- **Tint** (#dfe8e5) / **Deep Tint** (#10263d): the quiet fill under bot bubbles, tags and panels.
- **Overlay** (#ffffff) / **Raised Harbour** (#1c3a5a): the drawer.
- **Divider** (#d2ddd9) / **Night Divider** (#24496e): rules between drawer sections only.
- **Chip Blue** (#dce9f7, text #0a3f78) / (#1e4268, text #c3daf9): the category chip and action pills.

### Named Rules
**The Three Roles Rule.** Blue acts or answers, watermelon means "mine", lemon is a fill and nothing more. A fourth hue, or a role used for decoration, is a mistake.

**The Contrast Floor Rule.** Every text and UI pair stays at its WCAG floor in both themes (4.5:1 text, 3:1 UI), including muted text. `tests/test_theme_contrast.py` fails the build if one slips; softening a colour means re-running it.

**The Soft White Rule.** At night nothing is pure white: ink is #d6e2ee and text on fills is #e6eef8. Bright whites on a dark page read as glare.

## Typography

**Display Font:** Rubik (with the system UI stack as fallback)
**Body Font:** Rubik (same family)
**Label/Mono Font:** none - labels are Rubik at small sizes and heavier weights

**Character:** One rounded geometric sans in a few confident weights. Rubik covers Latin and Hebrew in one family, so Hebrew gets the same voice as English.

### Hierarchy
- **Display** (800, clamp 1.55-2rem, 1.12): the start screen headline.
- **Headline** (800, 2.1rem, tight tracking): page titles on the standalone About, Privacy and 404 pages.
- **Title** (700, 1.125rem, 1.25): a place's name on its card. The plate's distance is 800 at 1.05rem.
- **Body** (400, 1rem, 1.45): chat bubbles and inputs (16px, so iOS never zooms). Standalone pages use 1rem at 1.65 and a 600px measure.
- **Label** (600-700, 0.8125-0.85rem): tags, chips, toggles, plate travel time, links.

### Named Rules
**The Few Weights Rule.** 400 for reading, 600 for secondary facts, 700 for controls and names, 800 for headlines and the plate's distance. No fifth weight.

## Layout

A single centered column, 560px at most, filling the viewport height exactly: a pinned header, a scrolling chat log, and a pinned composer. Side gutters are 1.1rem; rhythm in the log is 0.7rem between messages and 0.6rem between cards. **Result cards run the full width of the column**; bubbles stay at 85% so a conversation still reads as two sides.

The header carries a title and one menu button, then the location status line and two segmented controls. Everything else (language, theme, new conversation, help, About, Privacy, account, saved addresses, favorites) lives in a slide-out drawer on the inline end edge. The **start screen** is a blue plate with a headline, a one-line pitch and three craving chips, with the location form directly below and the composer pinned under it; at 375x667 it fits without scrolling beyond ~10px. About and Privacy sit at the bottom of the start screen and in the drawer, never in a permanent footer. The standalone pages share a sticky bar (wordmark plate, 44px "Back" pill) over one raised sheet; the 404 is a sign plate.

Spacing is a small set of rem steps with 44px as the floor for any target. Right-to-left is handled with logical properties and `dir`, never with mirrored hard-coded left/right values.

## Elevation & Depth

Depth is **soft and ambient**, and structural: there are no card or bubble outlines. A card separates from the page by being a lighter fill with a low shadow; bot bubbles are a flat tint with no shadow; the drawer and toast are one step higher. Shadows are neutral black at low opacity (never a coloured glow).

### Shadow Vocabulary
- **Rest** (`--shadow-sm`, day: `0 1px 2px rgb(0 0 0 / .06), 0 8px 20px -6px rgb(0 0 0 / .12)`; night: `0 10px 24px -12px rgb(0 0 0 / .6)`): cards, the segmented thumb, option pills.
- **Raised** (`--shadow-md`, day: `0 12px 40px -8px rgb(0 0 0 / .28)`; night: `0 16px 48px -8px rgb(0 0 0 / .65)`): the drawer.
- **Selected ring** (`0 0 0 2px var(--accent)` over the rest shadow): a card picked from its map pin.

### Named Rules
**The Fill-Not-Line Rule.** Separate surfaces with fill and shadow. The only real edges are form fields (3:1 against the page, because a shadow is not a boundary) and drawer dividers; in forced-colors mode borders return everywhere.

## Shapes

Soft and round, with one rule for what is pressable. Controls are full pills (999px); cards and the start plate are 20px; the sign plate is 12px; reply panels 14px; chat bubbles 18px with one tail corner on the speaker's side; tags are 8px rectangles. The avatar and numbered map pins are the only true circles.

### Named Rules
**The Press Rule.** A rectangle you cannot press, a pill you can. Tags and the plate are rectangles; buttons, chips you tap and segments are pills. Do not mix them.

**The Logical Corner Rule.** The bubble tail uses logical corner radii so it stays on the speaker's side under right-to-left.

## Components

Soft, tactile pills around one blue sign: friendly, thumb-first, with a small press-scale rather than hover theatrics.

### Buttons
- **Primary (Send / Set):** blue fill, on-fill text, 0.7rem 1.3rem pill, weight 800; press scales to 0.97 (a dim at reduced motion).
- **Segmented control (Custom/Live, Walk/Drive):** one tinted pill track with a blue thumb that glides to the chosen option (data-driven, mirrored in RTL); 40px segments inside a 3px track. The label of the chosen option is on-fill, the other muted.
- **Action pills (Navigate, Instagram, Save):** chip-blue fill with accent text; a saved heart turns watermelon on a tint.
- **Report button:** a quiet speech-bubble icon, transparent until hovered; opens a tint panel with raised option pills (44px).
- **Focus:** one solid 2px accent outline with a 2px offset on everything; inputs add an accent border.

### Chips and Tags
- **Category chip:** chip-blue rectangle (8px), chip text, a 12px lucide icon.
- **Info tags (price, hours, tags):** tint rectangle with muted text; **Outdoor** is the one lemon tag.

### Cards / Containers
- **Place card:** full width, white (night: harbour card), 20px, no border, rest shadow. A head row (name left, **sign plate** at the trailing edge), then tags, then action pills. The plate is a 12px blue block with a thin inner rule: distance in 800, travel time beneath in 600 (a fixed-size pulse while it loads). Distance and time are always left-to-right.
- **Chat bubbles:** bot bubbles are a flat tint; the user's are solid blue with on-fill text. Both 85% wide.
- **Start plate:** the hero - a 20px blue plate with a headline, a pitch, craving chips (inverse pills; a tapped-before-location chip turns lemon), and a hint.

### Inputs / Fields
- **Style:** pill, surface fill, a real 1.5px edge (the one place a line stays), 16px text, placeholder truncated with an ellipsis.

### Navigation
- **Header:** title with its pin icon and a 44px menu button.
- **Drawer:** 300px (85vw max) from the inline end edge on the overlay surface over a flat scrim; a wordmark plate and the curator's one-line promise at the top; labelled rows (46px); account, favorites and saved addresses pinned below.

### Result map
A 260px Leaflet map opened on demand below a result block, numbered pins matching the cards, a ringed dot for the user; pinned left-to-right even in Hebrew. Any override of Leaflet's own styles needs strictly higher specificity than Leaflet's, never equal.

### Motion
Arrive in order, answer on contact, then hold still. Distances, scales and durations are tokens at the top of `App.css`; `prefers-reduced-motion` zeroes the travel and scale tokens and everything becomes a short fade.
- **The signature:** a reply arrives as bubble, then the first three cards rising in rank order (460ms, 70ms stagger, batch-relative so "Show more" staggers only its new cards), then the action buttons fade, then travel times settle into the plate.
- **Responses:** bubbles grow from their tail corner; the segmented thumb glides (300ms, snaps under reduced motion); the drawer slides in 340ms and leaves in 180ms; the heart dips on press; panels, the toast and the map mount with a short rise or fade.
- **Never:** bounce or overshoot, animated layout, blurred backdrops, or looping decoration (the typing dots and the loading pulse are the only loops).

## Do's and Don'ts

### Do:
- **Do** use only the CSS variables for colour so both themes and the user's explicit toggle work everywhere; use `--fill`/`--fill-fg` for solid blocks and `--accent` for text and rings.
- **Do** keep every target at least 44px, growing the hit area with padding or min-size rather than enlarging the icon.
- **Do** put new controls in the drawer, not the header, and links like About/Privacy in the drawer or start screen, not a footer.
- **Do** use logical properties (`inset-inline-end`, `margin-inline-start`, `border-end-start-radius`) and `--dir` for any directional transform so Hebrew mirrors.
- **Do** take every animation distance and scale from the motion tokens so reduced motion stays one block of overrides.
- **Do** re-run `tests/test_theme_contrast.py` after touching a colour.
- **Do** keep icons to lucide at one stroke width (2.5), `currentColor`, with an `aria-hidden` icon beside a visible label.

### Don't:
- **Don't** add a fourth hue or use watermelon or lemon as decoration; lemon is never body text or a button.
- **Don't** outline cards or bubbles; separate them with fill and shadow.
- **Don't** use a coloured glow or coloured shadow, or any `backdrop-filter`/blur.
- **Don't** use pure white on the night page; keep the soft whites.
- **Don't** animate width, height, padding or margin. Transform and opacity only.
- **Don't** add `dir="auto"` to place cards or their names; it makes cards in one list flip layout depending on each name's script. Chat bubbles are the only place it belongs.
- **Don't** re-skin Google's sign-in button; its look is Google's, and the script it injects can trip layout-animation detectors that are not ours.
- **Don't** run `prettier` over the frontend: the repo has no config and it reformats whole files.
- **Don't** use emoji as icons or add brand/logo glyphs (lucide has none by design).
- **Don't** make a report control loud - it is for the occasional stale pin.
