# Rich Text Editor Design

**Date:** 2026-03-23
**Status:** Design
**Depends on:** Interaction system (built), SceneMessage deprecation (done)

## Problem Statement

The current compose experience is a plain textarea. Players type raw text with no
formatting support. For a game where writing is the core experience, this feels dated
compared to Discord, F-list, and other modern chat platforms. Players expect bold,
italic, color, and spell checking as baseline features.

## Design Philosophy

The editor should feel like Discord's text input — players who know markdown can type
it directly, but most players use keyboard shortcuts (Ctrl+B) or toolbar buttons.
The formatting syntax is the storage format, not the primary input method. Content is
stored as plain text with formatting markers. No backend changes to the Interaction
model needed.

## Formatting Syntax

### Text Formatting (Markdown-style)

| Syntax | Rendered As | Shortcut |
|--------|------------|----------|
| `**bold**` | **bold** | Ctrl+B |
| `*italic*` | *italic* | Ctrl+I |
| `~~strikethrough~~` | ~~strikethrough~~ | Ctrl+Shift+S |
| URLs (auto-detected) | Clickable link | (automatic) |

### Color Codes (MU-style with xterm-256)

Named shortcuts for the 16 basic ANSI colors:

| Code | Color | Code | Color |
|------|-------|------|-------|
| `\|r` | Red | `\|R` | Bright Red |
| `\|g` | Green | `\|G` | Bright Green |
| `\|b` | Blue | `\|B` | Bright Blue |
| `\|y` | Yellow | `\|Y` | Bright Yellow |
| `\|c` | Cyan | `\|C` | Bright Cyan |
| `\|m` | Magenta | `\|M` | Bright Magenta |
| `\|w` | White | `\|W` | Bright White |
| `\|x` | Grey | `\|X` | Dark Grey |
| `\|n` | Reset to default | | |

Full xterm-256 palette: `|[0]` through `|[255]`

Example: `**She draws her blade** with a |[196]fierce|n determination.`

### What Is NOT Supported

