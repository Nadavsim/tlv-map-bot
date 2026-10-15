---
name: TLV Bot
description: One person's trusted Tel Aviv food and coffee list, as a warm, thumb-first chat.
colors:
  primary: "#c23f19"
  on-primary: "#ffffff"
  neutral-bg: "#fff8f2"
  neutral-fg: "#2a1b12"
  neutral-muted: "#8a5c42"
  surface: "#ffffff"
  border: "#f0dccb"
  chip-bg: "#ffede3"
  primary-night: "#c9ff3d"
  on-primary-night: "#15161a"
  neutral-bg-night: "#15161a"
  neutral-fg-night: "#f2f2ed"
  neutral-muted-night: "#9a9ca6"
  surface-night: "#1c1d22"
  border-night: "#2c2e36"
  chip-bg-night: "#23281a"
typography:
  display:
    fontFamily: "Nunito, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "2.1rem"
    fontWeight: 800
    lineHeight: 1.15
    letterSpacing: "-0.015em"
  headline:
    fontFamily: "Nunito, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "1.5rem"
    fontWeight: 800
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  title:
    fontFamily: "Nunito, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "1rem"
    fontWeight: 800
    lineHeight: 1.4
  body:
    fontFamily: "Nunito, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "0.95rem"
    fontWeight: 400
    lineHeight: 1.45
  label:
    fontFamily: "Nunito, -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    letterSpacing: "0.04em"
rounded:
  pill: "999px"
  card: "16px"
  bubble: "18px"
  bubble-tail: "4px"
  row: "12px"
  menu-item: "10px"
spacing:
  gutter: "1.1rem"
  gap-sm: "0.4rem"
  gap-md: "0.6rem"
  gap-lg: "0.7rem"
  touch-target: "44px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.pill}"
    padding: "0.7rem 1.3rem"
  button-toggle:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.neutral-muted}"
    rounded: "{rounded.pill}"
    padding: "0.5rem 0.7rem"
  button-toggle-active:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    rounded: "{rounded.pill}"
  chip-category:
    backgroundColor: "{colors.chip-bg}"
    textColor: "{colors.primary}"
    rounded: "{rounded.pill}"
    padding: "0.2rem 0.6rem"
  card-place:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.card}"
    padding: "0.8rem 1rem"
  bubble-bot:
    backgroundColor: "{colors.surface}"
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

It has two moods that share one structure. By day it is warm and vibrant - cream paper, espresso ink, a single rust accent. By night it is dark and moody - near-black surfaces with one electric lime accent. The night theme is a deliberate second direction, not a darkened copy of the day palette. In both, exactly one accent colour does all the work of saying "this is tappable" or "this is active".

It is built thumb-first for a phone held in one hand on a street corner: big targets, pill-shaped controls, short bubbles, and a header that holds only a title and a menu. Hebrew (right-to-left) is a first-class language, so the layout mirrors cleanly and nothing depends on left or right.

**Key Characteristics:**
- One accent per theme (rust by day, lime by night); never two competing colours.
- Everything tappable is a pill; containers are generously rounded cards and bubbles.
- Soft, warm-tinted depth - cards lift gently, nothing shouts.
- 44px minimum touch targets and WCAG AA contrast, including the muted text.
- Logical (not physical) directions throughout, so right-to-left works for free.

## Colors

A warm cream-and-rust day palette and a near-black-and-lime night palette, each reduced to one accent, one ink, one muted ink, a surface, a hairline border and a tinted chip fill. The frontmatter holds the day values under plain names and the night values under `-night` names; at runtime both are CSS custom properties (`--bg`, `--fg`, `--muted`, `--accent`, `--card-bg`, `--border`, `--chip-bg` ...) and components only ever read the variables.

