/**
 * #885 — StoryTray / BeatCard / JournalPage interaction tests.
 *
 * Mocks the queries module so the components render against fixed data:
 * live-dot + compass on tray rows, option buttons + resolve flow on the
 * beat card, and the active/concluded split on the journal page.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import type { BeatView, JournalEntry, ResolvedBeat } from '../types';

const ACTIVE_ENTRY: JournalEntry = {
  instance_id: 7,
  template_name: 'The Merchant Debt',
  status: 'active',
  current_node_key: 'entry',
  is_contract_holder: true,
  deeds: [],
  summary: 'PLACEHOLDER a debt is owed.',
  epilogue: '',
  current_node_flavor: 'PLACEHOLDER find him.',
  compass_rooms: ['Lantern Row Inn', 'Merchants Guildhall'],
  compass_anywhere: false,
};

const DONE_ENTRY: JournalEntry = {
  ...ACTIVE_ENTRY,
  instance_id: 8,
  template_name: 'Old Business',
  status: 'complete',
  current_node_key: null,
  current_node_flavor: '',
  compass_rooms: [],
  epilogue: 'PLACEHOLDER it ended quietly.',
};

const LIVE_BEAT: BeatView = {
  instance_id: 7,
  template_name: 'The Merchant Debt',
  node_key: 'entry',
  flavor_text: 'PLACEHOLDER the warehouse is quiet.',
  options: [
    {
      option_id: 31,
      approach_id: null,
      label: 'PLACEHOLDER attack him',
      kind: 'branch',
      check_type_name: null,
      base_risk: 0,
    },
  ],
};

const RESOLVED: ResolvedBeat = {
  instance_id: 7,
  outcome_name: null,
  story_text: 'PLACEHOLDER you commit to it.',
  is_terminal: false,
  next_beat: null,
  epilogue: '',
};

const resolveMutate = vi.fn();
const useJournalMock = vi.fn();
const useBeatMock = vi.fn();

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useJournal: () => useJournalMock(),
    useBeat: (...args: unknown[]) => useBeatMock(...args),
    useResolveBeat: () => ({ mutate: resolveMutate, isPending: false, error: null }),
  };
});

import { BeatCard } from '../components/BeatCard';
import { StoryTray } from '../components/StoryTray';
import { JournalPage } from '../pages/JournalPage';

function withProviders(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe('StoryTray', () => {
  beforeEach(() => {
    resolveMutate.mockClear();
    useJournalMock.mockReturnValue({
      data: { count: 2, next: null, previous: null, results: [ACTIVE_ENTRY, DONE_ENTRY] },
      isLoading: false,
    });
    useBeatMock.mockReturnValue({ data: LIVE_BEAT, isLoading: false });
  });

  it('lists only active stories with the live dot and compass', () => {
    render(withProviders(<StoryTray roomKey="Warehouse" />));
    expect(screen.getByText('The Merchant Debt')).toBeInTheDocument();
    expect(screen.queryByText('Old Business')).not.toBeInTheDocument();
    expect(screen.getByTestId('story-live-dot')).toBeInTheDocument();
    expect(screen.getByTestId('story-compass')).toHaveTextContent(
      'Lantern Row Inn · Merchants Guildhall'
    );
  });

  it('shows the empty state with a journal link', () => {
    useJournalMock.mockReturnValue({
      data: { count: 0, next: null, previous: null, results: [] },
      isLoading: false,
    });
    render(withProviders(<StoryTray roomKey="Warehouse" />));
    expect(screen.getByTestId('story-tray-empty')).toBeInTheDocument();
  });

  it('hides the live dot when no options are live here', () => {
    useBeatMock.mockReturnValue({ data: { ...LIVE_BEAT, options: [] }, isLoading: false });
    render(withProviders(<StoryTray roomKey="Elsewhere" />));
    expect(screen.queryByTestId('story-live-dot')).not.toBeInTheDocument();
  });
});

describe('BeatCard', () => {
  beforeEach(() => {
    resolveMutate.mockClear();
    useBeatMock.mockReturnValue({ data: LIVE_BEAT, isLoading: false });
  });

  it('renders framing prose and option buttons', () => {
    render(withProviders(<BeatCard instanceId={7} roomKey="Warehouse" />));
    expect(screen.getByText('PLACEHOLDER the warehouse is quiet.')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /attack him/i })).toBeInTheDocument();
  });

  it('resolves the picked option and shows the result', async () => {
    resolveMutate.mockImplementation((_vars, opts) => opts?.onSuccess?.(RESOLVED));
    const user = userEvent.setup();
    render(withProviders(<BeatCard instanceId={7} roomKey="Warehouse" />));
    await user.click(screen.getByRole('button', { name: /attack him/i }));
    expect(resolveMutate).toHaveBeenCalledWith(
      { instanceId: 7, option_id: 31, approach_id: null },
      expect.anything()
    );
    expect(screen.getByTestId('beat-result')).toHaveTextContent('PLACEHOLDER you commit to it.');
  });

  it('shows the not-here hint when no options are live', () => {
    useBeatMock.mockReturnValue({ data: { ...LIVE_BEAT, options: [] }, isLoading: false });
    render(withProviders(<BeatCard instanceId={7} roomKey="Elsewhere" />));
    expect(screen.getByTestId('beat-not-here')).toBeInTheDocument();
  });
});

describe('JournalPage', () => {
  it('splits active and concluded, with compass and epilogue', () => {
    useJournalMock.mockReturnValue({
      data: { count: 2, next: null, previous: null, results: [ACTIVE_ENTRY, DONE_ENTRY] },
      isLoading: false,
    });
    render(withProviders(<JournalPage />));
    expect(screen.getByTestId('journal-entry-7')).toHaveTextContent('The Merchant Debt');
    expect(screen.getByTestId('journal-compass')).toHaveTextContent('Lantern Row Inn');
    expect(screen.getByTestId('journal-entry-8')).toHaveTextContent(
      'PLACEHOLDER it ended quietly.'
    );
  });
});