- Headers (#, ##, etc.)
- Code blocks
- Images / embeds
- Spoiler tags
- Character mentions (command-level concern, not body text)
- Nested formatting beyond one level
- Any HTML

## Color System

### Storage

All colors stored as xterm-256 index codes. Named shortcuts (`|r`, `|b`, etc.) are
syntactic sugar that map to specific indices.

### Lookup Table

A shared xterm-256 → hex lookup table maps all 256 indices to CSS hex colors.
This table is used by:
- Frontend renderer (xterm index → hex → CSS `color` property)
- Color picker (hex from click position → nearest xterm index for storage)
- Future telnet renderer (xterm codes render natively, no conversion needed)

The table is a static JSON/TypeScript constant — no database, no API call. Both
frontend and (if needed) backend can import it.

### Color Picker UI

The toolbar includes a color button that opens a picker with two sections:

1. **Curated swatches** — 30-40 colors organized by tone (warm, cool, earth,
   metallic, magical). These are the most commonly used RP colors. Quick single-click.
2. **Full color wheel** — For custom colors. The picker snaps the selected color
   to the nearest xterm-256 index. Shows the hex preview and the xterm index.

When a color is selected, the editor inserts `|[index]` before the selection (or
cursor) and `|n` after. If text is selected, it wraps the selection.

## Editor Component

### Architecture

Replace the plain `<Textarea>` in `CommandInput.tsx` with a new `<RichTextInput>`
component. This is still fundamentally a textarea (not a contentEditable div or
Slate/Tiptap block editor) — it stores and shows the raw text with formatting
markers. The "rich" part is:

1. **Toolbar** — Buttons for Bold, Italic, Strikethrough, Color. Each inserts
   formatting markers around the current selection.
2. **Keyboard shortcuts** — Ctrl+B/I/Shift+S insert markers around selection.
3. **Spell check** — `spellCheck={true}` on the textarea (browser-native).
4. **Live preview** (optional) — A small preview area below the textarea showing
   how the text will render. Not MVP — can be added later.

### Toolbar Behavior

When the player clicks Bold with text selected:
- `hello world` with "world" selected → `hello **world**`

When clicked with no selection:
- Inserts `****` and places cursor between the asterisks

Color button:
- Opens the color picker
- Player selects a color
- If text selected: wraps with `|[index]...|n`
- If no selection: inserts `|[index]|n` and places cursor between

### Preserved Behavior

- Enter to submit (sends the raw text, including formatting markers)
- Shift+Enter for newline
- Arrow Up for command history
- All existing `CommandInput` functionality

## Rendering Component

### `<FormattedContent>`

A React component used everywhere interactions are displayed:

```tsx
<FormattedContent content={interaction.content} />
```

Parses the raw text and renders formatted output:

1. **Color codes** — `|[n]...|n` and `|r...|n` → `<span style="color: #hex">`
2. **Bold** — `**...**` → `<strong>`
3. **Italic** — `*...*` → `<em>`
4. **Strikethrough** — `~~...~~` → `<del>`
5. **URLs** — Auto-detected → `<a href="..." target="_blank" rel="noopener">`
6. **Plain text** — Everything else → text nodes

### Parser Rules

- Parsing is single-pass, left-to-right
- Color codes take priority over markdown (a color code inside bold is valid)
- Markdown formatting cannot span multiple lines (prevents runaway formatting)
- Unmatched markers render as literal text (a stray `*` is just an asterisk)
- URLs must start with `http://` or `https://` (no bare domain detection)
- No nested bold-in-bold or italic-in-italic
- Maximum color nesting: one level (no color inside color — inner wins)
- The reset code `|n` always returns to the default text color

### Security

- No HTML is ever parsed or rendered from content
- All output uses React's JSX (auto-escaped)
- URLs are validated before rendering as `<a>` tags
- The parser produces React elements, never `dangerouslySetInnerHTML`

## Where FormattedContent Is Used

- Scene interaction feed (`SceneMessages.tsx`)
- Interaction detail views
- Relationship update references
- Favorited interaction display
- Scene summary display
- Any future view that shows interaction content

## Implementation Plan

### Phase 1: FormattedContent Renderer
- xterm-256 lookup table (static TypeScript constant)
- Parser function that tokenizes content into segments
- `<FormattedContent>` React component
- Tests for all formatting edge cases

### Phase 2: RichTextInput Editor
- `<RichTextInput>` component wrapping textarea
- Toolbar with Bold/Italic/Strikethrough buttons
- Keyboard shortcuts (Ctrl+B/I/Shift+S)
- Selection wrapping logic
- Spell check enabled

### Phase 3: Color Picker
- Color picker component (curated swatches + wheel)
- Color button in toolbar
- Snap-to-nearest-xterm-256 logic
- Integration with RichTextInput

### Phase 4: Integration
- Replace `CommandInput`'s textarea with `RichTextInput`
- Replace raw `<p>{content}</p>` in SceneMessages with `<FormattedContent>`
- Update WebSocket payload rendering to use FormattedContent

## Open Questions

1. **Live preview while typing?** — A small preview below the textarea showing
   rendered output. Adds complexity but helps players see what others will see.
   Probably not MVP — add when players ask for it.

2. **Should the color wheel be a full HSL picker or a grid of the 256 xterm
   colors?** Grid is simpler and guarantees exact matches. Wheel is prettier
   but needs snap-to-nearest logic. Recommendation: curated swatches for MVP,
   full picker later.

3. **Toolbar position** — Above the textarea (like Discord) or floating near
   selection (like Google Docs)? Above is simpler and more predictable.
   Recommendation: above.

4. **Mobile** — Toolbar buttons need to be touch-friendly. The textarea approach
   works well on mobile since it's native input. Keyboard shortcuts won't work
   on mobile — toolbar buttons are the only option.
