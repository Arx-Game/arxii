/**
 * OptionPage - CONTEST kind fields (#3568): opposition_sheet,
 * opposition_check_type, and the authored_check_type Select shared with
 * CHECK (the page previously had no control for authored_check_type at
 * all). Mirrors DrillDownPageErrorCards.test.tsx's api-mocking pattern.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { MissionOption } from '../types';

vi.mock('../api', () => ({
  getMissionOption: vi.fn(),
  getMissionTemplate: vi.fn(),
  listMissionRoutes: vi.fn(),
  listPredicateLeaves: vi.fn(),
  patchMissionOption: vi.fn(),
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

function makeWrapper(initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/staff/missions/:id/nodes/:nodeId/options/:optionId" element={children} />
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
