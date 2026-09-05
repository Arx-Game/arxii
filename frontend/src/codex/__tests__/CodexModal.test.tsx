/**
 * Tests for CodexModal back/forward navigation.
 *
 * Verifies that clicking an inline link navigates to the new entry,
 * and that back/forward buttons work correctly.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { CodexModal } from '../components/CodexModal';
import { EntryDetail } from '../components/EntryDetail';
import type { CodexEntryDetail } from '../types';

// Mock the API module
vi.mock('../api', () => ({
  getEntry: vi.fn(),
  getCodexTree: vi.fn(),
  getEntries: vi.fn(),
  searchEntries: vi.fn(),
  getSubject: vi.fn(),
  getSubjectChildren: vi.fn(),
}));

import * as api from '../api';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

function makeEntry(
  id: number,
  name: string,
  loreContent: string,
  links: CodexEntryDetail['lore_links'],
  artUrl: string | null = null,
  perspectiveOf: string | null = null
): CodexEntryDetail {
  return {
    id,
    name,
    summary: `${name} summary`,
    lore_content: loreContent,
    mechanics_content: null,
    lore_links: links,
    mechanics_links: [],
    is_public: true,
    is_featured: false,
    featured_order: null,
    subject: 1,
    subject_name: 'Test Subject',
    subject_path: [
      { type: 'category' as const, id: 1, name: 'Test Category' },
      { type: 'subject' as const, id: 2, name: 'Test Subject' },
    ],
    display_order: 0,
    knowledge_status: 'known' as const,
    known_by: [],
    learn_threshold: 10,
    research_progress: null,
    art_url: artUrl,
    perspective_of: perspectiveOf,
    also_filed_under: [],
  };
}

describe('CodexModal navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows back button after navigating to a linked entry', async () => {
    const entry1 = makeEntry(1, 'First Entry', 'See [[Second Entry]].', [
      {
        match_text: '[[Second Entry]]',
        entry_id: 2,
        display_text: 'Second Entry',
        accessible: true,
      },
    ]);
    const entry2 = makeEntry(2, 'Second Entry', 'No links here.', []);

    vi.mocked(api.getEntry).mockImplementation(async (id: number) => {
      if (id === 1) return entry1;
      if (id === 2) return entry2;
      throw new Error('Not found');
    });

    render(<CodexModal entryId={1} open={true} onOpenChange={vi.fn()} />, {
      wrapper: createWrapper(),
    });

    // Wait for first entry to load
    await waitFor(() => {
      expect(screen.getByText('First Entry')).toBeInTheDocument();
    });

    // No back button initially
    expect(screen.queryByLabelText('Go back')).not.toBeInTheDocument();

    // Click the inline link
    await userEvent.click(screen.getByText('Second Entry'));

    // Wait for second entry to load
    await waitFor(() => {
      expect(screen.getByText('Second Entry')).toBeInTheDocument();
    });

    // Back button should now be visible
    expect(screen.getByLabelText('Go back')).toBeInTheDocument();
  });

  it('navigates back to previous entry', async () => {
    const entry1 = makeEntry(1, 'First Entry', 'See [[Second Entry]].', [
      {
        match_text: '[[Second Entry]]',
        entry_id: 2,
        display_text: 'Second Entry',
        accessible: true,
      },
    ]);
    const entry2 = makeEntry(2, 'Second Entry', 'No links here.', []);

    vi.mocked(api.getEntry).mockImplementation(async (id: number) => {
      if (id === 1) return entry1;
      if (id === 2) return entry2;
      throw new Error('Not found');
    });

    render(<CodexModal entryId={1} open={true} onOpenChange={vi.fn()} />, {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(screen.getByText('First Entry')).toBeInTheDocument();
    });

    // Navigate forward
    await userEvent.click(screen.getByText('Second Entry'));
    await waitFor(() => {
      expect(screen.getByText('Second Entry')).toBeInTheDocument();
    });

    // Navigate back
    await userEvent.click(screen.getByLabelText('Go back'));
    await waitFor(() => {
      expect(screen.getByText('First Entry')).toBeInTheDocument();
    });

    // Forward button should now be visible
    expect(screen.getByLabelText('Go forward')).toBeInTheDocument();
  });

  it('renders the entry art when art_url is present', async () => {
    const entry = makeEntry(
      1,
      'The Shroud',
      'A veil between worlds.',
      [],
      'https://example.com/shroud.jpg'
    );

    vi.mocked(api.getEntry).mockResolvedValue(entry);

    render(<CodexModal entryId={1} open={true} onOpenChange={vi.fn()} />, {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(screen.getByText('The Shroud')).toBeInTheDocument();
    });

    const img = screen.getByRole('img', { name: /The Shroud/i });
    expect(img).toHaveAttribute('src', 'https://example.com/shroud.jpg');
  });

  it('renders nothing extra when art_url is null', async () => {
    const entry = makeEntry(2, 'The Flickering', 'Something dim.', [], null);

    vi.mocked(api.getEntry).mockResolvedValue(entry);

    render(<CodexModal entryId={2} open={true} onOpenChange={vi.fn()} />, {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(screen.getByText('The Flickering')).toBeInTheDocument();
    });

    expect(screen.queryByRole('img')).not.toBeInTheDocument();
  });

  it('shows the attribution line when perspective_of is set', () => {
    const entry = makeEntry(3, 'The Cleansing', 'A rite of purification.', [], null, 'The Blessed');

    render(<EntryDetail entry={entry} onNavigateBreadcrumb={vi.fn()} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByText('As told by The Blessed')).toBeInTheDocument();
  });

  it('hides the attribution line when perspective_of is null', () => {
    const entry = makeEntry(4, 'The Reckoning', 'A canon entry.', [], null, null);

    render(<EntryDetail entry={entry} onNavigateBreadcrumb={vi.fn()} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByText('As told by', { exact: false })).not.toBeInTheDocument();
  });

  it('CodexModal shows the attribution line when perspective_of is set', async () => {
    const entry = makeEntry(5, 'The Vigil', 'A watch kept in silence.', [], null, 'les Ouwoux');

    vi.mocked(api.getEntry).mockResolvedValue(entry);

    render(<CodexModal entryId={5} open={true} onOpenChange={vi.fn()} />, {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(screen.getByText('The Vigil')).toBeInTheDocument();
    });

    expect(screen.getByText('As told by les Ouwoux')).toBeInTheDocument();
  });

  it('CodexModal hides the attribution line when perspective_of is null', async () => {
    const entry = makeEntry(6, 'The Founding', 'A canon entry.', [], null, null);

    vi.mocked(api.getEntry).mockResolvedValue(entry);

    render(<CodexModal entryId={6} open={true} onOpenChange={vi.fn()} />, {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(screen.getByText('The Founding')).toBeInTheDocument();
    });

    expect(screen.queryByText('As told by', { exact: false })).not.toBeInTheDocument();
  });
});

describe('CodexModal when the entry cannot be loaded', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('says which entry is unavailable instead of throwing to the page boundary', async () => {
    // play.arx2.com 2026-09-02: a heritage card linked an entry the viewer had
    // no knowledge row for, the 404 threw out of the modal, and the whole
    // character-creation stage was replaced by "Stage Error".
    vi.mocked(api.getEntry).mockRejectedValue(new Error('Failed to load entry'));
    render(<CodexModal entryId={106} open onOpenChange={() => {}} />, {
      wrapper: createWrapper(),
    });
    const notice = await screen.findByRole('alert');
    expect(notice.textContent).toMatch(/entry 106/i);
    expect(notice.textContent).toMatch(/not available/i);
  });
});
