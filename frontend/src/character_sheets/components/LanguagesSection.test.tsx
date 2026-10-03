/**
 * LanguagesSection (#4090): temporary rows name the condition and the trained level.
 *
 * Ruling Q1 (#4090 Task 11): the gloss adds " · trained <Band>" only when the
 * trained `fluency` is above 0. A language raised only by a condition (no
 * trained fluency at all) shows just "from <Condition>", with no "trained"
 * text — matching the approved demo (demo-4090.html, Screen 3).
 */
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { LanguagesSection } from './LanguagesSection';
import type { MyLanguage } from '@/species/types';

const rows: MyLanguage[] = [];
vi.mock('@/species/queries', () => ({ useMyLanguages: () => ({ data: rows }) }));

function row(overrides: Partial<MyLanguage>): MyLanguage {
  return {
    language_id: 1,
    name: 'Common',
    fluency: 80,
    band: 'fluent',
    is_current: false,
    effective_fluency: 80,
    effective_band: 'fluent',
    temporary_sources: [],
    ...overrides,
  };
}

/**
 * Selector list per top-level rule header in a CSS file, same approach as
 * `character-creation/__tests__/components/offers/classGuard.ts`'s
 * `ruleSelectors` (#3667 shape): proves a rule REACHES the rendered element,
 * not just that a class name string appears somewhere in the file.
 */
function ruleSelectors(css: string): string[] {
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const selectors: string[] = [];
  const headerRe = /(?:^|\})\s*([^{}]+?)\s*\{/g;
  let match: RegExpExecArray | null;
  while ((match = headerRe.exec(stripped))) {
    const header = match[1].trim();
    if (!header || header.startsWith('@')) continue;
    for (const sel of header.split(',')) {
      const trimmed = sel.trim();
      if (trimmed) selectors.push(trimmed);
    }
  }
  return selectors;
}

function reachedBy(el: Element, selectors: string[]): boolean {
  return selectors.some((sel) => {
    try {
      return el.matches(sel);
    } catch {
      return false;
    }
  });
}

describe('LanguagesSection', () => {
  it('renders a trained row as before, with no tag', () => {
    rows.splice(0, rows.length, row({ is_current: true }));
    render(<LanguagesSection />);
    expect(screen.getByText('Common (speaking)')).toBeInTheDocument();
    expect(screen.getByText('Fluent')).toBeInTheDocument();
    expect(screen.queryByText('Temporary')).not.toBeInTheDocument();
  });

  it('marks a raised row temporary, names the condition and the trained level', () => {
    rows.splice(
      0,
      rows.length,
      row({
        language_id: 2,
        name: 'Tongue B',
        fluency: 20,
        band: 'broken',
        effective_fluency: 80,
        temporary_sources: ['Understood Tongue'],
      })
    );
    render(<LanguagesSection />);
    expect(screen.getByText('Fluent')).toBeInTheDocument();
    expect(screen.getByText('Temporary')).toBeInTheDocument();
    expect(screen.getByText('from Understood Tongue · trained Broken')).toBeInTheDocument();
  });

  it('shows no trained text for a condition-only language (Ruling Q1)', () => {
    rows.splice(
      0,
      rows.length,
      row({
        language_id: 3,
        name: 'Tongue A',
        fluency: 0,
        band: 'none',
        temporary_sources: ['Understood Tongue'],
      })
    );
    render(<LanguagesSection />);
    expect(screen.getByText('from Understood Tongue')).toBeInTheDocument();
    expect(screen.queryByText(/trained/)).not.toBeInTheDocument();
  });

  it('reaches the Temporary tag and the gloss with a real sheet.css rule, not just a class name', () => {
    rows.splice(
      0,
      rows.length,
      row({
        language_id: 2,
        name: 'Tongue B',
        fluency: 20,
        band: 'broken',
        effective_fluency: 80,
        temporary_sources: ['Understood Tongue'],
      })
    );
    render(<LanguagesSection />);
    const css = readFileSync(resolve(__dirname, '../sheet.css'), 'utf8');
    const selectors = ruleSelectors(css);
    const tagEl = screen.getByText('Temporary');
    const glossEl = screen.getByText(/^from Understood Tongue/);
    expect(reachedBy(tagEl, selectors)).toBe(true);
    expect(reachedBy(glossEl, selectors)).toBe(true);
  });
});
