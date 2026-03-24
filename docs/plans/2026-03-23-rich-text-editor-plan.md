# Rich Text Editor Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the plain textarea in CommandInput with a rich text compose experience
featuring bold/italic/strikethrough toolbar, xterm-256 color codes with a color picker,
browser spell check, and a FormattedContent renderer for displaying formatted interactions.

**Architecture:** Pure frontend — no backend changes. Content stored as plain text with
markdown and MU-style color markers. A `FormattedContent` component parses and renders
the markers. A `RichTextInput` component wraps a textarea with a toolbar that inserts
markers around selected text. An xterm-256 lookup table maps color indices to hex.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Radix UI, Vitest

**Design doc:** `docs/plans/2026-03-23-rich-text-editor-design.md`

**Key conventions:**
- Functional components with TypeScript interfaces
- Radix UI for popovers/dropdowns
- Tailwind for styling
- Vitest for tests
- Run: `pnpm --dir frontend test -- --run`
- Run: `pnpm --dir frontend typecheck && pnpm --dir frontend lint`

---

## Task 1: xterm-256 Color Lookup Table

**Files:**
- Create: `frontend/src/lib/xterm256.ts`
- Test: `frontend/src/lib/__tests__/xterm256.test.ts`

Create a static lookup table mapping all 256 xterm color indices to hex values.
Also map the named MU color shortcuts to their indices.

```typescript
// The full 256-color table
export const XTERM_TO_HEX: Record<number, string> = {
  0: '#000000',   // Black
  1: '#800000',   // Red
  2: '#008000',   // Green
  // ... all 256 entries
  255: '#eeeeee', // Grey93
};

// Named MU color shortcuts → xterm index
export const MU_COLOR_NAMES: Record<string, number> = {
  'r': 1,    // Red
  'R': 9,    // Bright Red
  'g': 2,    // Green
  'G': 10,   // Bright Green
  'b': 4,    // Blue
  'B': 12,   // Bright Blue
  'y': 3,    // Yellow
  'Y': 11,   // Bright Yellow
  'c': 6,    // Cyan
  'C': 14,   // Bright Cyan
  'm': 5,    // Magenta
  'M': 13,   // Bright Magenta
  'w': 7,    // White
  'W': 15,   // Bright White
  'x': 8,    // Grey
  'X': 0,    // Black/Dark
};

/** Get hex color for an xterm-256 index. Returns undefined for invalid indices. */
export function xtermToHex(index: number): string | undefined {
  return XTERM_TO_HEX[index];
}

/** Get hex color for a named MU color shortcut. */
export function muColorToHex(name: string): string | undefined {
  const index = MU_COLOR_NAMES[name];
  return index !== undefined ? XTERM_TO_HEX[index] : undefined;
}

/** Find the nearest xterm-256 index for a given hex color. */
export function hexToNearestXterm(hex: string): number {
  // Parse hex to RGB, find closest match by Euclidean distance
  // in the 256-color palette
}
```

The full 256-color table values are well-documented. Use the standard xterm color
chart (colors 0-7 standard, 8-15 bright, 16-231 6x6x6 RGB cube, 232-255 grayscale).

