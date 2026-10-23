/**
 * NodePage - progress track fields (#3568): track_successes/track_failures
 * thresholds, track_success_target/track_failure_target (over the
 * template's other nodes, or terminal), and the two beat-outcome
 * overrides. Mirrors DrillDownPageErrorCards.test.tsx's api-mocking
 * pattern.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { MissionNode } from '../types';

vi.mock('../api', () => ({
  getMissionNode: vi.fn(),
  getMissionTemplate: vi.fn(),
  listMissionNodes: vi.fn(),
  listMissionOptions: vi.fn(),
  patchMissionNode: vi.fn(),
  listMissionRoutes: vi.fn(),
  listRouteCandidates: vi.fn(),
  getGraphCheck: vi.fn(),
  listOutcomeTiers: vi.fn(),
  createMissionOption: vi.fn(),
  deleteMissionNode: vi.fn(),
  copyNode: vi.fn(),
  copySubtree: vi.fn(),
}));

vi.mock('@/gm-adjudication/queries', () => ({
  useCheckTypeCatalog: () => ({ data: [{ id: 7, name: 'Wrestling' }] }),
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

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

const page = (results: unknown[]) =>
  ({ count: results.length, next: null, previous: null, results }) as never;

function makeWrapper(initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/staff/missions/:id/nodes/:nodeId" element={children} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

afterEach(() => {
  // A dialog unmounted by navigation can leave Radix's body lock behind.
  document.body.style.pointerEvents = '';
});

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
  vi.mocked(api.listMissionRoutes).mockResolvedValue(page([]));
  vi.mocked(api.listRouteCandidates).mockResolvedValue(page([]));
  vi.mocked(api.getGraphCheck).mockResolvedValue([]);
  vi.mocked(api.listOutcomeTiers).mockResolvedValue([
    { id: 2, name: 'Success', success_level: 1, rolled_by_checks: true },
  ]);
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

const OPT = (over: Record<string, unknown>) => ({
  id: 20,
  node: 5,
  order: 1,
  key: 'dig',
  option_kind: 'check',
  source_kind: 'authored',
  authored_ic_framing: 'Dig in',
  branch_target: null,
  ...over,
});

describe('NodePage graph controls', () => {
  it('adds an option with order one past the highest existing order', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listMissionOptions).mockResolvedValue(
      page([OPT({ id: 20, order: 1 }), OPT({ id: 21, order: 4, key: 'run' })])
    );
    vi.mocked(api.createMissionOption).mockResolvedValue(OPT({ id: 22, order: 5 }) as never);
    render(<NodePage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5') });

    await user.click(await screen.findByRole('button', { name: 'Add option' }));
    await user.type(await screen.findByLabelText('Option key'), 'flee');
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Add option' }));

    expect(api.createMissionOption).toHaveBeenCalledWith({
      node: 5,
      key: 'flee',
      option_kind: 'branch',
      order: 5,
      source_kind: 'authored',
    });
    expect(await screen.findByTestId('where')).toHaveTextContent(
      '/staff/missions/1/nodes/5/options/22'
    );
  });

  it('posts authored_check_type for a Check option and waits for a check type', async () => {
    const user = userEvent.setup();
    vi.mocked(api.createMissionOption).mockResolvedValue(OPT({ id: 22, order: 1 }) as never);
    render(<NodePage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5') });

    await user.click(await screen.findByRole('button', { name: 'Add option' }));
    await user.type(await screen.findByLabelText('Option key'), 'dig');
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByLabelText('Option kind'));
    await user.click(screen.getByRole('option', { name: 'Check' }));

    const submit = within(dialog).getByRole('button', { name: 'Add option' });
    expect(submit).toBeDisabled();
    await user.click(within(dialog).getByLabelText('Check type'));
    await user.click(screen.getByRole('option', { name: 'Wrestling' }));
    expect(submit).toBeEnabled();
    await user.click(submit);

    expect(api.createMissionOption).toHaveBeenCalledWith({
      node: 5,
      key: 'dig',
      option_kind: 'check',
      order: 1,
      source_kind: 'authored',
      authored_check_type: 7,
    });
  });

  it('offers only Branch, Check and Contest on a track node', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getMissionNode).mockResolvedValue({ ...TRACK_NODE, track_successes: 3 });
    render(<NodePage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5') });

    await user.click(await screen.findByRole('button', { name: 'Add option' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByLabelText('Option kind'));
    const names = screen.getAllByRole('option').map((o) => o.textContent);
    expect(names).toEqual(['Branch', 'Check', 'Contest']);
    await user.keyboard('{Escape}');
    await user.keyboard('{Escape}');
  });

  it('offers only Technique Cast as the act off the entry node', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getMissionNode).mockResolvedValue({ ...TRACK_NODE, is_entry: false });
    render(<NodePage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5') });

    await user.click(await screen.findByRole('button', { name: 'Add option' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByLabelText('Option kind'));
    await user.click(screen.getByRole('option', { name: 'External act' }));
    await user.click(within(dialog).getByLabelText('Act'));
    const names = screen.getAllByRole('option').map((o) => o.textContent);
    expect(names).toEqual(['Technique Cast']);
    await user.keyboard('{Escape}');
    await user.keyboard('{Escape}');
  });

  it('marks an option the graph check has a problem with', async () => {
    vi.mocked(api.listMissionOptions).mockResolvedValue(page([OPT({ id: 20 })]));
    vi.mocked(api.getGraphCheck).mockResolvedValue([
      { kind: 'missing_tiers', message: 'x', node: 5, option: 20, route: null, missing_tiers: [] },
    ] as never);
    render(<NodePage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5') });
    expect(await screen.findByLabelText('Has a problem')).toBeInTheDocument();
  });

  it('lists an incoming route in the delete confirmation', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listMissionNodes).mockResolvedValue(page([TRACK_NODE, OTHER_NODE]));
    vi.mocked(api.listMissionOptions).mockImplementation((async (f: { node?: number }) =>
      f.node ? page([]) : page([OPT({ id: 30, node: 6, key: 'knock' })])) as never);
    vi.mocked(api.listMissionRoutes).mockResolvedValue(
      page([{ id: 40, option: 30, target_node: 5, outcome_tier: 2 }])
    );
    render(<NodePage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5') });

    await user.click(await screen.findByRole('button', { name: 'Delete node' }));
    const dialog = await screen.findByRole('dialog');
    expect(await within(dialog).findByText('aftermath: knock · Success')).toBeInTheDocument();
    expect(within(dialog).getByText('These will become a mission ending')).toBeInTheDocument();
  });

  it('shows the server message when the delete is refused', async () => {
    const user = userEvent.setup();
    vi.mocked(api.deleteMissionNode).mockRejectedValue(
      new Error('A mission run has used this node, so it cannot be deleted.')
    );
    render(<NodePage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5') });

    await user.click(await screen.findByRole('button', { name: 'Delete node' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Delete node' }));
    expect(
      await within(dialog).findByText('A mission run has used this node, so it cannot be deleted.')
    ).toBeInTheDocument();
  });

  it('copies the node and opens the copy', async () => {
    const user = userEvent.setup();
    vi.mocked(api.copyNode).mockResolvedValue({ ...OTHER_NODE, id: 77, key: 'siege-2' });
    render(<NodePage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5') });

    await user.click(await screen.findByRole('button', { name: 'Copy node' }));
    await user.type(await screen.findByLabelText('New node key'), 'siege-2');
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Copy node' }));

    expect(api.copyNode).toHaveBeenCalledWith(5, { new_key: 'siege-2' });
    await vi.waitFor(() => expect(api.getMissionNode).toHaveBeenCalledWith(77));
  });

  it('copies the node and everything after it with a key prefix', async () => {
    const user = userEvent.setup();
    vi.mocked(api.copySubtree).mockResolvedValue({ ...OTHER_NODE, id: 88, key: 'b-siege' });
    render(<NodePage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5') });

    await user.click(
      await screen.findByRole('button', { name: 'Copy node and everything after it' })
    );
    await user.type(await screen.findByLabelText('Key prefix'), 'b-');
    const dialog = screen.getByRole('dialog');
    await user.click(
      within(dialog).getByRole('button', { name: 'Copy node and everything after it' })
    );

    expect(api.copySubtree).toHaveBeenCalledWith(5, { new_key_prefix: 'b-' });
    await vi.waitFor(() => expect(api.getMissionNode).toHaveBeenCalledWith(88));
  });
});
