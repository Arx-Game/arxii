/**
 * JournalRow tests (#3941) — the Reading Room's one row, collapsed and opened.
 *
 * Every dependency is mocked: the row is a leaf that must render standalone
 * (no QueryClientProvider, no router), so a stream of 20 rows costs 20 cheap
 * mounts and a unit test never needs the app's providers.
 */
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { JournalEntrySummary } from '../api';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/roster/queries', () => ({ useMyRosterEntriesQuery: () => ({ data: [] }) }));
vi.mock('@/progression/nominationQueries', () => ({
  useMyNominationsQuery: () => ({ data: [] }),
  useNominateMutation: () => ({ mutate: vi.fn(), isPending: false }),
  useWithdrawNominationMutation: () => ({ mutate: vi.fn(), isPending: false }),
}));
vi.mock('@/social/queries', () => ({
  useCreateMute: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateBlock: () => ({ mutate: vi.fn(), isPending: false }),
}));
const detail = vi.fn();
vi.mock('../queries', () => ({
  useJournalEntry: (id: number, enabled: boolean) => detail(id, enabled),
  useRespondToJournal: () => ({ mutate: vi.fn(), isPending: false }),
  useEditJournalEntry: () => ({ mutate: vi.fn(), isPending: false }),
  journalsKeys: { lists: () => ['journals', 'list'] },
}));

import { JournalRow } from '../components/JournalRow';

function entry(over: Partial<JournalEntrySummary> = {}): JournalEntrySummary {
  return {
    id: 3,
    author: 10,
    author_name: 'Ilsavet du Verane',
    title: 'On the matter of the harbor tolls',
    is_public: true,
    response_type: null,
    parent: null,
    created_at: '2026-09-17T10:00:00Z',
    edited_at: null,
    tags: [{ id: 1, name: 'harbor' }],
    response_count: 2,
    posthumous_override: 'inherit',
    revealed_at: null,
    is_posthumous: false,
    about: null,
    about_name: null,
    author_persona_id: 99,
    ic_timestamp: '1012-09-22T10:00:00Z',
    can_retort: false,
    is_own: false,
    ...over,
  };
}
const viewer = { sheetId: 20, personaId: 5, isStaff: false };

describe('JournalRow (#3941)', () => {
  it('collapsed shows writer, IC date, title and no actions', () => {
    detail.mockReturnValue({ data: undefined });
    render(<JournalRow entry={entry()} open={false} onToggle={vi.fn()} viewer={viewer} />);
    expect(screen.getByText('Ilsavet du Verane')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '22 September 1012' })).toBeInTheDocument();
    expect(screen.queryByText('Praise')).not.toBeInTheDocument();
    expect(screen.queryByText('harbor')).not.toBeInTheDocument();
  });

  it('flips the date without toggling the row', () => {
    detail.mockReturnValue({ data: undefined });
    const onToggle = vi.fn();
    render(<JournalRow entry={entry()} open={false} onToggle={onToggle} viewer={viewer} />);
    fireEvent.click(screen.getByRole('button', { name: '22 September 1012' }));
    expect(screen.getByRole('button', { name: '17 Sep 2026' })).toBeInTheDocument();
    expect(onToggle).not.toHaveBeenCalled();
  });

  it('open shows tags, Praise and Nominate, and no Retort without consent', () => {
    detail.mockReturnValue({ data: { body: 'Full text', responses: [] } });
    render(<JournalRow entry={entry()} open onToggle={vi.fn()} viewer={viewer} />);
    expect(screen.getByText('Full text')).toBeInTheDocument();
    expect(screen.getByText('harbor')).toBeInTheDocument();
    expect(screen.getByText('Praise')).toBeInTheDocument();
    expect(screen.queryByText('Retort')).not.toBeInTheDocument();
    expect(screen.queryByText('Condemn')).not.toBeInTheDocument();
    expect(screen.getByText('Mute writer')).toBeInTheDocument();
  });

  it('open shows Retort and Condemn when can_retort', () => {
    detail.mockReturnValue({ data: { body: 'Full text', responses: [] } });
    render(
      <JournalRow entry={entry({ can_retort: true })} open onToggle={vi.fn()} viewer={viewer} />
    );
    expect(screen.getAllByText('Retort').length).toBeGreaterThan(0);
    expect(screen.getAllByText('Condemn').length).toBeGreaterThan(0);
  });

  it('a black entry says only Black journal and a post mortem takes no actions', () => {
    detail.mockReturnValue({ data: { body: 'x', responses: [] } });
    const { rerender } = render(
      <JournalRow
        entry={entry({ is_public: false, is_own: true })}
        open
        onToggle={vi.fn()}
        viewer={viewer}
      />
    );
    expect(screen.getByText('Black journal')).toBeInTheDocument();
    expect(screen.queryByText(/yours alone/i)).not.toBeInTheDocument();
    expect(screen.getByText('Remain sealed')).toBeInTheDocument();
    rerender(
      <JournalRow
        entry={entry({
          is_public: false,
          revealed_at: '2026-09-16T00:00:00Z',
          is_posthumous: true,
        })}
        open
        onToggle={vi.fn()}
        viewer={viewer}
      />
    );
    expect(screen.getByText(/Post mortem/)).toBeInTheDocument();
    expect(screen.queryByText('Praise')).not.toBeInTheDocument();
  });
});
