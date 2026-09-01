/**
 * Single-pass parser for formatted content with MU* color codes,
 * markdown-style bold/italic/strikethrough, and auto-linked URLs.
 */

import { MU_COLOR_NAMES, xtermToHex } from './xterm256';

// Discriminated union for segment types
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
  content: string;
  hex: string;
}
interface LinkSegment {
  type: 'link';
  content: string;
  url: string;
}

export type Segment =
  | TextSegment
  | BoldSegment
  | ItalicSegment
  | StrikethroughSegment
  | ColorSegment
  | LinkSegment;

export type SegmentType = Segment['type'];

/**
 * Token types produced by the lexer pass.
 * Each token carries its position in the source string.
 */
interface Token {
  kind:
    | 'colorStart'
    | 'colorReset'
    | 'boldMarker'
    | 'italicMarker'
    | 'strikeMarker'
    | 'url'
    | 'markdownLink'
    | 'text';
  start: number;
  end: number;
  /** For colorStart: the resolved hex value. */
  hex?: string;
  /** For url / markdownLink: the matched URL string. */
  url?: string;
  /** For markdownLink: the display text between [ and ]. */
  displayText?: string;
}

// Pattern for color codes: |r, |[123], etc. and |n for reset
const COLOR_START_RE = /\|(\[(\d{1,3})\]|([a-zA-Z]))/g;
const COLOR_RESET_RE = /\|n/g;
const BOLD_RE = /\*\*/g;
const STRIKE_RE = /~~/g;
const URL_RE = /https?:\/\/[^\s<>"{}|\\^`[\]]+/g;
const MARKDOWN_LINK_RE = /\[([^\]\n]{1,500})\]\((https?:\/\/[^\s)]{1,2048})\)/g;

/** Trailing punctuation that is unlikely to be part of a URL. */
const TRAILING_PUNCT = new Set(['.', ',', ')', '!', '?', ':', ';']);

function collectColorTokens(text: string, tokens: Token[]): void {
  COLOR_START_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = COLOR_START_RE.exec(text)) !== null) {
    const hex = resolveColorHex(m);
    if (hex !== undefined) {
      tokens.push({ kind: 'colorStart', start: m.index, end: m.index + m[0].length, hex });
    }
  }

  COLOR_RESET_RE.lastIndex = 0;
  while ((m = COLOR_RESET_RE.exec(text)) !== null) {
    tokens.push({ kind: 'colorReset', start: m.index, end: m.index + m[0].length });
  }
}

/** The hex a `|[123]` or `|r` match resolves to, or undefined if it names no color. */
function resolveColorHex(m: RegExpExecArray): string | undefined {
  if (m[2] !== undefined) {
    // Indexed: |[123]
    return xtermToHex(parseInt(m[2], 10));
  }
  if (m[3] === undefined) return undefined;
  // Named: |r — 'n' is the reset code, not a color
  if (m[3] === 'n' || m[3] === 'N') return undefined;
  const idx = MU_COLOR_NAMES[m[3]];
  return idx === undefined ? undefined : xtermToHex(idx);
}

/** Two-character markdown markers (`**`, `~~`), which pair up in a later pass. */
function collectMarkerTokens(text: string, tokens: Token[]): void {
  const patterns: Array<[RegExp, Token['kind']]> = [
    [BOLD_RE, 'boldMarker'],
    [STRIKE_RE, 'strikeMarker'],
  ];
  for (const [re, kind] of patterns) {
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      tokens.push({ kind, start: m.index, end: m.index + 2 });
    }
  }
}

function collectLinkTokens(text: string, tokens: Token[]): void {
  // Bare URLs — trailing sentence punctuation is not part of the link.
  URL_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = URL_RE.exec(text)) !== null) {
    let url = m[0];
    let end = m.index + url.length;
    while (url.length > 0 && TRAILING_PUNCT.has(url[url.length - 1])) {
      url = url.slice(0, -1);
      end--;
    }
    if (url.length > 0) {
      tokens.push({ kind: 'url', start: m.index, end, url });
    }
  }

  // Markdown links [display](https://url)
  MARKDOWN_LINK_RE.lastIndex = 0;
  while ((m = MARKDOWN_LINK_RE.exec(text)) !== null) {
    tokens.push({
      kind: 'markdownLink',
      start: m.index,
      end: m.index + m[0].length,
      url: m[2],
      displayText: m[1],
    });
  }
}

