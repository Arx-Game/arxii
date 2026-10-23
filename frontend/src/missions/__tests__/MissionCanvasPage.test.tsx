/**
 * MissionCanvasPage - Problems panel, node click navigation, Add node (#4558).
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { GraphProblem, MissionNode } from '../types';

vi.mock('@xyflow/react', async () => {
  const actual = await vi.importActual<typeof import('@xyflow/react')>('@xyflow/react');
  return {
    ...actual,
    // jsdom has no layout engine: render each node as a button that fires onNodeClick.
    ReactFlow: ({
      nodes,
      onNodeClick,
    }: {
      nodes: { id: string; data: { label: string } }[];
      onNodeClick: (e: unknown, n: unknown) => void;
    }) => (
      <div>
        {nodes.map((n) => (
          <button key={n.id} onClick={(e) => onNodeClick(e, n)}>
            {n.data.label}
          </button>
        ))}
      </div>
    ),
    Background: () => null,
    Controls: () => null,
  };
});

vi.mock('../api', () => ({
  getMissionTemplate: vi.fn(),
  listMissionNodes: vi.fn(),
  listMissionOptions: vi.fn(),
  listMissionRoutes: vi.fn(),
  listRouteCandidates: vi.fn(),
  listOutcomeTiers: vi.fn(),
  getGraphCheck: vi.fn(),
  createMissionNode: vi.fn(),
  patchMissionNode: vi.fn(),
}));

import * as api from '../api';
import { MissionCanvasPage } from '../pages/MissionCanvasPage';

const page = (results: unknown[]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});

const NODE = {
  id: 5,
  template: 1,
  key: 'gate',
  is_entry: true,
  editor_x: 0,
  editor_y: 0,
} as MissionNode;

function Where() {
  return <div data-testid="where">{useLocation().pathname}</div>;
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/staff/missions/1/canvas']}>
        <Routes>
          <Route path="/staff/missions/:id/canvas" element={children} />
          <Route path="*" element={<Where />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  return render(<MissionCanvasPage />, { wrapper });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.getMissionTemplate).mockResolvedValue({ id: 1, name: 'Siege' } as never);
  vi.mocked(api.listMissionNodes).mockResolvedValue(page([NODE]) as never);
  vi.mocked(api.listMissionOptions).mockResolvedValue(page([]) as never);
  vi.mocked(api.listMissionRoutes).mockResolvedValue(page([]) as never);
  vi.mocked(api.listRouteCandidates).mockResolvedValue(page([]) as never);
  vi.mocked(api.listOutcomeTiers).mockResolvedValue([]);
  vi.mocked(api.getGraphCheck).mockResolvedValue([]);
});

describe('MissionCanvasPage', () => {
  it('says nothing about problems while the check is still loading', async () => {
    vi.mocked(api.getGraphCheck).mockReturnValue(new Promise(() => {}));
    renderPage();
    await screen.findByRole('heading', { name: 'Problems' });
    expect(screen.queryByText('No problems found.')).toBeNull();
  });

  it('says there are no problems when the check is clean', async () => {
    renderPage();
    expect(await screen.findByText('No problems found.')).toBeInTheDocument();
  });

  it('lists a problem as a link to its option page', async () => {
    vi.mocked(api.getGraphCheck).mockResolvedValue([
      {
        kind: 'missing_tiers',
        message: 'Option "dig" has no route for Failure.',
        node: 5,
        option: 9,
        route: null,
        missing_tiers: ['Failure'],
      } as GraphProblem,
    ]);
    renderPage();
    const link = await screen.findByRole('link', {
      name: 'Option "dig" has no route for Failure.',
    });
    expect(link).toHaveAttribute('href', '/staff/missions/1/nodes/5/options/9');
    expect(await screen.findByText('⚠ gate (entry)')).toBeInTheDocument();
  });

  it('opens the node page when a node is clicked', async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole('button', { name: 'gate (entry)' }));
    expect(await screen.findByTestId('where')).toHaveTextContent('/staff/missions/1/nodes/5');
  });

  it('adds the first node as the entry node on an empty mission', async () => {
    vi.mocked(api.listMissionNodes).mockResolvedValue(page([]) as never);
    vi.mocked(api.getGraphCheck).mockResolvedValue([
      {
        kind: 'no_entry',
        message: 'No entry node',
        node: null,
        option: null,
        route: null,
        missing_tiers: [],
      },
    ] as GraphProblem[]);
    vi.mocked(api.createMissionNode).mockResolvedValue(NODE);
    const user = userEvent.setup();
    renderPage();
    expect(await screen.findByText('No entry node')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Add node' }));
    await user.type(await screen.findByLabelText('Node key'), 'gate');
    const buttons = screen.getAllByRole('button', { name: 'Add node' });
    await user.click(buttons[buttons.length - 1]);
    await waitFor(() =>
      expect(api.createMissionNode).toHaveBeenCalledWith({
        template: 1,
        key: 'gate',
        is_entry: true,
        conflict_mode: 'group_vote',
      })
    );
  });

  it('shows the server message inline when adding a node fails', async () => {
    vi.mocked(api.createMissionNode).mockRejectedValue(new Error('A node with that key exists.'));
    const user = userEvent.setup();
    renderPage();
    await screen.findByText('No problems found.');
    await user.click(screen.getByRole('button', { name: 'Add node' }));
    await user.type(await screen.findByLabelText('Node key'), 'gate');
    const buttons = screen.getAllByRole('button', { name: 'Add node' });
    await user.click(buttons[buttons.length - 1]);
    expect(await screen.findByText('A node with that key exists.')).toBeInTheDocument();
  });
});
