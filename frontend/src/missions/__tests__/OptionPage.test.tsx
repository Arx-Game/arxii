/**
 * OptionPage - CONTEST kind fields (#3568): opposition_sheet,
 * opposition_check_type, and the authored_check_type Select shared with
 * CHECK (the page previously had no control for authored_check_type at
 * all). Mirrors DrillDownPageErrorCards.test.tsx's api-mocking pattern.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { MissionOption } from '../types';

vi.mock('../api', () => ({
  getMissionOption: vi.fn(),
  getMissionTemplate: vi.fn(),
  listMissionRoutes: vi.fn(),
  listPredicateLeaves: vi.fn(),
  patchMissionOption: vi.fn(),
  listMissionNodes: vi.fn(),
  listOutcomeTiers: vi.fn(),
  getGraphCheck: vi.fn(),
  createMissionRoute: vi.fn(),
  patchMissionRoute: vi.fn(),
  deleteMissionRoute: vi.fn(),
  deleteMissionOption: vi.fn(),
}));

vi.mock('@/gm-adjudication/queries', () => ({
  useCheckTypeCatalog: () => ({
    data: [
      {
        id: 7,
        name: 'Wrestling',
        category: 1,
        category_name: 'Combat',
        description: '',
        trait_summary: '',
      },
    ],
  }),
}));

import * as api from '../api';
import * as queries from '../queries';

import { OptionPage } from '../pages/OptionPage';

const CONTEST_OPTION: MissionOption = {
  id: 9,
  node: 5,
  order: 1,
  key: '',
  option_kind: 'contest',
  source_kind: 'authored',
  encounter_risk_level: '',
  visibility_rule: {},
  authored_check_type: null,
  authored_base_risk: 0,
  authored_ic_framing: '',
  authored_ic_framing_needs_rewrite: false,
  branch_target: null,
  challenge: null,
  opponent_lines: [],
  opposition_sheet: null,
  opposition_check_type: null,
} as MissionOption;

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

const page = (results: unknown[]) =>
  ({ count: results.length, next: null, previous: null, results }) as never;

const TIERS = [
  { id: 1, name: 'Failure', success_level: -1 },
  { id: 2, name: 'Success', success_level: 1 },
  { id: 3, name: 'Critical Success', success_level: 2 },
];
const NODES = [
  { id: 5, key: 'gate' },
  { id: 6, key: 'courtyard' },
];
const ROUTE = {
  id: 50,
  option: 9,
  outcome_tier: 2,
  target_node: 6,
  is_random_set: false,
  outcome_text: '',
  beat_outcome: '',
};

function makeWrapper(initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/staff/missions/:id/nodes/:nodeId/options/:optionId" element={children} />
          <Route path="*" element={<Where />} />
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
  vi.mocked(api.getMissionOption).mockResolvedValue(CONTEST_OPTION);
  vi.mocked(api.listMissionRoutes).mockResolvedValue({
    count: 0,
    next: null,
    previous: null,
    results: [],
  });
  vi.mocked(api.listPredicateLeaves).mockResolvedValue([]);
  vi.mocked(api.patchMissionOption).mockResolvedValue(CONTEST_OPTION);
  vi.mocked(api.listMissionNodes).mockResolvedValue(page(NODES));
  vi.mocked(api.listOutcomeTiers).mockResolvedValue(TIERS as never);
  vi.mocked(api.getGraphCheck).mockResolvedValue([]);
});

describe('OptionPage CONTEST fields', () => {
  it('renders opposition_sheet, opposition_check_type and authored_check_type controls', async () => {
    render(<OptionPage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5/options/9') });

    expect(await screen.findByLabelText('Opposition sheet id')).toBeInTheDocument();
    expect(screen.getByLabelText('Opposition check type')).toBeInTheDocument();
    expect(screen.getByLabelText('Check type')).toBeInTheDocument();
  });

  it('saves opposition_sheet, opposition_check_type and authored_check_type in the PATCH body', async () => {
    const user = userEvent.setup();
    render(<OptionPage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5/options/9') });

    const sheetInput = await screen.findByLabelText('Opposition sheet id');
    await user.clear(sheetInput);
    await user.type(sheetInput, '12');

    await user.click(screen.getByLabelText('Opposition check type'));
    await user.click(screen.getByRole('option', { name: 'Wrestling' }));

    await user.click(screen.getByLabelText('Check type'));
    await user.click(screen.getByRole('option', { name: 'Wrestling' }));

    await user.click(screen.getByRole('button', { name: /^save$/i }));

    expect(api.patchMissionOption).toHaveBeenCalledWith(
      9,
      expect.objectContaining({
        opposition_sheet: 12,
        opposition_check_type: 7,
        authored_check_type: 7,
      })
    );
  });

  it('does not render opposition fields for a BRANCH option', async () => {
    vi.mocked(api.getMissionOption).mockResolvedValue({
      ...CONTEST_OPTION,
      option_kind: 'branch',
      authored_check_type: null,
      opposition_sheet: null,
      opposition_check_type: null,
    });
    render(<OptionPage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5/options/9') });

    await screen.findByText('Option settings');
    expect(screen.queryByLabelText('Opposition sheet id')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Opposition check type')).not.toBeInTheDocument();
  });
});

describe('OptionPage opens_as_standoff', () => {
  it('shows the toggle for an ENCOUNTER option and saves it', async () => {
    const user = userEvent.setup();
    vi.mocked(api.getMissionOption).mockResolvedValue({
      ...CONTEST_OPTION,
      option_kind: 'encounter',
      opens_as_standoff: false,
    } as MissionOption);
    render(<OptionPage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5/options/9') });

    await user.click(await screen.findByLabelText('Opens as a standoff'));
    await user.click(screen.getByRole('button', { name: /^save$/i }));

    expect(api.patchMissionOption).toHaveBeenCalledWith(
      9,
      expect.objectContaining({ opens_as_standoff: true })
    );
  });

  it('hides the toggle for a non-ENCOUNTER option', async () => {
    render(<OptionPage />, { wrapper: makeWrapper('/staff/missions/1/nodes/5/options/9') });

    await screen.findByText('Option settings');
    expect(screen.queryByLabelText('Opens as a standoff')).toBeNull();
  });
});

describe('OptionPage route editor', () => {
  const url = '/staff/missions/1/nodes/5/options/9';

  it('shows each route with tier and destination by name', async () => {
    vi.mocked(api.listMissionRoutes).mockResolvedValue(page([ROUTE]));
    render(<OptionPage />, { wrapper: makeWrapper(url) });
    const row = await screen.findByTestId('route-row');
    expect(within(row).getByLabelText('Outcome tier')).toHaveTextContent('Success');
    expect(within(row).getByLabelText('Leads to')).toHaveTextContent('courtyard');
  });

  it('saves Mission ends as a null target', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listMissionRoutes).mockResolvedValue(page([ROUTE]));
    vi.mocked(api.patchMissionRoute).mockResolvedValue(ROUTE as never);
    render(<OptionPage />, { wrapper: makeWrapper(url) });
    const row = await screen.findByTestId('route-row');
    await user.click(within(row).getByLabelText('Leads to'));
    await user.click(screen.getByRole('option', { name: 'Mission ends' }));
    await user.click(within(row).getByRole('button', { name: 'Save route' }));
    expect(api.patchMissionRoute).toHaveBeenCalledWith(
      50,
      expect.objectContaining({ target_node: null, outcome_tier: 2, beat_outcome: '' })
    );
  });

  it('leaves a random route target alone when saving', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listMissionRoutes).mockResolvedValue(page([ROUTE]));
    vi.mocked(api.patchMissionRoute).mockResolvedValue(ROUTE as never);
    render(<OptionPage />, { wrapper: makeWrapper(url) });
    const row = await screen.findByTestId('route-row');
    await user.click(within(row).getByLabelText('Random set'));
    await user.click(within(row).getByRole('button', { name: 'Save route' }));
    const body = vi.mocked(api.patchMissionRoute).mock.calls[0][1];
    expect(body).toMatchObject({ is_random_set: true });
    expect(body).not.toHaveProperty('target_node');
  });

  it('shows the server message on the row', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listMissionRoutes).mockResolvedValue(page([ROUTE]));
    vi.mocked(api.patchMissionRoute).mockRejectedValue(new Error('A check route may not lead on.'));
    render(<OptionPage />, { wrapper: makeWrapper(url) });
    const row = await screen.findByTestId('route-row');
    await user.click(within(row).getByLabelText('Random set'));
    await user.click(within(row).getByRole('button', { name: 'Save route' }));
    expect(await within(row).findByText('A check route may not lead on.')).toBeInTheDocument();
  });

  it('adds a route with the first tier that has none', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listMissionRoutes).mockResolvedValue(page([ROUTE]));
    vi.mocked(api.createMissionRoute).mockResolvedValue(ROUTE as never);
    render(<OptionPage />, { wrapper: makeWrapper(url) });
    await user.click(await screen.findByRole('button', { name: 'Add route' }));
    expect(api.createMissionRoute).toHaveBeenCalledWith({
      option: 9,
      outcome_tier: 1,
      target_node: null,
    });
  });

  it('hides Add route for a branch option that already has its route', async () => {
    vi.mocked(api.getMissionOption).mockResolvedValue({
      ...CONTEST_OPTION,
      option_kind: 'branch',
    });
    vi.mocked(api.listMissionRoutes).mockResolvedValue(page([{ ...ROUTE, outcome_tier: null }]));
    render(<OptionPage />, { wrapper: makeWrapper(url) });
    await screen.findByTestId('route-row');
    expect(screen.queryByRole('button', { name: 'Add route' })).toBeNull();
  });

  it('adds the missing tiers one route each', async () => {
    const user = userEvent.setup();
    vi.mocked(api.listMissionRoutes).mockResolvedValue(page([]));
    vi.mocked(api.getGraphCheck).mockResolvedValue([
      {
        kind: 'missing_tiers',
        message: 'x',
        node: 5,
        option: 9,
        route: null,
        missing_tiers: ['Failure', 'Critical Success'],
      },
    ] as never);
    vi.mocked(api.createMissionRoute).mockResolvedValue(ROUTE as never);
    render(<OptionPage />, { wrapper: makeWrapper(url) });
    await user.click(await screen.findByRole('button', { name: 'Add the missing tiers' }));
    await vi.waitFor(() => expect(api.createMissionRoute).toHaveBeenCalledTimes(2));
    expect(api.createMissionRoute).toHaveBeenNthCalledWith(1, {
      option: 9,
      outcome_tier: 1,
      target_node: null,
    });
    expect(api.createMissionRoute).toHaveBeenNthCalledWith(2, {
      option: 9,
      outcome_tier: 3,
      target_node: null,
    });
  });

  it('deletes the option and returns to the node page', async () => {
    const user = userEvent.setup();
    vi.mocked(api.deleteMissionOption).mockResolvedValue(undefined);
    render(<OptionPage />, { wrapper: makeWrapper(url) });
    await user.click(await screen.findByRole('button', { name: 'Delete option' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Delete option' }));
    expect(await screen.findByTestId('where')).toHaveTextContent('/staff/missions/1/nodes/5');
    expect(api.deleteMissionOption).toHaveBeenCalledWith(9);
  });

  it('shows the server message when the option delete is refused', async () => {
    const user = userEvent.setup();
    vi.mocked(api.deleteMissionOption).mockRejectedValue(
      new Error('A mission run has used this option, so it cannot be deleted.')
    );
    render(<OptionPage />, { wrapper: makeWrapper(url) });
    await user.click(await screen.findByRole('button', { name: 'Delete option' }));
    const dialog = await screen.findByRole('dialog');
    await user.click(within(dialog).getByRole('button', { name: 'Delete option' }));
    expect(
      await within(dialog).findByText(
        'A mission run has used this option, so it cannot be deleted.'
      )
    ).toBeInTheDocument();
  });
});