function collectTokens(text: string): Token[] {
  const tokens: Token[] = [];
  collectColorTokens(text, tokens);
  collectMarkerTokens(text, tokens);
  collectLinkTokens(text, tokens);
  tokens.sort((a, b) => a.start - b.start || a.end - b.end);
  return tokens;
}

/**
 * Try to find a matching closing marker for a given opening marker.
 * Returns the index in the tokens array of the closing marker, or -1.
 *
 * For markdown markers (bold/strike), the content between markers must
 * not contain newlines — newlines break the span.
 */
function findClosingMarker(tokens: Token[], openIdx: number, kind: string, text: string): number {
  const open = tokens[openIdx];
  for (let i = openIdx + 1; i < tokens.length; i++) {
    if (tokens[i].kind === kind && tokens[i].start > open.end) {
      // For markdown markers, reject if the inner content contains a newline
      const inner = text.slice(open.end, tokens[i].start);
      if (inner.includes('\n')) {
        return -1;
      }
      return i;
    }
  }
  return -1;
}

function pushText(segments: Segment[], content: string): void {
  if (content.length > 0) {
    segments.push({ type: 'text', content });
  }
}

/**
 * A resolved span of formatted text: the markers occupy `fullStart..fullEnd`,
 * the content they wrap occupies `contentStart..contentEnd`.
 */
interface Range {
  type: SegmentType;
  contentStart: number;
  contentEnd: number;
  fullStart: number;
  fullEnd: number;
  hex?: string;
  url?: string;
}

/**
 * Pair up two-character markers of one kind (`**` or `~~`) into ranges.
 *
 * A pair with empty content is not a span and is left unconsumed, so its
 * markers stay in the text. Bold additionally swallows any italic markers
 * inside the pair — `**a *b* c**` is bold throughout, not bold-around-italic.
 */
function matchPairedMarkers(
  tokens: Token[],
  text: string,
  kind: 'boldMarker' | 'strikeMarker',
  type: 'bold' | 'strikethrough',
  consumed: Set<number>,
  ranges: Range[]
): void {
  for (let i = 0; i < tokens.length; i++) {
    if (consumed.has(i) || tokens[i].kind !== kind) continue;
    const closeIdx = findClosingMarker(tokens, i, kind, text);
    if (closeIdx === -1) continue;
    if (text.slice(tokens[i].end, tokens[closeIdx].start).length === 0) continue;

    ranges.push({
      type,
      contentStart: tokens[i].end,
      contentEnd: tokens[closeIdx].start,
      fullStart: tokens[i].start,
      fullEnd: tokens[closeIdx].end,
    });
    consumed.add(i);
    consumed.add(closeIdx);
    if (type === 'bold') {
      for (let j = i + 1; j < closeIdx; j++) {
        if (tokens[j].kind === 'italicMarker') consumed.add(j);
      }
    }
  }
}

/**
 * The positions of single `*` characters that can open or close an italic span.
 *
 * Skips the two characters of any `**` (matched bold markers, and unmatched
 * ones too — a stray `**` is not two italics) and anything sitting inside a
 * range already claimed by bold or strikethrough.
 */
function findItalicPositions(text: string, ranges: Range[]): number[] {
  const boldMarkerPositions = new Set<number>();
  for (const r of ranges) {
    if (r.type !== 'bold') continue;
    for (let p = r.fullStart; p < r.fullStart + 2; p++) boldMarkerPositions.add(p);
    for (let p = r.fullEnd - 2; p < r.fullEnd; p++) boldMarkerPositions.add(p);
  }
  const isInsideRange = (pos: number): boolean =>
    ranges.some((r) => pos > r.fullStart && pos < r.fullEnd);

  const positions: number[] = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] !== '*' || boldMarkerPositions.has(i)) continue;
    if (i + 1 < text.length && text[i + 1] === '*') {
      i++; // part of an unconsumed ** — skip both characters
      continue;
    }
    if (i > 0 && text[i - 1] === '*') continue;
    if (isInsideRange(i)) continue;
    positions.push(i);
  }
  return positions;
}

/** Pair the leftover single `*` markers into italic ranges, in order. */
function matchItalicRanges(text: string, ranges: Range[]): void {
  const positions = findItalicPositions(text, ranges);
  for (let i = 0; i + 1 < positions.length; i += 2) {
    const openPos = positions[i];
    const closePos = positions[i + 1];
    const innerText = text.slice(openPos + 1, closePos);
    // A newline breaks the span, same as the other markdown markers.
    if (innerText.length === 0 || innerText.includes('\n')) continue;
    ranges.push({
      type: 'italic',
      contentStart: openPos + 1,
      contentEnd: closePos,
      fullStart: openPos,
      fullEnd: closePos + 1,
    });
  }
}

