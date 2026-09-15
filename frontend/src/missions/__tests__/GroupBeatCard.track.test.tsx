/**
 * GroupBeatCard track pips (#3568) - beat.track renders as two Pips rows
 * above the options; a null track renders nothing.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { Provider } from 'react-redux';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { store } from '@/store/store';
import type { GroupBeatResult } from '../types';

const TRACK_BEAT: GroupBeatResult = {
  group_beat: {
    instance_id: 7,
    node_key: 'entry',
    flavor_text: 'PLACEHOLDER the siege drags on.',
    conflict_mode: 'group_vote',
    phase: 'pick',
    options: [
      {
        option_id: 31,
        approach_id: null,
        label: 'PLACEHOLDER press the assault',
        kind: 'check',
        check_type_name: null,
        base_risk: 0,
      },
    ],
    ballots: [],
    expires_at: null,
    is_paused: false,
    track: { successes: 1, needed: 3, failures: 0, allowed: 2 },
  },
  resolved: null,
};

const NO_TRACK_BEAT: GroupBeatResult = {
  group_beat: { ...TRACK_BEAT.group_beat!, track: null },
  resolved: null,
};

const useGroupBeatMock = vi.fn();

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useGroupBeat: (...args: unknown[]) => useGroupBeatMock(...args),
    useSubmitGroupPick: () => ({ mutate: vi.fn(), isPending: false, error: null }),
    useCastGroupVote: () => ({ mutate: vi.fn(), isPending: false, error: null }),
  };
});

import { GroupBeatCard } from '../components/GroupBeatCard';

function withProviders(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  // Redux Provider: the unmocked player hooks (InvitePicker's
  // useInviteToMission) read the tab's browsing identity from the store (#3479).
  return (
    <Provider store={store}>
      <QueryClientProvider client={qc}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    </Provider>
  );
}

describe('GroupBeatCard track pips', () => {
  it('renders successes and failures pip rows when beat.track is set', () => {
    useGroupBeatMock.mockReturnValue({ data: TRACK_BEAT, isLoading: false });
    render(withProviders(<GroupBeatCard instanceId={7} roomKey="Siege Camp" />));

    const track = screen.getByTestId('beat-track');
    expect(track).toBeInTheDocument();
    expect(screen.getByTestId('beat-track-successes')).toHaveTextContent('1/3');
    expect(screen.getByTestId('beat-track-failures')).toHaveTextContent('0/2');
  });

  it('renders no track section when beat.track is null', () => {
    useGroupBeatMock.mockReturnValue({ data: NO_TRACK_BEAT, isLoading: false });
    render(withProviders(<GroupBeatCard instanceId={7} roomKey="Siege Camp" />));

    expect(screen.queryByTestId('beat-track')).not.toBeInTheDocument();
  });
});
