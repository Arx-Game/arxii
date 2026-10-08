/**
 * CodexPage restricted-knowledge reading (#4191).
 *
 * Nothing on the page explains who sees what: the "Staff view" line (#3775) is
 * gone, and a non-public entry is told apart by a tone shift alone, in the search
 * results as on the cards.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { CodexPage } from '../pages/CodexPage';
import { mockStaffAccount } from '@/test/mocks/account';
import type { CodexEntryListItem } from '../types';

function makeEntry(overrides: Partial<CodexEntryListItem>): CodexEntryListItem {
  return {
    id: 1,
    name: 'Bene',
    summary: '',
    is_public: true,
    is_featured: false,
    featured_order: null,
    subject: 1,
    subject_name: 'Celestial',
    subject_path: [{ type: 'subject', id: 1, name: 'Celestial' }],
    display_order: 1,
    knowledge_status: null,
    known_by: [],
    art_url: null,
    perspective_of: null,
    also_filed_under: [],
    ...overrides,
  };
}

const RESULTS = [
  makeEntry({ id: 1, name: 'Bene' }),
  makeEntry({ id: 2, name: 'The Shroud', is_public: false, knowledge_status: 'known' }),
];

vi.mock('@/store/hooks', () => ({ useAccount: () => mockStaffAccount }));
vi.mock('@/hooks/useDebouncedValue', () => ({ useDebouncedValue: (value: string) => value }));
vi.mock('../queries', () => ({
  useCodexTree: () => ({ data: [], isLoading: false }),
  useCodexSearch: (query: string) => ({
    data: query.length >= 2 ? RESULTS : undefined,
    isLoading: false,
  }),
}));
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: () => ({ data: [] }),
}));

function renderPage() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <CodexPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('CodexPage restricted reading', () => {
  it('tells staff nothing about their view', () => {
    renderPage();
    expect(screen.queryByText(/Staff view/)).not.toBeInTheDocument();
  });

  it('shifts the tone of a non-public search result and leaves a public one plain', async () => {
    renderPage();
    await userEvent.type(screen.getByPlaceholderText('Search codex...'), 'sh');

    expect(screen.getByRole('button', { name: /The Shroud/ })).toHaveClass('codex-restricted');
    expect(screen.getByRole('button', { name: /Bene/ })).not.toHaveClass('codex-restricted');
  });
});