### Primary
- **Rust** (#c23f19): the day accent - active toggles, the user's own bubbles, the primary Send/Set pill, links, the title's pin icon, category chips' text. Darkened from the original brighter orange so white text on it clears 4.5:1.
- **Electric Lime** (#c9ff3d): the night accent in the same roles, with near-black (#15161a) text on top of it.

### Neutral
- **Warm Cream** (#fff8f2): the day page background.
- **Espresso** (#2a1b12): day body text.
- **Clay** (#8a5c42): day muted text - location status, distance and travel time, tag chips. Chosen to hold about 5.4:1 on the cream; do not lighten it.
- **Paper White** (#ffffff): day cards and bot bubbles.
- **Warm Hairline** (#f0dccb): day borders and dividers.
- **Blush Tint** (#ffede3): the day chip and hover-row fill.
- **Ink Black** (#15161a): the night page background.
- **Chalk** (#f2f2ed): night body text.
- **Slate Mist** (#9a9ca6): night muted text.
- **Charcoal Card** (#1c1d22): night cards and bot bubbles.
- **Graphite Hairline** (#2c2e36): night borders.
- **Moss Tint** (#23281a): the night chip fill, a lime-tinted dark.

### Named Rules
**The One Accent Rule.** Each theme has exactly one accent. It marks what is active or tappable and is never used as decoration. If something needs to be quieter, drop to the muted ink, not to a second colour.

**The Contrast Floor Rule.** Muted text is information (distances, times, status), so it must stay at 4.5:1 or better on its background in both themes. Lightening `--muted` to look softer is a regression.

## Typography

**Display Font:** Nunito (with the system UI stack as fallback)
**Body Font:** Nunito (same family)
**Label/Mono Font:** none - labels are Nunito at small sizes and heavier weights

**Character:** A single rounded humanist sans, used in a few confident weights. Its friendly, slightly rounded terminals are what make the interface read as a person talking rather than a tool. Nunito has no Hebrew glyphs, so Hebrew falls through to the system font; the layout is built so that doesn't matter.

### Hierarchy
- **Display** (800, 2.1rem, 1.15): page titles on the standalone About, Privacy and 404 pages.
- **Headline** (800, 1.5rem, tight -0.02em tracking): the app title in the header, with its pin icon.
- **Title** (800, 1rem): a place's name on its card.
- **Body** (400-600, 0.95rem, 1.45): chat bubbles; user bubbles are 600. Standalone pages use 1rem at 1.65 and a 600px measure.
- **Label** (700, 0.75-0.85rem): chips, toggles, pills, links; section headings in the drawer are 800 at 0.7rem, uppercase, 0.04em tracking.

### Named Rules
**The Few Weights Rule.** 400 for reading, 600 for the user's own words, 700 for controls, 800 for names and titles. Do not introduce a fifth weight.

## Layout

A single centered column, 560px at most, filling the viewport height exactly: a pinned header, a scrolling chat log, and a pinned composer, so messages scroll without the page growing. Side gutters are 1.1rem; vertical rhythm inside the log is 0.7rem between messages and 0.6rem between cards.

The header carries only the title and one menu button - everything else (language, theme, new conversation, help, account, saved addresses, favorites) lives in a slide-out drawer anchored to the inline end edge. This is structural: it prevents the header overflowing on narrow phones no matter how many controls are added later. Result cards are capped at 85% of the log so a conversation still reads as two sides.

Spacing is a small set of rem steps (0.4 / 0.5 / 0.6 / 0.7) with 44px as the floor for any target. Right-to-left is handled with logical properties and `dir`, never with mirrored hard-coded left/right values.

## Elevation & Depth

Depth is soft and ambient, a hybrid of a hairline border and a gentle shadow. A card sits on a 1.5px border for definition and a light shadow for lift; on hover the shadow deepens slightly. Shadows are never pure black in the day theme - they are tinted warm so they sit on cream without looking grey. In the night theme a faint top highlight and a deeper shadow give a glassy edge against the near-black page.

### Shadow Vocabulary
- **Rest** (`--shadow-sm`, day: `0 1px 2px rgba(42,27,18,.06), 0 4px 10px rgba(255,90,54,.08)`; night: `inset 0 1px 0 rgba(255,255,255,.04), 0 4px 12px rgba(0,0,0,.35)`): bubbles and place cards.
- **Lift** (`--shadow-md`, day: `0 2px 4px rgba(42,27,18,.07), 0 8px 20px rgba(255,90,54,.12)`; night: `inset 0 1px 0 rgba(255,255,255,.05), 0 8px 24px rgba(0,0,0,.45)`): card hover and the slide-out drawer.

### Named Rules
**The Warm Shadow Rule.** Shadows are tinted to the palette, never neutral black on cream. Depth signals "this surface is touchable", not drama.

## Shapes

Soft and round. Controls are full pills (999px); cards are 16px; chat bubbles are 18px with one 4px corner as a "tail" on the side the speaker sits; list rows and drawer items are 10-12px. Borders are 1.5px hairlines. The circular avatar and the numbered map pins are the only true circles.

### Named Rules
**The Pill Rule.** Anything you can press is a pill. Containers (cards, bubbles, panels) are rounded rectangles. Do not mix square controls into the set.

**The Logical Corner Rule.** The bubble tail uses logical corner radii (`border-end-start` / `border-end-end`) so it stays on the speaker's side under right-to-left.

## Components

Soft, tactile pills: friendly, thumb-first, with a small press-scale rather than any dramatic hover.

### Buttons
- **Shape:** full pill (999px).
- **Primary (Send / Set / Save):** accent fill with the on-accent text, 0.7rem 1.3rem, weight 800. Hover brightens slightly (`brightness(1.08)`); press scales to 0.96.
- **Toggle (Custom/Live, Walk/Drive):** two equal pills in a row; inactive is a surface pill with a hairline border and muted text, active fills with the accent. One toggle row is never wider than the screen.
- **Ghost / link pills (Navigate, Instagram, Save a favorite):** blush-tint fill with accent text, 0.8rem bold, pressing scales slightly. Quiet icon-only controls (the speech-bubble feedback button) are transparent with muted ink and gain a tint on hover.
- **Focus:** one ring for every control - a 3px accent ring at 35% via `color-mix`, applied with `:focus-visible` only.

### Chips
- **Category chip:** blush-tint pill, accent text, 0.75rem bold, a 12px lucide icon before the word.
- **Info chips (price, hours, outdoor, tags):** transparent with a 1.5px hairline border and muted text; each kind has its own small icon so it reads as a different fact, not another tag.

### Cards / Containers
- **Place card:** surface fill, 16px corners, 1.5px hairline, rest shadow lifting to the lift shadow on hover, 0.8rem 1rem padding. Name in 800, then chips, then the distance and travel time (kept left-to-right), then the action pills.
- **Chat bubbles:** bot bubbles are surface with a hairline; the user's are solid accent. Both are capped at 85% width and fade in with a 6px rise.

### Inputs / Fields
- **Style:** pill (999px), surface fill, 1.5px hairline, 0.7rem 1rem, placeholder truncated with an ellipsis rather than clipped.
- **Focus:** the border shifts to the accent and the standard 3px ring appears.

### Navigation
- **Header:** the title with its pin icon and a single 44px menu button; below it the location status line and the two toggle rows.
- **Drawer:** a 300px (85vw max) panel from the inline end edge with a dimmed backdrop; labelled full-width rows; the account section pinned to the bottom. Escape and the backdrop close it.

### Result map
A 260px Leaflet map opened on demand below a result block, with numbered pin badges matching the cards and a ringed dot for the user. Its container is pinned left-to-right even in Hebrew, and any override of Leaflet's own styles needs strictly higher specificity than Leaflet's.

## Do's and Don'ts

### Do:
- **Do** use only the CSS variables for colour so both themes and the user's explicit toggle work everywhere.
- **Do** keep every target at least 44px, growing the hit area with padding or min-size rather than enlarging the icon.
- **Do** put new controls in the drawer, not the header.
- **Do** use logical properties (`inset-inline-end`, `margin-inline-start`, `border-end-start-radius`) so Hebrew mirrors correctly.
- **Do** keep icons to lucide at one stroke width (2.5), `currentColor`, with an `aria-hidden` icon next to a visible label.
- **Do** give distance and travel time `dir="ltr"` - they are always digits and Latin units.

### Don't:
- **Don't** add a second accent colour or use the accent as decoration.
- **Don't** use a pure-black shadow on the cream background.
- **Don't** lighten the muted ink below AA contrast to make things look softer.
- **Don't** add `dir="auto"` to place cards or their names; it makes cards in one list flip layout depending on each name's script. Chat bubbles are the only place it belongs.
- **Don't** re-skin Google's sign-in button; its content and look are Google's.
- **Don't** use emoji as icons or add brand/logo glyphs (lucide has none by design).
- **Don't** make a feedback or report control loud - it is for the occasional stale pin, so it stays muted until hovered.
