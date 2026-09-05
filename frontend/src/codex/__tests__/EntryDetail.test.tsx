/**
 * Tests for EntryDetail's "Also filed under" line (#2896).
 *
 * A filed entry keeps one canonical home (`subject`/`subject_path`) but can
 * also be cross-listed under other subjects; the detail view renders those
 * as a quiet line of breadcrumb links beneath the canonical breadcrumb, and
 * renders nothing when the entry carries no filings.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { EntryDetail } from '../components/EntryDetail';
import type { CodexEntryDetail } from '../types';

function makeEntry(overrides: Partial<CodexEntryDetail> = {}): CodexEntryDetail {
  return {
    id: 1,
    name: 'The Shroud',
    summary: 'A grey veil no army and no messenger ever crossed.',
    lore_content: 'Full lore content.',
    mechanics_content: null,
    lore_links: [],
    mechanics_links: [],
    is_public: true,
    is_featured: false,
    featured_order: null,
    subject: 2,
    subject_name: 'Geography',
    subject_path: [
      { type: 'category', id: 1, name: 'The World' },
      { type: 'subject', id: 2, name: 'Geography' },
    ],
    display_order: 0,
    knowledge_status: 'known',
    known_by: [],
    learn_threshold: 10,
    research_progress: null,
    art_url: null,
    perspective_of: null,
    also_filed_under: [],
    ...overrides,
  };
}

function renderEntry(entry: CodexEntryDetail, onNavigateBreadcrumb = vi.fn()) {
  return render(<EntryDetail entry={entry} onNavigateBreadcrumb={onNavigateBreadcrumb} />, {
    wrapper: ({ children }) => <MemoryRouter>{children}</MemoryRouter>,
  });
}

describe('EntryDetail also_filed_under', () => {
  it('renders nothing for an empty list', () => {
    renderEntry(makeEntry({ also_filed_under: [] }));

    expect(screen.queryByText('Also filed under:', { exact: false })).not.toBeInTheDocument();
  });

  it('renders a breadcrumb link per secondary filing', () => {
    renderEntry(
      makeEntry({
        also_filed_under: [
          {
            subject_id: 5,
            name: 'Rites of Passage',
            breadcrumb_path: [
              { type: 'category', id: 1, name: 'Culture' },
              { type: 'subject', id: 5, name: 'Rites of Passage' },
            ],
          },
          {
            subject_id: 6,
            name: 'Border Disputes',
            breadcrumb_path: [
              { type: 'category', id: 1, name: 'Culture' },
              { type: 'subject', id: 6, name: 'Border Disputes' },
            ],
          },
        ],
      })
    );

    expect(screen.getByText('Also filed under:')).toBeInTheDocument();
    expect(screen.getByText('Rites of Passage')).toBeInTheDocument();
    expect(screen.getByText('Border Disputes')).toBeInTheDocument();
  });

  it('navigates to the filed subject when a secondary filing link is clicked', async () => {
    const onNavigateBreadcrumb = vi.fn();
    renderEntry(
      makeEntry({
        also_filed_under: [
          {
            subject_id: 5,
            name: 'Rites of Passage',
            breadcrumb_path: [
              { type: 'category', id: 1, name: 'Culture' },
              { type: 'subject', id: 5, name: 'Rites of Passage' },
            ],
          },
        ],
      }),
      onNavigateBreadcrumb
    );

    await userEvent.click(screen.getByText('Rites of Passage'));

    expect(onNavigateBreadcrumb).toHaveBeenCalledWith('subject', 5);
  });
});
