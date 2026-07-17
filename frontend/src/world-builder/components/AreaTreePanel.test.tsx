import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { WorldBuilderArea } from '../types';
import { AreaTreePanel } from './AreaTreePanel';

vi.mock('../queries', () => ({
  useWorldBuilderAreasQuery: vi.fn(),
}));

const { useWorldBuilderAreasQuery } = await import('../queries');

function makeArea(overrides: Partial<WorldBuilderArea> = {}): WorldBuilderArea {
  return {
    id: 1,
    name: 'Arx',
    slug: 'arx',
    level: 40,
    level_display: 'City',
    origin: 'authored',
    parent: null,
    children_count: 0,
    grid_x: null,
    grid_y: null,
    ...overrides,
  };
}

const roots = [makeArea({ id: 1, name: 'Arx', children_count: 1 })];
const children = [makeArea({ id: 2, name: 'Ward of the Lyceum', parent: 1, children_count: 0 })];

function mockAreas() {
  vi.mocked(useWorldBuilderAreasQuery).mockImplementation((params = {}, enabled) => {
    if (params.hasParent === false) {
      return { data: { results: roots, count: roots.length }, isLoading: false } as never;
    }
    if (params.parent === 1 && enabled) {
      return { data: { results: children, count: children.length }, isLoading: false } as never;
    }
    return { data: undefined, isLoading: false } as never;
  });
}

describe('AreaTreePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAreas();
  });

  it('lists root areas', () => {
    renderWithProviders(
      <AreaTreePanel selectedAreaId={null} onSelectArea={vi.fn()} onCreateArea={vi.fn()} />
    );
    expect(screen.getByText('Arx')).toBeInTheDocument();
  });

  it('selects an area on click', async () => {
    const onSelectArea = vi.fn();
    renderWithProviders(
      <AreaTreePanel selectedAreaId={null} onSelectArea={onSelectArea} onCreateArea={vi.fn()} />
    );
    await userEvent.click(screen.getByTestId('area-tree-node'));
    expect(onSelectArea).toHaveBeenCalledWith(1);
  });

  it('expands a node to fetch and show its children', async () => {
    renderWithProviders(
      <AreaTreePanel selectedAreaId={null} onSelectArea={vi.fn()} onCreateArea={vi.fn()} />
    );
    expect(screen.queryByText('Ward of the Lyceum')).not.toBeInTheDocument();

    await userEvent.click(screen.getByTestId('area-tree-expand-1'));

    expect(await screen.findByText('Ward of the Lyceum')).toBeInTheDocument();
  });

  it('requests a new root area via the tree header +', async () => {
    const onCreateArea = vi.fn();
    renderWithProviders(
      <AreaTreePanel selectedAreaId={null} onSelectArea={vi.fn()} onCreateArea={onCreateArea} />
    );
    await userEvent.click(screen.getByTestId('area-tree-new-root'));
    expect(onCreateArea).toHaveBeenCalledWith(null);
  });

  it('requests a new child area via a node`s +', async () => {
    const onCreateArea = vi.fn();
    renderWithProviders(
      <AreaTreePanel selectedAreaId={null} onSelectArea={vi.fn()} onCreateArea={onCreateArea} />
    );
    await userEvent.click(screen.getByTestId('area-tree-new-child-1'));
    expect(onCreateArea).toHaveBeenCalledWith(1);
  });
});