/**
 * Turn each color start into a range running to the next reset.
 *
 * A color with no reset after it runs to the end of the text — an unterminated
 * `|r` colors the rest of the line rather than being dropped.
 */
function matchColorRanges(
  tokens: Token[],
  text: string,
  consumed: Set<number>,
  ranges: Range[]
): void {
  for (let i = 0; i < tokens.length; i++) {
    if (consumed.has(i) || tokens[i].kind !== 'colorStart' || !tokens[i].hex) continue;

    const resetIdx = tokens.findIndex((t, j) => j > i && t.kind === 'colorReset');
    const contentEnd = resetIdx === -1 ? text.length : tokens[resetIdx].start;
    if (text.slice(tokens[i].end, contentEnd).length > 0) {
      ranges.push({
        type: 'color',
        contentStart: tokens[i].end,
        contentEnd,
        fullStart: tokens[i].start,
        fullEnd: resetIdx === -1 ? text.length : tokens[resetIdx].end,
        hex: tokens[i].hex,
      });
    }
    consumed.add(i);
    if (resetIdx !== -1) consumed.add(resetIdx);
  }
}

/**
 * Add ranges for URLs and markdown links that no other range already covers.
 *
 * A link inside a bold or colored span is left alone: that span already owns
 * the text, and nesting the two would double-render it.
 */
function matchLinkRanges(tokens: Token[], consumed: Set<number>, ranges: Range[]): void {
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (consumed.has(i) || (t.kind !== 'url' && t.kind !== 'markdownLink')) continue;
    if (ranges.some((r) => t.start >= r.fullStart && t.end <= r.fullEnd)) continue;

    const displayLen = t.displayText?.length ?? 0;
    ranges.push({
      type: 'link',
      // A markdown link displays only the text between the brackets.
      contentStart: t.kind === 'markdownLink' ? t.start + 1 : t.start,
      contentEnd: t.kind === 'markdownLink' ? t.start + 1 + displayLen : t.end,
      fullStart: t.start,
      fullEnd: t.end,
      url: t.url,
    });
    consumed.add(i);
  }
}

/**
 * Walk the ranges in source order, emitting the plain text between them.
 *
 * Ranges are resolved independently and may overlap; a range that starts before
 * where the previous one ended is dropped rather than rendered twice.
 */
function buildSegments(text: string, ranges: Range[]): Segment[] {
  const segments: Segment[] = [];
  ranges.sort((a, b) => a.fullStart - b.fullStart);

  let pos = 0;
  for (const range of ranges) {
    if (range.fullStart < pos) continue;
    if (range.fullStart > pos) {
      pushText(segments, text.slice(pos, range.fullStart));
    }

    const content = text.slice(range.contentStart, range.contentEnd);
    if (range.type === 'link') {
      segments.push({ type: 'link', content, url: range.url! });
    } else if (range.type === 'color') {
      segments.push({ type: 'color', content, hex: range.hex! });
    } else {
      segments.push({ type: range.type, content });
    }
    pos = range.fullEnd;
  }

  if (pos < text.length) {
    pushText(segments, text.slice(pos));
  }
  return segments;
}

/**
 * Parse formatted content into an array of typed segments.
 *
 * Processes color codes, bold, italic, strikethrough, and URLs in a single
 * pass over the input text. The passes run in a fixed order because each one
 * narrows what is still available to the next: bold claims the italic markers
 * inside it, italics take what bold and strikethrough left, colors and links
 * skip anything already claimed.
 */
export function parseFormattedContent(text: string): Segment[] {
  if (!text) return [];

  const tokens = collectTokens(text);
  const consumed = new Set<number>();
  const ranges: Range[] = [];

  matchPairedMarkers(tokens, text, 'boldMarker', 'bold', consumed, ranges);
  matchPairedMarkers(tokens, text, 'strikeMarker', 'strikethrough', consumed, ranges);
  matchItalicRanges(text, ranges);
  matchColorRanges(tokens, text, consumed, ranges);
  matchLinkRanges(tokens, consumed, ranges);

  return buildSegments(text, ranges);
}
