import { describe, expect, it } from 'vitest';
import { parseFormattedContent } from '../formatParser';

describe('parseFormattedContent', () => {
  it('returns empty array for empty string', () => {
    expect(parseFormattedContent('')).toEqual([]);
  });

  it('parses plain text', () => {
    expect(parseFormattedContent('hello')).toEqual([{ type: 'text', content: 'hello' }]);
  });

  it('parses bold text', () => {
    expect(parseFormattedContent('**hello**')).toEqual([{ type: 'bold', content: 'hello' }]);
  });

  it('parses italic text', () => {
    expect(parseFormattedContent('*hello*')).toEqual([{ type: 'italic', content: 'hello' }]);
  });

  it('parses strikethrough text', () => {
    expect(parseFormattedContent('~~hello~~')).toEqual([
      { type: 'strikethrough', content: 'hello' },
    ]);
  });

  it('parses named color with reset', () => {
    const result = parseFormattedContent('|rhello|n');
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe('color');
    expect(result[0].content).toBe('hello');
    const seg = result[0];
    expect(seg.type).toBe('color');
    if (seg.type === 'color') expect(seg.hex).toBe('#800000');
  });

  it('parses indexed color with reset', () => {
    const result = parseFormattedContent('|[196]hello|n');
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe('color');
    expect(result[0].content).toBe('hello');
    const seg = result[0];
    expect(seg.type).toBe('color');
    if (seg.type === 'color') expect(seg.hex).toBe('#ff0000');
  });

  it('parses color extending to end when no reset', () => {
    const result = parseFormattedContent('|rhello');
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe('color');
    expect(result[0].content).toBe('hello');
    const seg = result[0];
    expect(seg.type).toBe('color');
    if (seg.type === 'color') expect(seg.hex).toBe('#800000');
  });

  it('parses URLs', () => {
    const result = parseFormattedContent('visit https://example.com today');
    expect(result).toHaveLength(3);
    expect(result[0]).toEqual({ type: 'text', content: 'visit ' });
    expect(result[1]).toEqual({
      type: 'link',
      content: 'https://example.com',
      url: 'https://example.com',
    });
    expect(result[2]).toEqual({ type: 'text', content: ' today' });
  });

  it('parses mixed bold and italic', () => {
    const result = parseFormattedContent('**bold** and *italic*');
    expect(result).toHaveLength(3);
    expect(result[0]).toEqual({ type: 'bold', content: 'bold' });
    expect(result[1]).toEqual({ type: 'text', content: ' and ' });
    expect(result[2]).toEqual({ type: 'italic', content: 'italic' });
  });

  it('treats unmatched * as plain text', () => {
    const result = parseFormattedContent('*hello');
    expect(result).toEqual([{ type: 'text', content: '*hello' }]);
  });

  it('treats unmatched ** as plain text', () => {
    const result = parseFormattedContent('**hello');
    expect(result).toEqual([{ type: 'text', content: '**hello' }]);
  });

  it('treats empty bold markers as plain text', () => {
    const result = parseFormattedContent('****');
    expect(result).toEqual([{ type: 'text', content: '****' }]);
  });

  it('handles * inside bold as part of bold content', () => {
    // **bold*text** — the * inside should be part of bold content
    const result = parseFormattedContent('**bold*text**');
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe('bold');
    expect(result[0].content).toBe('bold*text');
  });

  it('handles text before and after formatting', () => {
    const result = parseFormattedContent('before **bold** after');
    expect(result).toEqual([
      { type: 'text', content: 'before ' },
      { type: 'bold', content: 'bold' },
      { type: 'text', content: ' after' },
    ]);
  });

  it('handles multiple color segments', () => {
    const result = parseFormattedContent('|rred|n and |ggreen|n');
    expect(result).toHaveLength(3);
    expect(result[0].type).toBe('color');
    expect(result[0].content).toBe('red');
    expect(result[1]).toEqual({ type: 'text', content: ' and ' });
    expect(result[2].type).toBe('color');
    expect(result[2].content).toBe('green');
  });

  // Newline boundary tests
  it('does not parse bold spanning newlines', () => {
    const result = parseFormattedContent('**bold\ntext**');
    // Should be plain text, not bold
    expect(result.every((s) => s.type === 'text')).toBe(true);
  });

  it('does not parse italic spanning newlines', () => {
    const result = parseFormattedContent('*italic\nacross lines*');
    expect(result.every((s) => s.type === 'text')).toBe(true);
  });

  it('allows color to span newlines', () => {
    const result = parseFormattedContent('|rcolor\nacross lines|n');
    expect(result).toHaveLength(1);
    expect(result[0].type).toBe('color');
    expect(result[0].content).toBe('color\nacross lines');
  });

  // URL trailing punctuation
  it('strips trailing punctuation from URLs', () => {
    const result = parseFormattedContent('see https://example.com.');
    expect(result).toHaveLength(3);
    expect(result[0]).toEqual({ type: 'text', content: 'see ' });
    expect(result[1]).toEqual({
      type: 'link',
      content: 'https://example.com',
      url: 'https://example.com',
    });
    expect(result[2]).toEqual({ type: 'text', content: '.' });
  });

  it('strips trailing comma from URLs', () => {
    const result = parseFormattedContent('https://example.com, and more');
    expect(result).toHaveLength(2);
    expect(result[0]).toEqual({
      type: 'link',
      content: 'https://example.com',
      url: 'https://example.com',
    });
    expect(result[1]).toEqual({ type: 'text', content: ', and more' });
  });
});
