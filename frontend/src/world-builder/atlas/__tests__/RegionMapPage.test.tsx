import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { RegionMapPips } from '../../types';
import { RegionMapPage } from '../RegionMapPage';

const mutateAsync = vi.fn();

// jsdom has no PointerEvent, so pointer events carry no clientX/clientY without this.
if (typeof window.PointerEvent === 'undefined') {
  class PointerEventPolyfill extends MouseEvent {
    constructor(type: string, params: PointerEventInit = {}) {
      super(type, params);
    }
  }
  // @ts-expect-error jsdom doesn't implement PointerEvent
  window.PointerEvent = PointerEventPolyfill;
}

vi.mock('../../queries', () => ({
  useRegionMapPipsQuery: vi.fn(),
  useRegionMapUpload: vi.fn(() => ({ mutate: vi.fn(), isPending: false })),
  useWorldBuilderAction: vi.fn(() => ({ mutateAsync })),
}));

vi.mock('../../useWorldBuilderActor', () => ({
  useWorldBuilderActor: () => 7,
}));

vi.mock('@/almanach/queries', () => ({
  useRealms: vi.fn(() => ({ data: { results: [{ id: 1, name: 'Luxen' }] } })),
  useLadder: vi.fn(() => ({
    data: {
      rows: [{ title_id: 100, name: 'Salvation', tier: 'county', house_name: 'House Stellaris' }],
      unclaimed_by_tier: {},
    },
    refetch: vi.fn(),
  })),
  useAlmanachMutation: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));

import { useRegionMapPipsQuery } from '../../queries';

const payload: RegionMapPips = {
  region: {
    id: 1,
    name: 'Catenys',
    area: null,
    area_name: '',
    anchor_x: 0,
    anchor_y: 0,
    width_cells: 2,
    height_cells: 2,
    pips_per_cell: 10,
    created_at: '2026-10-12T00:00:00Z',
    latest_upload: {
      id: 1,
      file_name: 'C1.map',
      byte_size: 12,
      generator_version: '1.154.0',
      source_width_px: 1200,
      source_height_px: 1200,
      uploaded_by_name: 'staff',
      uploaded_at: '2026-10-12T00:00:00Z',
      rasterized_at: '2026-10-12T00:00:00Z',
    },
  },
  terrains: ['water', 'plain', 'forest'],
  // a nine-pip island at (1..3, 0..2) in a sea
  pips: Array.from({ length: 5 * 4 }, (_, i): RegionMapPips['pips'][number] => {
    const x = i % 5;
    const y = Math.floor(i / 5);
    const land = x >= 1 && x <= 3 && y <= 2;
    return [x, y, land ? 'plain' : 'water', x === 1 && y === 0];
  }),
  footprints: [
    {
      area_id: 10,
      name: 'Salvation',
      level: 53,
      level_display: 'County',
      parent_id: null,
      realm_id: 1,
      holder_org_id: 4,
      holder_name: 'House Stellaris',
      title_id: 100,
      seat: [1, 0],
      pips: [
        [1, 0],
        [2, 0],
      ],
    },
  ],
};

describe('RegionMapPage', () => {
  beforeEach(() => {
    // jsdom has no 2D context; the page guards for null and draws nothing here.
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    mutateAsync.mockReset();
    mutateAsync.mockResolvedValue({ success: true, message: '', data: { changed: [] } });
    window.localStorage.clear();
    vi.mocked(useRegionMapPipsQuery).mockReturnValue({
      data: payload,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useRegionMapPipsQuery>);
  });

  it('draws the region with its header, legend and the focused footprint', () => {
    renderWithProviders(<RegionMapPage regionId={1} focusAreaId={10} />);
    expect(screen.getByRole('heading', { name: 'Catenys' })).toBeInTheDocument();
    expect(screen.getByText(/2 × 2 cells · 200 miles across · C1.map/)).toBeInTheDocument();
    expect(screen.getByTestId('region-map-canvas')).toHaveAttribute('width', '120');
    expect(screen.getByTestId('region-map-legend')).toHaveTextContent('forest');
    expect(screen.getByRole('heading', { name: 'Salvation' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open in the Almanach' })).toHaveAttribute(
      'href',
      '/staff/almanach/titles/100'
    );
    expect(screen.getByRole('link', { name: 'Download' })).toHaveAttribute(
      'href',
      '/api/world-builder/region-maps/1/file/'
    );
  });

  it('offers the realm ladder in carve mode', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    expect(screen.getByText('Open ground')).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Carve' }));
    await user.selectOptions(screen.getByTestId('carve-realm'), '1');
    await user.selectOptions(screen.getByTestId('carve-domain'), '100');
    expect(screen.getByTestId('carve-domain')).toHaveValue('100');
    await user.click(screen.getByRole('button', { name: 'Create domain' }));
    expect(screen.getByTestId('plant-form')).toHaveTextContent('under Salvation');
  });

  it('offers brush, fill and loop in carve mode, brush first, with nothing to undo', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    expect(screen.queryByRole('button', { name: 'Fill' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Carve' }));
    expect(screen.getByRole('button', { name: 'Brush' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Fill' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Loop' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('brush-width')).toHaveValue('1');
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Redo' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Clear' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Fill' }));
    expect(screen.queryByTestId('brush-width')).not.toBeInTheDocument();
  });

  it('paints a brush square of the chosen width into the domain', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    await user.click(screen.getByRole('button', { name: 'Carve' }));
    await user.selectOptions(screen.getByTestId('carve-realm'), '1');
    await user.selectOptions(screen.getByTestId('carve-domain'), '100');
    await user.selectOptions(screen.getByTestId('brush-width'), '3');
    const viewport = screen.getByTestId('region-map-viewport');
    // zoom 1, no pan, a zero rect: a pip is 6px, so (33, 33) is pip (5, 5)
    fireEvent.pointerDown(viewport, { clientX: 33, clientY: 33, button: 0 });
    fireEvent.pointerUp(window, { clientX: 33, clientY: 33 });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const { key, kwargs } = mutateAsync.mock.calls[0][0];
    expect(key).toBe('atlas_carve_footprint');
    expect(kwargs.title_id).toBe(100);
    const add = kwargs.add as [number, number][];
    expect(add).toHaveLength(9);
    expect(add).toContainEqual([4, 4]);
    expect(add).toContainEqual([6, 6]);
  });

  async function enterCarve(user: ReturnType<typeof userEvent.setup>) {
    await user.click(screen.getByRole('button', { name: 'Carve' }));
    await user.selectOptions(screen.getByTestId('carve-realm'), '1');
    await user.selectOptions(screen.getByTestId('carve-domain'), '100');
  }
  function click(x: number, y: number) {
    const viewport = screen.getByTestId('region-map-viewport');
    fireEvent.pointerDown(viewport, { clientX: x, clientY: y, button: 0 });
    fireEvent.pointerUp(window, { clientX: x, clientY: y });
  }
  const lastCall = () => mutateAsync.mock.calls.at(-1)?.[0];
  const ISLAND = ['1,0', '1,1', '1,2', '2,0', '2,1', '2,2', '3,0', '3,1', '3,2'];

  it('fills the landmass under a click and nothing from water', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    await enterCarve(user);
    await user.click(screen.getByRole('button', { name: 'Fill' }));
    click(3, 3); // pip (0, 0): water
    click(9, 9); // pip (1, 1): the island
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const { key, kwargs } = lastCall();
    expect(key).toBe('atlas_carve_footprint');
    const add = (kwargs.add as [number, number][]).map(([x, y]) => `${x},${y}`).sort();
    expect(add).toEqual(ISLAND);
  });

  it('fills the land inside a drawn loop', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    await enterCarve(user);
    await user.click(screen.getByRole('button', { name: 'Loop' }));
    const viewport = screen.getByTestId('region-map-viewport');
    // the island's four corners, sampled far apart: the loop must join them and fill (2, 1)
    fireEvent.pointerDown(viewport, { clientX: 9, clientY: 3, button: 0 });
    fireEvent.pointerMove(window, { clientX: 21, clientY: 3 });
    fireEvent.pointerMove(window, { clientX: 21, clientY: 15 });
    fireEvent.pointerMove(window, { clientX: 9, clientY: 15 });
    fireEvent.pointerUp(window, { clientX: 9, clientY: 15 });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    const add = (lastCall().kwargs.add as [number, number][]).map(([x, y]) => `${x},${y}`).sort();
    expect(add).toEqual(ISLAND);
  });

  it('undoes a gesture by restoring prior holders, redoes with the new ones, and keeps a refused undo', async () => {
    const user = userEvent.setup();
    mutateAsync.mockResolvedValue({
      success: true,
      message: '',
      data: { changed: [[1, 0, null, 10]] },
    });
    renderWithProviders(<RegionMapPage regionId={1} />);
    await enterCarve(user);
    click(9, 3);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled());
    mutateAsync.mockResolvedValue({ success: true, message: '', data: null });
    await user.click(screen.getByRole('button', { name: 'Undo' }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
    expect(lastCall()).toEqual({
      key: 'atlas_restore_footprint',
      kwargs: { pips: [[1, 0, null]] },
    });
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Redo' })).toBeEnabled();
    await user.click(screen.getByRole('button', { name: 'Redo' }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(3));
    expect(lastCall()).toEqual({
      key: 'atlas_restore_footprint',
      kwargs: { pips: [[1, 0, 10]] },
    });
    // the server refuses the next undo: the entry stays
    mutateAsync.mockResolvedValue({ success: false, message: 'No.', data: null });
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(4));
    expect(lastCall().key).toBe('atlas_restore_footprint');
    await waitFor(() => expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled());
  });

  it('ignores a second undo while the first restore is in flight', async () => {
    const user = userEvent.setup();
    mutateAsync.mockResolvedValue({
      success: true,
      message: '',
      data: { changed: [[1, 0, null, 10]] },
    });
    renderWithProviders(<RegionMapPage regionId={1} />);
    await enterCarve(user);
    click(9, 3);
    click(15, 3);
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
    let settle: (value: unknown) => void = () => {};
    mutateAsync.mockImplementation(() => new Promise((resolve) => (settle = resolve)));
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true, shiftKey: true });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(3));
    expect(lastCall().key).toBe('atlas_restore_footprint');
    settle({ success: true, message: '', data: null });
    // the first undo settles with one entry left to undo, nothing double-counted
    await waitFor(() => expect(screen.getByRole('button', { name: 'Redo' })).toBeEnabled());
    expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled();
    expect(mutateAsync).toHaveBeenCalledTimes(3);
  });

  it('clears the domain behind a confirmation', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    await enterCarve(user);
    await user.click(screen.getByRole('button', { name: 'Clear' }));
    const dialog = await screen.findByRole('alertdialog');
    expect(dialog).toHaveTextContent('Salvation');
    await user.click(within(dialog).getByRole('button', { name: 'Clear' }));
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(lastCall()).toEqual({ key: 'atlas_clear_footprint', kwargs: { title_id: 100 } });
  });

  it('shows the loading and error states', () => {
    vi.mocked(useRegionMapPipsQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useRegionMapPipsQuery>);
    const { unmount } = renderWithProviders(<RegionMapPage regionId={1} />);
    expect(screen.getByTestId('region-map-loading')).toBeInTheDocument();
    unmount();
    vi.mocked(useRegionMapPipsQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useRegionMapPipsQuery>);
    renderWithProviders(<RegionMapPage regionId={1} />);
    expect(screen.getByTestId('region-map-error')).toBeInTheDocument();
  });
});
