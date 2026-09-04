/**
 * NodePage - progress track fields (#3568): track_successes/track_failures
 * thresholds, track_success_target/track_failure_target (over the
 * template's other nodes, or terminal), and the two beat-outcome
 * overrides. Mirrors DrillDownPageErrorCards.test.tsx's api-mocking
 * pattern.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { MissionNode } from '../types';

vi.mock('../api', () => ({
  getMissionNode: vi.fn(),
  getMissionTemplate: vi.fn(),
  listMissionNodes: vi.fn(),
  listMissionOptions: vi.fn(),
  patchMissionNode: vi.fn(),
}));

import * as api from '../api';
import * as queries from '../queries';

import { NodePage } from '../pages/NodePage';

const TRACK_NODE: MissionNode = {
  id: 5,
  template: 1,
  key: 'siege',
  is_entry: false,
  conflict_mode: 'group_vote',
  joint_combine: null,
  joint_count: null,
  allowed_riders: [],
  deny_all_riders: false,
  editor_x: 0,
  editor_y: 0,
  flavor_text: '',
  flavor_text_needs_rewrite: false,
  track_successes: 0,
  track_failures: 0,
  track_success_target: null,
  track_failure_target: null,
  track_success_beat_outcome: '',
  track_failure_beat_outcome: '',
} as MissionNode;

const OTHER_NODE: MissionNode = {
  ...TRACK_NODE,
  id: 6,
  key: 'aftermath',
};

function makeWrapper(initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/staff/missions/:id/nodes/:nodeId" element={children} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.spyOn(queries, 'useMissionTemplate').mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof queries.useMissionTemplate>);
  vi.mocked(api.getMissionNode).mockResolvedValue(TRACK_NODE);
  vi.mocked(api.listMissionOptions).mockResolvedValue({
    count: 0,
    next: null,
    previous: null,
    results: [],
  });
  vi.mocked(api.listMissionNodes).mockResolvedValue({
    count: 2,
    next: null,
    previous: null,
    results: [TRACK_NODE, OTHER_NODE],
  });
  vi.mocked(api.patchMissionNode).mockResolvedValue(TRACK_NODE);
});

describe('NodePage progress track', () => {
  it('renders the track threshold, target, and beat-outcome controls', async () => {
    render(<NodePage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5') });

    expect(await screen.findByLabelText('Successes needed')).toBeInTheDocument();
    expect(screen.getByLabelText('Failures allowed')).toBeInTheDocument();
    expect(screen.getByLabelText('On track success, go to')).toBeInTheDocument();
    expect(screen.getByLabelText('On track failure, go to')).toBeInTheDocument();
    expect(screen.getByLabelText('Success beat outcome')).toBeInTheDocument();
    expect(screen.getByLabelText('Failure beat outcome')).toBeInTheDocument();
  });

  it('does not offer the current node as its own track target', async () => {
    render(<NodePage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5') });

    const user = userEvent.setup();
    await user.click(await screen.findByLabelText('On track success, go to'));
    expect(screen.getByRole('option', { name: 'aftermath' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'siege' })).not.toBeInTheDocument();
  });

  it('saves track thresholds, targets, and beat outcomes in the PATCH body', async () => {
    const user = userEvent.setup();
    render(<NodePage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5') });

    const successes = await screen.findByLabelText('Successes needed');
    await user.clear(successes);
    await user.type(successes, '3');

    const failures = screen.getByLabelText('Failures allowed');
    await user.clear(failures);
    await user.type(failures, '2');

    await user.click(screen.getByLabelText('On track success, go to'));
    await user.click(screen.getByRole('option', { name: 'aftermath' }));

    await user.click(screen.getByLabelText('Success beat outcome'));
    await user.click(screen.getByRole('option', { name: 'success' }));

    await user.click(screen.getByRole('button', { name: /^save$/i }));

    expect(api.patchMissionNode).toHaveBeenCalledWith(
      5,
      expect.objectContaining({
        track_successes: 3,
        track_failures: 2,
        track_success_target: 6,
        track_failure_target: null,
        track_success_beat_outcome: 'success',
        track_failure_beat_outcome: '',
      })
    );
  });
});
