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
    | 'text';
  start: number;
  end: number;
  /** For colorStart: the resolved hex value. */
  hex?: string;
  /** For url: the matched URL string. */
  url?: string;
}

// Pattern for color codes: |r, |[123], etc. and |n for reset
const COLOR_START_RE = /\|(\[(\d{1,3})\]|([a-zA-Z]))/g;
const COLOR_RESET_RE = /\|n/g;
const BOLD_RE = /\*\*/g;
const STRIKE_RE = /~~/g;
const URL_RE = /https?:\/\/[^\s<>"{}|\\^`[\]]+/g;

/** Trailing punctuation that is unlikely to be part of a URL. */
const TRAILING_PUNCT = new Set(['.', ',', ')', '!', '?', ':', ';']);

function collectTokens(text: string): Token[] {
  const tokens: Token[] = [];

  // Color starts
  COLOR_START_RE.lastIndex = 0;
  let m: RegExpExecArray | null;
  while ((m = COLOR_START_RE.exec(text)) !== null) {
    let hex: string | undefined;
    if (m[2] !== undefined) {
      // Indexed: |[123]
      hex = xtermToHex(parseInt(m[2], 10));
    } else if (m[3] !== undefined) {
      // Named: |r — skip 'n' as it is the reset code, not a color
      if (m[3] === 'n' || m[3] === 'N') continue;
      const idx = MU_COLOR_NAMES[m[3]];
      if (idx !== undefined) {
        hex = xtermToHex(idx);
      }
    }
    if (hex !== undefined) {
      tokens.push({ kind: 'colorStart', start: m.index, end: m.index + m[0].length, hex });
    }
  }

  // Color resets
  COLOR_RESET_RE.lastIndex = 0;
  while ((m = COLOR_RESET_RE.exec(text)) !== null) {
    tokens.push({ kind: 'colorReset', start: m.index, end: m.index + m[0].length });
  }

  // Bold markers (**)
  BOLD_RE.lastIndex = 0;
  while ((m = BOLD_RE.exec(text)) !== null) {
    tokens.push({ kind: 'boldMarker', start: m.index, end: m.index + 2 });
  }

  // Strikethrough markers (~~)
  STRIKE_RE.lastIndex = 0;
  while ((m = STRIKE_RE.exec(text)) !== null) {
    tokens.push({ kind: 'strikeMarker', start: m.index, end: m.index + 2 });
  }

  // URLs — strip trailing punctuation
  URL_RE.lastIndex = 0;
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

  // Sort by position
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
 * Parse formatted content into an array of typed segments.
 *
 * Processes color codes, bold, italic, strikethrough, and URLs
 * in a single pass over the input text.
 */
export function parseFormattedContent(text: string): Segment[] {
  if (!text) return [];

  const segments: Segment[] = [];
  const tokens = collectTokens(text);

  // Track which token indices are "consumed" as part of a matched pair
  const consumed = new Set<number>();

  // First pass: resolve paired markers (bold, strike, italic) and colors
  // We'll build a list of "ranges" that represent formatted content
  interface Range {
    type: SegmentType;
    contentStart: number;
    contentEnd: number;
    fullStart: number;
    fullEnd: number;
    hex?: string;
    url?: string;
  }

  const ranges: Range[] = [];

  // Match bold pairs
  for (let i = 0; i < tokens.length; i++) {
    if (consumed.has(i)) continue;
    if (tokens[i].kind === 'boldMarker') {
      const closeIdx = findClosingMarker(tokens, i, 'boldMarker', text);
      if (closeIdx !== -1) {
        const innerText = text.slice(tokens[i].end, tokens[closeIdx].start);
        if (innerText.length > 0) {
          ranges.push({
            type: 'bold',
            contentStart: tokens[i].end,
            contentEnd: tokens[closeIdx].start,
            fullStart: tokens[i].start,
            fullEnd: tokens[closeIdx].end,
          });
          consumed.add(i);
          consumed.add(closeIdx);
          // Also consume any italic markers inside the bold range
          for (let j = i + 1; j < closeIdx; j++) {
            if (tokens[j].kind === 'italicMarker') {
              consumed.add(j);
            }
          }
        }
      }
    }
  }

  // Match strikethrough pairs
  for (let i = 0; i < tokens.length; i++) {
    if (consumed.has(i)) continue;
    if (tokens[i].kind === 'strikeMarker') {
      const closeIdx = findClosingMarker(tokens, i, 'strikeMarker', text);
      if (closeIdx !== -1) {
        const innerText = text.slice(tokens[i].end, tokens[closeIdx].start);
        if (innerText.length > 0) {
          ranges.push({
            type: 'strikethrough',
            contentStart: tokens[i].end,
            contentEnd: tokens[closeIdx].start,
            fullStart: tokens[i].start,
            fullEnd: tokens[closeIdx].end,
          });
          consumed.add(i);
          consumed.add(closeIdx);
        }
      }
    }
  }

  // Collect italic markers that weren't consumed by bold
  // Build a Set of consumed positions from bold ranges for O(1) lookup
  const consumedPositions = new Set<number>();
  for (const r of ranges) {
    if (r.type === 'bold') {
      // The bold markers occupy fullStart..fullStart+2 and fullEnd-2..fullEnd
      for (let p = r.fullStart; p < r.fullStart + 2; p++) consumedPositions.add(p);
      for (let p = r.fullEnd - 2; p < r.fullEnd; p++) consumedPositions.add(p);
    }
  }

  // Build a Set of positions inside any range for O(1) lookup
  // We only need to check range boundaries, so collect all range intervals
  const rangeIntervals: Array<{ start: number; end: number }> = ranges.map((r) => ({
    start: r.fullStart,
    end: r.fullEnd,
  }));

  function isInsideRange(pos: number): boolean {
    for (const interval of rangeIntervals) {
      if (pos > interval.start && pos < interval.end) {
        return true;
      }
    }
    return false;
  }

  const italicPositions: number[] = [];
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '*') {
      // Check this isn't part of a consumed bold marker range
      if (consumedPositions.has(i)) continue;

      // Check it's not part of a ** (unconsumed bold that didn't match)
      if (i + 1 < text.length && text[i + 1] === '*') {
        // Part of ** — skip both
        i++;
        continue;
      }
      if (i > 0 && text[i - 1] === '*') {
        // Second char of ** — already skipped
        continue;
      }

      // Also check it's not inside a consumed range (bold content)
      if (isInsideRange(i)) continue;

      italicPositions.push(i);
    }
  }

  // Pair up italic markers — reject pairs that span newlines
  for (let i = 0; i + 1 < italicPositions.length; i += 2) {
    const openPos = italicPositions[i];
    const closePos = italicPositions[i + 1];
    const innerText = text.slice(openPos + 1, closePos);
    if (innerText.length > 0 && !innerText.includes('\n')) {
      ranges.push({
        type: 'italic',
        contentStart: openPos + 1,
        contentEnd: closePos,
        fullStart: openPos,
        fullEnd: closePos + 1,
      });
    }
  }

  // Match color ranges
  for (let i = 0; i < tokens.length; i++) {
    if (consumed.has(i)) continue;
    if (tokens[i].kind === 'colorStart' && tokens[i].hex) {
      // Find the next colorReset
      let resetIdx = -1;
      for (let j = i + 1; j < tokens.length; j++) {
        if (tokens[j].kind === 'colorReset') {
          resetIdx = j;
          break;
        }
      }
      if (resetIdx !== -1) {
        const innerText = text.slice(tokens[i].end, tokens[resetIdx].start);
        if (innerText.length > 0) {
          ranges.push({
            type: 'color',
            contentStart: tokens[i].end,
            contentEnd: tokens[resetIdx].start,
            fullStart: tokens[i].start,
            fullEnd: tokens[resetIdx].end,
            hex: tokens[i].hex,
          });
        }
        consumed.add(i);
        consumed.add(resetIdx);
      } else {
        // No reset — color extends to end
        const innerText = text.slice(tokens[i].end);
        if (innerText.length > 0) {
          ranges.push({
            type: 'color',
            contentStart: tokens[i].end,
            contentEnd: text.length,
            fullStart: tokens[i].start,
            fullEnd: text.length,
            hex: tokens[i].hex,
          });
        }
        consumed.add(i);
      }
    }
  }

  // Add URL ranges
  for (let i = 0; i < tokens.length; i++) {
    if (consumed.has(i)) continue;
    if (tokens[i].kind === 'url') {
      // Check URL isn't inside an already-matched range
      let inside = false;
      for (const r of ranges) {
        if (tokens[i].start >= r.fullStart && tokens[i].end <= r.fullEnd) {
          inside = true;
          break;
        }
      }
      if (!inside) {
        ranges.push({
          type: 'link',
          contentStart: tokens[i].start,
          contentEnd: tokens[i].end,
          fullStart: tokens[i].start,
          fullEnd: tokens[i].end,
          url: tokens[i].url,
        });
        consumed.add(i);
      }
    }
  }

  // Sort ranges by fullStart
  ranges.sort((a, b) => a.fullStart - b.fullStart);

  // Now build segments by walking through the text
  let pos = 0;
  for (const range of ranges) {
    // Skip overlapping ranges
    if (range.fullStart < pos) continue;

    // Text before this range
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

  // Remaining text
  if (pos < text.length) {
    pushText(segments, text.slice(pos));
  }

  return segments;
}
