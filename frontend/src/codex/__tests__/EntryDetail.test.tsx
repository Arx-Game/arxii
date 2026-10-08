/**
 * Tests for EntryDetail's "Also filed under" line (#2896), its restricted-knowledge
 * reading (#4191) and the owner's companion beside and under the prose (#4198).
 *
 * A filed entry keeps one canonical home (`subject`/`subject_path`) but can
 * also be cross-listed under other subjects; the detail view renders those
 * as a quiet line of breadcrumb links beneath the canonical breadcrumb, and
 * renders nothing when the entry carries no filings.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { EntryDetail } from '../components/EntryDetail';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => ({
  ...(await vi.importActual<typeof import('react-router-dom')>('react-router-dom')),
  useNavigate: () => mockNavigate,
}));
import type { CodexEntryDetail } from '../types';

function makeEntry(overrides: Partial<CodexEntryDetail> = {}): CodexEntryDetail {
  return {
    id: 1,
    name: 'The Shroud',
    summary: 'A grey veil no army and no messenger ever crossed.',
    quote: '',
    companion: null,
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

describe('EntryDetail restricted tone', () => {
  const knower = {
    roster_entry_id: 7,
    character_name: 'Ilsavet',
    status: 'known' as const,
    research_progress: 0,
  };

  it('shifts the tone of a non-public entry and leaves a public one plain', () => {
    const { rerender } = render(
      <EntryDetail entry={makeEntry({ is_public: false })} onNavigateBreadcrumb={vi.fn()} />,
      { wrapper: ({ children }) => <MemoryRouter>{children}</MemoryRouter> }
    );
    expect(screen.getByText('The Shroud').closest('.codex-restricted')).not.toBeNull();

    rerender(<EntryDetail entry={makeEntry({ is_public: true })} onNavigateBreadcrumb={vi.fn()} />);
    expect(screen.getByText('The Shroud').closest('.codex-restricted')).toBeNull();
  });

  it('shows "Known by" only on a multi-character account', () => {
    const entry = makeEntry({ is_public: false, known_by: [knower] });
    const { rerender } = render(<EntryDetail entry={entry} onNavigateBreadcrumb={vi.fn()} />, {
      wrapper: ({ children }) => <MemoryRouter>{children}</MemoryRouter>,
    });
    expect(screen.queryByText('Known by:')).not.toBeInTheDocument();

    rerender(<EntryDetail entry={entry} multiCharacter onNavigateBreadcrumb={vi.fn()} />);
    expect(screen.getByText('Known by:')).toBeInTheDocument();
    expect(screen.getByText('Ilsavet')).toBeInTheDocument();
  });
});

describe('EntryDetail companion (#4198)', () => {
  const companion = {
    rail: [
      { label: 'Domains', items: [{ text: 'Carnage, Hunters', entry_id: null, anchor: null }] },
      {
        label: 'Feast days',
        items: [
          {
            text: 'The Reaping Festival · Masquing 18 (10/18)',
            entry_id: null,
            anchor: 'feast-10-18',
          },
        ],
      },
      {
        label: 'Cards',
        items: [
          { text: 'Death', entry_id: null, anchor: null },
          { text: 'The Tower reversed', entry_id: null, anchor: null },
        ],
      },
      { label: 'Feud', items: [{ text: 'Calyx', entry_id: 8, anchor: 'relationship-2' }] },
    ],
    sections: [
      {
        anchor: 'feast-10-18',
        label: 'Feast day',
        name: 'The Reaping Festival',
        when: 'Masquing 18 (10/18)',
        entry_id: null,
        body: 'Grand hunts and a feast of undercooked meat.',
      },
      {
        anchor: 'relationship-2',
        label: 'Feud',
        name: 'Calyx',
        when: null,
        entry_id: 8,
        body: 'She stole the first harvest.',
      },
    ],
  };

  it('draws nothing beside the prose when no owner claims the entry', () => {
    renderEntry(makeEntry({ companion: null }));
    expect(screen.queryByLabelText('At a glance')).not.toBeInTheDocument();
    expect(document.querySelector('.codex-with-rail')).toBeNull();
  });

  it('draws the rail beside the Lore and the sections under it', () => {
    renderEntry(makeEntry({ companion }));
    const rail = screen.getByLabelText('At a glance');
    expect(rail.closest('.codex-with-rail')).not.toBeNull();
    expect(rail).toHaveTextContent('Domains');
    expect(rail).toHaveTextContent('Carnage, Hunters');
    expect(rail).toHaveTextContent('Death, The Tower reversed');
    expect(
      screen.getByRole('link', { name: 'The Reaping Festival · Masquing 18 (10/18)' })
    ).toHaveAttribute('href', '#feast-10-18');
    const section = document.getElementById('feast-10-18');
    expect(section).toHaveTextContent('Feast day');
    expect(section).toHaveTextContent('The Reaping Festival');
    expect(section).toHaveTextContent('Masquing 18 (10/18)');
    expect(section).toHaveTextContent('Grand hunts and a feast of undercooked meat.');
    expect(document.getElementById('relationship-2')).toHaveTextContent(
      'She stole the first harvest.'
    );
  });

  it('a line to another god opens that entry', async () => {
    renderEntry(makeEntry({ companion }));
    await userEvent.click(
      within(screen.getByLabelText('At a glance')).getByRole('button', { name: 'Calyx' })
    );
    expect(mockNavigate).toHaveBeenCalledWith('/codex?entry=8');
  });
});
