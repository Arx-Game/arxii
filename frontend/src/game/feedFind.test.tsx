import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import {
  findInteractions,
  findNotes,
  interactionMatchesFind,
  markMatches,
  markMatchesInHtml,
  noteMatchesFind,
  normalizeFind,
} from './feedFind';

describe('find in this session', () => {
  it('matches the shown line, the recorded text, or the speaker, case folded', () => {
    const item = {
      content: 'glances at the gate.',
      line: 'Nyx glances at the Gate.',
      persona: { name: 'Nyx' },
    };
    expect(interactionMatchesFind(item, 'gate')).toBe(true);
    expect(interactionMatchesFind(item, 'nyx')).toBe(true);
    expect(interactionMatchesFind({ content: 'quiet', persona: { name: 'Bram' } }, 'gate')).toBe(
      false
    );
    expect(interactionMatchesFind(item, '')).toBe(true);
  });

  it('matches a note by its content or subject', () => {
    expect(noteMatchesFind({ content: 'Rain rests on the stones.' }, 'stones')).toBe(true);
    expect(noteMatchesFind({ content: 'A bench.', subject: 'The east gate' }, 'gate')).toBe(true);
    expect(noteMatchesFind({ content: 'A bench.' }, 'gate')).toBe(false);
  });

  it('returns the same list when there is nothing to find', () => {
    const items = [{ content: 'a', persona: { name: 'b' } }];
    expect(findInteractions(items, '')).toBe(items);
    const notes = [{ content: 'a' }];
    expect(findNotes(notes, normalizeFind('   '))).toBe(notes);
    expect(findInteractions(items, 'zzz')).toEqual([]);
  });

  it('marks every match in text, and nothing without a needle', () => {
    expect(markMatches('the gate by the gatehouse', '')).toBe('the gate by the gatehouse');
    const { container } = render(<span>{markMatches('the Gate by the gatehouse', 'gate')}</span>);
    const marks = container.querySelectorAll('mark[data-find-match]');
    expect(marks).toHaveLength(2);
    expect(marks[0].textContent).toBe('Gate');
    expect(container.textContent).toBe('the Gate by the gatehouse');
  });

  it('marks matches inside HTML text runs and leaves tags alone', () => {
    const html = '<span class="text-red-400">the gate</span> is <b>agate</b>';
    expect(markMatchesInHtml(html, 'gate')).toBe(
      '<span class="text-red-400">the <mark data-find-match="">gate</mark></span> is <b>a<mark data-find-match="">gate</mark></b>'
    );
    expect(markMatchesInHtml(html, '')).toBe(html);
  });
});
