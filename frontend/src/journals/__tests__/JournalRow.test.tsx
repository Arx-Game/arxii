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
    body: 'The tolls are the harbour and the harbour is the city.',
    kind: 'entry',
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

  it('reads its prose off the row itself, with nothing fetched while it is shut', () => {
    detail.mockReturnValue({ data: undefined });
    render(<JournalRow entry={entry()} open={false} onToggle={vi.fn()} viewer={viewer} />);

    expect(
      screen.getByText('The tolls are the harbour and the harbour is the city.')
    ).toBeInTheDocument();
    // The detail query exists for the responses, and stays disabled until the row opens.
    expect(detail).toHaveBeenCalledWith(3, false);
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

  it('an Introduction wears its own name in the band', () => {
    detail.mockReturnValue({ data: { body: 'x', responses: [] } });
    render(
      <JournalRow
        entry={entry({ kind: 'first_journal' })}
        open={false}
        onToggle={vi.fn()}
        viewer={viewer}
      />
    );
    expect(screen.getByText('First Journal')).toBeInTheDocument();
  });

  it('shows each response in full, without a second request for it', () => {
    detail.mockReturnValue({
      data: {
        body: 'Full text',
        responses: [
          {
            ...entry(),
            id: 44,
            author_name: 'Corvin Ashe',
            title: 'The tolls are a tax on bread',
            body: 'You name the harbour and mean the granary.',
            response_type: 'retort',
          },
        ],
      },
    });
    render(<JournalRow entry={entry()} open onToggle={vi.fn()} viewer={viewer} />);

    expect(screen.getByText('The tolls are a tax on bread')).toBeInTheDocument();
    expect(screen.getByText('You name the harbour and mean the granary.')).toBeInTheDocument();
    expect(screen.getByText('retort')).toBeInTheDocument();
    // One detail query for the row; none for the response it already has in hand.
    expect(detail).not.toHaveBeenCalledWith(44, expect.anything());
  });

  it('offers a black row no Mute or Block, even to staff reading it', () => {
    detail.mockReturnValue({ data: { body: 'x', responses: [] } });
    render(
      <JournalRow
        entry={entry({ is_public: false, is_own: false })}
        open
        onToggle={vi.fn()}
        viewer={{ sheetId: 20, personaId: 5, isStaff: true }}
      />
    );

    expect(screen.getByText('Black journal')).toBeInTheDocument();
    expect(screen.queryByText('Mute writer')).not.toBeInTheDocument();
    expect(screen.queryByText('Block writer')).not.toBeInTheDocument();
    expect(screen.queryByText('Praise')).not.toBeInTheDocument();
  });
});
