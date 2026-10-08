/**
 * Tests for EntryGrid's "filed from <canonical subject>" gloss (#2896) and its
 * restricted-knowledge reading (#4191).
 *
 * A subject listing can include entries filed there from elsewhere; the grid
 * glosses those cards with their canonical subject so browsing stays honest
 * about which listing is the entry's real home.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { EntryGrid } from '../components/EntryGrid';
import type { CodexEntryListItem } from '../types';

function makeEntry(overrides: Partial<CodexEntryListItem> = {}): CodexEntryListItem {
  return {
    id: 1,
    name: 'Bene',
    summary: 'Resonance of giving',
    is_public: true,
    is_featured: false,
    featured_order: null,
    subject: 1,
    subject_name: 'Celestial',
    subject_path: [],
    display_order: 1,
    knowledge_status: null,
    known_by: [],
    art_url: null,
    perspective_of: null,
    also_filed_under: [],
    ...overrides,
  };
}

describe('EntryGrid filed-from gloss', () => {
  it('shows no gloss for an entry canonical to the browsed subject', () => {
    render(
      <EntryGrid entries={[makeEntry({ subject: 1 })]} subjectId={1} onSelectEntry={vi.fn()} />
    );

    expect(screen.queryByText('Filed from', { exact: false })).not.toBeInTheDocument();
  });

  it('shows no gloss when the browsed subject is unknown', () => {
    render(<EntryGrid entries={[makeEntry({ subject: 1 })]} onSelectEntry={vi.fn()} />);

    expect(screen.queryByText('Filed from', { exact: false })).not.toBeInTheDocument();
  });

  it('glosses an entry filed here from its canonical subject', () => {
    render(
      <EntryGrid
        entries={[makeEntry({ subject: 9, subject_name: 'Celestial' })]}
        subjectId={1}
        onSelectEntry={vi.fn()}
      />
    );

    expect(screen.getByText('Filed from Celestial')).toBeInTheDocument();
  });
});

const KNOWER = {
  roster_entry_id: 7,
  character_name: 'Ilsavet',
  status: 'known' as const,
  research_progress: 0,
};

describe('EntryGrid restricted tone', () => {
  it('shifts the tone of a non-public entry and writes nothing', () => {
    render(
      <EntryGrid
        entries={[makeEntry({ is_public: false, knowledge_status: 'known' })]}
        onSelectEntry={vi.fn()}
      />
    );

    expect(screen.getByText('Bene').closest('.codex-restricted')).not.toBeNull();
    expect(screen.queryByText(/restricted|private|secret/i)).not.toBeInTheDocument();
  });

  it('leaves a public entry plain', () => {
    render(<EntryGrid entries={[makeEntry({ is_public: true })]} onSelectEntry={vi.fn()} />);

    expect(screen.getByText('Bene').closest('.codex-restricted')).toBeNull();
  });

  it('shows the per-character badges only on a multi-character account', () => {
    const entry = makeEntry({ is_public: false, knowledge_status: 'known', known_by: [KNOWER] });
    const { rerender } = render(<EntryGrid entries={[entry]} onSelectEntry={vi.fn()} />);
    expect(screen.queryByText('Ilsavet')).not.toBeInTheDocument();

    rerender(<EntryGrid entries={[entry]} multiCharacter onSelectEntry={vi.fn()} />);
    expect(screen.getByText('Ilsavet')).toBeInTheDocument();
  });
});