Tests:
- Known colors map correctly (index 1 = red, index 196 = bright red, etc.)
- Named shortcuts map correctly (|r → index 1 → #800000)
- hexToNearestXterm finds closest match
- Invalid indices return undefined

Commit: `feat(frontend): add xterm-256 color lookup table`

---

## Task 2: Content Parser

**Files:**
- Create: `frontend/src/lib/formatParser.ts`
- Test: `frontend/src/lib/__tests__/formatParser.test.ts`

A parser that tokenizes formatted content into an array of typed segments:

```typescript
interface TextSegment {
  type: 'text';
  content: string;
}

interface BoldSegment {
  type: 'bold';
  content: string;
}

interface ItalicSegment {
  type: 'italic';
  content: string;
}

interface StrikethroughSegment {
  type: 'strikethrough';
  content: string;
}

interface ColorSegment {
  type: 'color';
  hex: string;
  content: string;
}

interface LinkSegment {
  type: 'link';
  url: string;
  content: string;
}

type Segment = TextSegment | BoldSegment | ItalicSegment | StrikethroughSegment
  | ColorSegment | LinkSegment;

export function parseFormattedContent(text: string): Segment[] {
  // Single-pass left-to-right parser
  // Priority: color codes > bold > italic > strikethrough > links > plain text
  // Color: |[123]text|n or |rtext|n
  // Bold: **text**
  // Italic: *text* (but not inside **)
  // Strikethrough: ~~text~~
  // URLs: https?://...
  // Unmatched markers → plain text
  // No multi-line spanning for markdown markers
}
```

Tests (comprehensive — this is the core logic):
- Plain text passthrough
- Bold: `**hello**` → BoldSegment
- Italic: `*hello*` → ItalicSegment
- Strikethrough: `~~hello~~` → StrikethroughSegment
- Color named: `|rhello|n` → ColorSegment with red hex
- Color indexed: `|[196]hello|n` → ColorSegment with index 196 hex
- URL: `https://example.com` → LinkSegment
- Mixed: `**bold** and *italic*` → [Bold, Text, Italic]
- Unmatched `*` → plain text
- Unmatched `**` → plain text
- Color without reset → color extends to end of text
- Nested: `**|rbold red|n**` → Bold wrapping Color (or Color wrapping Bold — define priority)
- Empty markers: `****` → plain text
- Multiple colors: `|rred|n and |bblue|n`
- Multi-line: formatting does NOT span newlines for markdown (color CAN span)

Commit: `feat(frontend): add formatted content parser with markdown and MU colors`

---

## Task 3: FormattedContent React Component

**Files:**
- Create: `frontend/src/components/FormattedContent.tsx`
- Test: `frontend/src/components/__tests__/FormattedContent.test.tsx`

React component that renders parsed segments:

```tsx
import { parseFormattedContent } from '@/lib/formatParser';

interface FormattedContentProps {
  content: string;
  className?: string;
}

export function FormattedContent({ content, className }: FormattedContentProps) {
  const segments = parseFormattedContent(content);

  return (
    <span className={className}>
      {segments.map((segment, i) => {
        switch (segment.type) {
          case 'bold':
            return <strong key={i}>{segment.content}</strong>;
          case 'italic':
            return <em key={i}>{segment.content}</em>;
          case 'strikethrough':
            return <del key={i}>{segment.content}</del>;
          case 'color':
            return <span key={i} style={{ color: segment.hex }}>{segment.content}</span>;
          case 'link':
            return (
              <a key={i} href={segment.url} target="_blank" rel="noopener noreferrer"
                 className="text-blue-500 underline hover:text-blue-700">
                {segment.content}
              </a>
            );
          default:
            return <span key={i}>{segment.content}</span>;
        }
      })}
    </span>
  );
}
```

Tests:
- Renders plain text unchanged
- Renders bold as `<strong>`
- Renders italic as `<em>`
- Renders color as span with inline color style
- Renders links as `<a>` with target="_blank" and rel="noopener"
- Handles empty content
- Handles content with no formatting

Commit: `feat(frontend): add FormattedContent renderer component`

---

## Task 4: RichTextInput Component — Toolbar and Keyboard Shortcuts

**Files:**
- Create: `frontend/src/components/RichTextInput.tsx`
- Test: `frontend/src/components/__tests__/RichTextInput.test.tsx`

A textarea with a formatting toolbar above it:

```tsx
interface RichTextInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onKeyDown?: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  placeholder?: string;
  rows?: number;
  className?: string;
}

export function RichTextInput({
  value, onChange, onSubmit, onKeyDown, placeholder, rows = 2, className
}: RichTextInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  function wrapSelection(before: string, after: string) {
    const textarea = textareaRef.current;
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const text = value;
    const selected = text.substring(start, end);
    const newText = text.substring(0, start) + before + selected + after + text.substring(end);
    onChange(newText);
    // Restore cursor position after the wrapped text
    requestAnimationFrame(() => {
      textarea.selectionStart = start + before.length;
      textarea.selectionEnd = end + before.length;
      textarea.focus();
    });
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // Ctrl+B → Bold
    if (e.ctrlKey && e.key === 'b') {
      e.preventDefault();
      wrapSelection('**', '**');
      return;
    }
    // Ctrl+I → Italic
    if (e.ctrlKey && e.key === 'i') {
      e.preventDefault();
      wrapSelection('*', '*');
      return;
    }
    // Ctrl+Shift+S → Strikethrough
    if (e.ctrlKey && e.shiftKey && e.key === 'S') {
      e.preventDefault();
      wrapSelection('~~', '~~');
      return;
    }
    // Enter to submit
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSubmit();
      return;
    }
    // Delegate other keys to parent handler
    onKeyDown?.(e);
  }

  return (
    <div className={className}>
      {/* Toolbar */}
      <div className="flex items-center gap-1 border-b px-2 py-1">
        <ToolbarButton label="Bold" shortcut="Ctrl+B"
          onClick={() => wrapSelection('**', '**')}>
          <strong>B</strong>
        </ToolbarButton>
        <ToolbarButton label="Italic" shortcut="Ctrl+I"
          onClick={() => wrapSelection('*', '*')}>
          <em>I</em>
        </ToolbarButton>
        <ToolbarButton label="Strikethrough" shortcut="Ctrl+Shift+S"
          onClick={() => wrapSelection('~~', '~~')}>
          <del>S</del>
        </ToolbarButton>
        {/* Color button added in Task 5 */}
      </div>
      {/* Textarea */}
      <Textarea
        ref={textareaRef}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        rows={rows}
        spellCheck={true}
        className="resize-none border-0 focus-visible:ring-0"
      />
    </div>
  );
}

function ToolbarButton({ label, shortcut, onClick, children }: {
  label: string; shortcut: string; onClick: () => void; children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      title={`${label} (${shortcut})`}
      onClick={onClick}
      className="rounded px-2 py-0.5 text-sm hover:bg-accent"
    >
      {children}
    </button>
  );
}
```

Tests:
- Renders textarea with toolbar
- Bold button inserts `**` markers around selection
- Italic button inserts `*` markers
- Strikethrough button inserts `~~` markers
- Ctrl+B keyboard shortcut works
- Ctrl+I keyboard shortcut works
- Enter submits
- Shift+Enter inserts newline
- spellCheck is enabled

Commit: `feat(frontend): add RichTextInput with formatting toolbar and shortcuts`

---

## Task 5: Color Picker

**Files:**
- Create: `frontend/src/components/ColorPicker.tsx`
- Test: `frontend/src/components/__tests__/ColorPicker.test.tsx`

A popover triggered by a color button in the toolbar. Shows curated swatches organized
by category. Selecting a color calls a callback with the xterm index.

```tsx
import { Popover, PopoverTrigger, PopoverContent } from '@/components/ui/popover';
import { XTERM_TO_HEX } from '@/lib/xterm256';

// Curated palette: 40-ish colors that look good for RP
const CURATED_PALETTE = [
  { label: 'Reds', indices: [1, 9, 124, 160, 196, 203, 210] },
  { label: 'Oranges', indices: [208, 214, 215, 172, 130] },
  { label: 'Yellows', indices: [3, 11, 220, 226, 228] },
  { label: 'Greens', indices: [2, 10, 28, 34, 40, 82, 114] },
  { label: 'Blues', indices: [4, 12, 20, 27, 33, 39, 75] },
  { label: 'Purples', indices: [5, 13, 53, 92, 128, 134, 170] },
  { label: 'Cyans', indices: [6, 14, 37, 44, 51, 87] },
  { label: 'Neutrals', indices: [7, 15, 8, 0, 240, 245, 250, 255] },
];

interface ColorPickerProps {
  onSelectColor: (xtermIndex: number) => void;
}

export function ColorPicker({ onSelectColor }: ColorPickerProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button type="button" title="Text Color"
          className="rounded px-2 py-0.5 text-sm hover:bg-accent">
          🎨
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-2">
        {CURATED_PALETTE.map((group) => (
          <div key={group.label} className="mb-2">
            <div className="text-xs text-muted-foreground mb-1">{group.label}</div>
            <div className="flex flex-wrap gap-1">
              {group.indices.map((idx) => (
                <button
                  key={idx}
                  type="button"
                  title={`Color ${idx}`}
                  onClick={() => onSelectColor(idx)}
                  className="h-5 w-5 rounded border border-border hover:ring-2 ring-primary"
                  style={{ backgroundColor: XTERM_TO_HEX[idx] }}
                />
              ))}
            </div>
          </div>
        ))}
      </PopoverContent>
    </Popover>
  );
}
```

Integrate into RichTextInput toolbar — the color picker's `onSelectColor` calls
`wrapSelection('|[index]', '|n')`.

Tests:
- Renders color button in toolbar
- Clicking opens popover with color swatches
- Selecting a color inserts `|[index]...|n` markers
- Popover closes after selection

Commit: `feat(frontend): add color picker with curated xterm-256 palette`

---

## Task 6: Integration — Replace CommandInput and SceneMessages Display

**Files:**
- Modify: `frontend/src/game/components/CommandInput.tsx`
- Modify: `frontend/src/scenes/components/SceneMessages.tsx`

### CommandInput

Replace the plain `<Textarea>` with `<RichTextInput>`:

```tsx
import { RichTextInput } from '@/components/RichTextInput';

export function CommandInput({ character }: CommandInputProps) {
  // ... existing state and handlers ...

  return (
    <div className="shrink-0 border-t">
      <RichTextInput
        value={command}
        onChange={(val) => { setCommand(val); setHistoryIndex(-1); }}
        onSubmit={handleSubmit}
        onKeyDown={handleKeyDown}
        placeholder="Write a pose..."
        rows={2}
      />
    </div>
  );
}
```

### SceneMessages

Replace the `formatContent` function's raw `<p>{content}</p>` with
`<FormattedContent content={content} />`:

```tsx
import { FormattedContent } from '@/components/FormattedContent';

function formatContent(content: string, mode: string) {
  switch (mode) {
    case 'say':
      return <p>&ldquo;<FormattedContent content={content} />&rdquo;</p>;
    case 'whisper':
      return <p className="italic text-muted-foreground">
        <FormattedContent content={content} />
      </p>;
    case 'action':
      return <div className="mt-1"><ActionResult content={content} /></div>;
    default:
      return <p><FormattedContent content={content} /></p>;
  }
}
```

Tests:
- CommandInput renders RichTextInput with toolbar
- SceneMessages renders formatted content (bold, italic, colors)

Commit: `feat(frontend): integrate RichTextInput and FormattedContent into game UI`

---

## Task 7: Full Frontend Check

Run:
- `pnpm --dir frontend test -- --run`
- `pnpm --dir frontend typecheck`
- `pnpm --dir frontend lint`
- `pnpm --dir frontend build`

Fix any issues.

Also run backend to make sure nothing broke:
- `uv run arx test`

Commit: `fix(frontend): test and lint fixes for rich text editor`

---

## Summary

| Task | What | Key Files |
|------|------|-----------|
| 1 | xterm-256 lookup table | `lib/xterm256.ts` |
| 2 | Content parser | `lib/formatParser.ts` |
| 3 | FormattedContent component | `components/FormattedContent.tsx` |
| 4 | RichTextInput with toolbar | `components/RichTextInput.tsx` |
| 5 | Color picker | `components/ColorPicker.tsx` |
| 6 | Integration | `CommandInput.tsx`, `SceneMessages.tsx` |
| 7 | Full check | All files |

### Not in this plan
- Live preview while typing (future enhancement)
- Full color wheel (MVP uses curated swatches only)
- Telnet color stripping (backend concern, deferred)
- Mobile-optimized toolbar (works but not polished)
