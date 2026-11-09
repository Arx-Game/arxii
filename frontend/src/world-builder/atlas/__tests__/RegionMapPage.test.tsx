import { StrictMode, useState } from 'react';

import { act, fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { RegionMapPips } from '../../types';
import { RegionMapPage } from '../RegionMapPage';

const mutateAsync = vi.fn();
const toastError = vi.fn();

vi.mock('sonner', () => ({
  toast: { error: (...args: unknown[]) => toastError(...args), success: vi.fn() },
}));

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
      rows: [
        {
          title_id: 100,
          name: 'Salvation',
          tier: 'county',
          house_name: 'House Stellaris',
          parent_title_id: null,
          state: 'Held',
        },
        {
          title_id: 200,
          name: 'Kingdom of Luxen',
          tier: 'kingdom',
          house_name: '',
          parent_title_id: null,
          state: 'Titular',
        },
        {
          title_id: 300,
          name: 'New Crown',
          tier: 'kingdom',
          house_name: '',
          parent_title_id: null,
          state: 'Unclaimed',
        },
        {
          title_id: 400,
          name: 'Kingdom of Arvum',
          tier: 'kingdom',
          house_name: '',
          parent_title_id: null,
          state: 'Potential',
        },
      ],
      unclaimed_by_tier: {},
    },
    refetch: vi.fn(),
  })),
  useAlmanachMutation: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false })),
}));

import { useLadder } from '@/almanach/queries';
import { useRegionMapPipsQuery } from '../../queries';

const realLadder = vi.mocked(useLadder).getMockImplementation()!;

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
      charters: [200],
    },
  ],
  landless_titles: [
    {
      title_id: 200,
      name: 'Kingdom of Luxen',
      tier: 'kingdom',
      station: 'titular',
      realm_id: 1,
      fief_ids: [100],
    },
    {
      title_id: 300,
      name: 'New Crown',
      tier: 'kingdom',
      station: 'seated',
      realm_id: 1,
      fief_ids: [],
    },
  ],
};

/** The county's seat barony on pip (2, 0), only for the tests that drag it (#4988). */
const SEAT_BARONY: RegionMapPips['footprints'][number] = {
  area_id: 11,
  name: 'Salvation Seat',
  level: 40,
  level_display: 'Barony',
  parent_id: 10,
  realm_id: 1,
  holder_org_id: 4,
  holder_name: 'House Stellaris',
  title_id: 101,
  seat: [2, 0],
  pips: [[2, 0]],
  charters: [],
};

describe('RegionMapPage', () => {
  beforeEach(() => {
    // jsdom has no 2D context; the page guards for null and draws nothing here.
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null);
    mutateAsync.mockReset();
    toastError.mockReset();
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

  it('offers the four views on the panel, All by default, and remembers the pick (#5030)', async () => {
    const user = userEvent.setup();
    const { unmount } = renderWithProviders(<RegionMapPage regionId={1} focusAreaId={10} />);
    const picker = screen.getByRole('group', { name: 'view' });
    expect(
      within(picker)
        .getAllByRole('button')
        .map((b) => b.textContent)
    ).toEqual(['Geography', 'Domain', 'Domain-Vassal', 'All']);
    expect(within(picker).getByRole('button', { name: 'All' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.getByTestId('region-map-viewport')).toHaveAttribute('data-map-view', 'all');
    expect(screen.getByTestId('map-view-anchor')).toHaveTextContent('Salvation');
    await user.click(within(picker).getByRole('button', { name: 'Geography' }));
    expect(screen.getByTestId('region-map-viewport')).toHaveAttribute('data-map-view', 'geography');
    unmount();
    renderWithProviders(<RegionMapPage regionId={1} />);
    expect(screen.getByTestId('region-map-viewport')).toHaveAttribute('data-map-view', 'geography');
    expect(screen.getByTestId('map-view-anchor')).toHaveTextContent('no domain selected');
  });

  it('Carve mode starts on Domain-Vassal, keeps a change, and Select gets its own view back (#5030)', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} focusAreaId={10} />);
    const viewport = screen.getByTestId('region-map-viewport');
    await user.click(screen.getByRole('button', { name: 'Carve' }));
    expect(viewport).toHaveAttribute('data-map-view', 'domain-vassal');
    const picker = screen.getByRole('group', { name: 'view' });
    await user.click(within(picker).getByRole('button', { name: 'Geography' }));
    expect(viewport).toHaveAttribute('data-map-view', 'geography');
    expect(viewport).toHaveAttribute('data-visible', '0');
    await user.selectOptions(screen.getByTestId('carve-realm'), '1');
    await user.selectOptions(screen.getByTestId('carve-domain'), '100');
    expect(viewport).toHaveAttribute('data-map-view', 'geography');
    // the domain being carved is drawn even in Geography
    expect(viewport).toHaveAttribute('data-visible', '1');
    expect(screen.getByTestId('map-view-anchor')).toHaveTextContent('Salvation');
    await user.click(screen.getByRole('button', { name: 'Select' }));
    expect(viewport).toHaveAttribute('data-map-view', 'all');
    await user.click(screen.getByRole('button', { name: 'Carve' }));
    expect(viewport).toHaveAttribute('data-map-view', 'domain-vassal');
  });

  it('zooms past the lattice range on the map (#5009)', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    const viewport = screen.getByTestId('region-map-viewport');
    const plus = screen.getByRole('button', { name: '+' });
    for (let i = 0; i < 12; i += 1) await user.click(plus);
    expect(Number(viewport.getAttribute('data-zoom'))).toBeGreaterThan(1.5);
    const minus = screen.getByRole('button', { name: '−' });
    for (let i = 0; i < 30; i += 1) await user.click(minus);
    expect(Number(viewport.getAttribute('data-zoom'))).toBeLessThan(0.25);
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

  it('opens the Almanach in its own tab so the map stays put (#5011)', () => {
    renderWithProviders(<RegionMapPage regionId={1} focusAreaId={10} />);
    const link = screen.getByRole('link', { name: 'Open in the Almanach' });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener');
  });

  it('points the side panel at the domain being carved (#5011)', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} focusAreaId={10} />);
    await user.click(screen.getByRole('button', { name: 'Carve' }));
    await user.selectOptions(screen.getByTestId('carve-realm'), '1');
    await user.selectOptions(screen.getByTestId('carve-domain'), '200');
    expect(screen.getByRole('heading', { name: 'Kingdom of Luxen' })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open in the Almanach' })).toHaveAttribute(
      'href',
      '/staff/almanach/titles/200'
    );
  });

  it('offers brush, fill and loop in carve mode, brush first, with nothing to undo', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    expect(screen.queryByRole('button', { name: 'Fill' })).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Carve' }));
    await user.selectOptions(screen.getByTestId('carve-realm'), '1');
    await user.selectOptions(screen.getByTestId('carve-domain'), '100');
    expect(screen.getByRole('button', { name: 'Brush' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Fill' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('button', { name: 'Loop' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('brush-width')).toHaveValue('1');
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Redo' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Clear' })).toBeEnabled();
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

  it('ignores undo while a carve is still committing, then undoes it', async () => {
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
    let settle: (value: unknown) => void = () => {};
    mutateAsync.mockImplementation(() => new Promise((resolve) => (settle = resolve)));
    click(15, 3); // this carve stays in flight
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mutateAsync).toHaveBeenCalledTimes(2);
    settle({ success: true, message: '', data: { changed: [[2, 0, null, 10]] } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled());
    mutateAsync.mockResolvedValue({ success: true, message: '', data: null });
    fireEvent.keyDown(window, { key: 'z', ctrlKey: true });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(3));
    expect(lastCall()).toEqual({
      key: 'atlas_restore_footprint',
      kwargs: { pips: [[2, 0, null]] },
    });
  });

  it('swallows a failed carve request and leaves nothing to undo', async () => {
    const user = userEvent.setup();
    mutateAsync.mockRejectedValue(new Error('The action failed.'));
    renderWithProviders(<RegionMapPage regionId={1} />);
    await enterCarve(user);
    click(9, 3);
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('button', { name: 'Undo' })).toBeDisabled();
    expect(screen.getByTestId('region-map-page')).toBeInTheDocument();
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

  it('refuses a carve gesture until a domain is picked', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    await user.click(screen.getByRole('button', { name: 'Carve' }));
    for (const name of ['Brush', 'Fill', 'Loop']) {
      expect(screen.getByRole('button', { name })).toBeDisabled();
    }
    const viewport = screen.getByTestId('region-map-viewport');
    fireEvent.pointerDown(viewport, { clientX: 9, clientY: 3, button: 0 });
    fireEvent.pointerUp(window, { clientX: 9, clientY: 3 });
    expect(toastError).toHaveBeenCalledWith('Pick a domain to carve.');
    expect(toastError).toHaveBeenCalledTimes(1);
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mutateAsync).not.toHaveBeenCalled();
    await user.selectOptions(screen.getByTestId('carve-realm'), '1');
    await user.selectOptions(screen.getByTestId('carve-domain'), '100');
    for (const name of ['Brush', 'Fill', 'Loop']) {
      expect(screen.getByRole('button', { name })).toBeEnabled();
    }
  });

  it('selects a landless title in Select mode and draws its Historical Charter as a ghost', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    await user.selectOptions(screen.getByTestId('select-realm'), '1');
    await user.selectOptions(screen.getByTestId('select-domain'), '200');
    const panel = screen.getByTestId('region-map-panel');
    expect(within(panel).getByRole('heading', { name: 'Kingdom of Luxen' })).toBeInTheDocument();
    expect(within(panel).getByText('Titular')).toBeInTheDocument();
    expect(within(panel).getByText(/holds nothing/)).toBeInTheDocument();
    const toggle = within(panel).getByRole('button', { name: 'Historical Charter' });
    expect(toggle).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByTestId('region-map-viewport')).toHaveAttribute('data-ghost-pips', '0');
    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('region-map-viewport')).toHaveAttribute('data-ghost-pips', '2');
    expect(within(panel).getByText('Salvation')).toBeInTheDocument();
    expect(mutateAsync).not.toHaveBeenCalled();
  });

  it('names no station for a seated crown that only lacks land', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    await user.selectOptions(screen.getByTestId('select-realm'), '1');
    await user.selectOptions(screen.getByTestId('select-domain'), '300');
    const panel = screen.getByTestId('region-map-panel');
    expect(within(panel).getByRole('heading', { name: 'New Crown' })).toBeInTheDocument();
    expect(within(panel).queryByText('Titular')).toBeNull();
    expect(within(panel).queryByText('Potential')).toBeNull();
    expect(within(panel).getByText(/holds nothing/)).toBeInTheDocument();
  });

  it('opens a panel for a ladder rung the map payload does not carry', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    await user.selectOptions(screen.getByTestId('select-realm'), '1');
    await user.selectOptions(screen.getByTestId('select-domain'), '400');
    const panel = screen.getByTestId('region-map-panel');
    expect(within(panel).getByRole('heading', { name: 'Kingdom of Arvum' })).toBeInTheDocument();
    expect(within(panel).getByText('Potential')).toBeInTheDocument();
    expect(within(panel).getByText(/holds nothing/)).toBeInTheDocument();
    expect(within(panel).getByRole('link', { name: 'Open in the Almanach' })).toHaveAttribute(
      'href',
      '/staff/almanach/titles/400'
    );
  });

  it('keeps the door focus under StrictMode, which runs the initializer twice', async () => {
    window.sessionStorage.setItem('world-builder-atlas:focus-title', '200');
    renderWithProviders(
      <StrictMode>
        <RegionMapPage regionId={1} />
      </StrictMode>
    );
    const panel = screen.getByTestId('region-map-panel');
    expect(within(panel).getByRole('heading', { name: 'Kingdom of Luxen' })).toBeInTheDocument();
    await waitFor(() =>
      expect(window.sessionStorage.getItem('world-builder-atlas:focus-title')).toBeNull()
    );
  });

  it('takes the focus a title page left and fills both pickers from it', async () => {
    window.sessionStorage.setItem('world-builder-atlas:focus-title', '200');
    renderWithProviders(<RegionMapPage regionId={1} />);
    const panel = screen.getByTestId('region-map-panel');
    expect(within(panel).getByRole('heading', { name: 'Kingdom of Luxen' })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('select-realm')).toHaveValue('1'));
    expect(screen.getByTestId('select-domain')).toHaveValue('200');
    expect(screen.getByTestId('select-domain')).toBeEnabled();
    // read once: a reload keeps the user's own selection, not the door's
    expect(window.sessionStorage.getItem('world-builder-atlas:focus-title')).toBeNull();
  });

  it('Adjust sends take_from_siblings with the carve and only while pressed', async () => {
    const user = userEvent.setup();
    renderWithProviders(<RegionMapPage regionId={1} />);
    await enterCarve(user);
    const adjust = screen.getByTestId('carve-adjust');
    expect(adjust).toHaveAttribute('aria-pressed', 'false');
    await user.click(adjust);
    expect(adjust).toHaveAttribute('aria-pressed', 'true');
    click(33, 33);
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(lastCall()?.kwargs.take_from_siblings).toBe(true);
    await user.click(adjust);
    click(39, 39);
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(2));
    expect(lastCall()?.kwargs).not.toHaveProperty('take_from_siblings');
  });

  it('dragging a barony seat dispatches atlas_move_seat with the drop pip and no carve', async () => {
    const user = userEvent.setup();
    vi.mocked(useRegionMapPipsQuery).mockReturnValue({
      data: { ...payload, footprints: [...payload.footprints, SEAT_BARONY] },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useRegionMapPipsQuery>);
    mutateAsync.mockResolvedValue({
      success: true,
      data: {
        changed: [
          [2, 0, 11, 10],
          [3, 0, 10, 11],
        ],
      },
    });
    renderWithProviders(<RegionMapPage regionId={1} />);
    await enterCarve(user);
    const viewport = screen.getByTestId('region-map-viewport');
    // pip (2, 0) is the barony's seat: 6px a pip, so client (15, 3)
    fireEvent.pointerDown(viewport, { clientX: 15, clientY: 3, button: 0 });
    fireEvent.pointerMove(window, { clientX: 21, clientY: 3 });
    fireEvent.pointerUp(window, { clientX: 21, clientY: 3 });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    expect(lastCall()).toEqual({ key: 'atlas_move_seat', kwargs: { area_id: 11, pip: [3, 0] } });
    // a drop on its own pip sends nothing
    fireEvent.pointerDown(viewport, { clientX: 15, clientY: 3, button: 0 });
    fireEvent.pointerUp(window, { clientX: 15, clientY: 3 });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mutateAsync).toHaveBeenCalledTimes(1);
  });

  it('a cancelled seat press moves nothing, and a barony with no title can still be undone', async () => {
    const user = userEvent.setup();
    vi.mocked(useRegionMapPipsQuery).mockReturnValue({
      data: {
        ...payload,
        footprints: [...payload.footprints, { ...SEAT_BARONY, title_id: null }],
      },
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useRegionMapPipsQuery>);
    mutateAsync.mockResolvedValue({
      success: true,
      data: {
        changed: [
          [2, 0, 11, 10],
          [3, 0, 10, 11],
        ],
      },
    });
    renderWithProviders(<RegionMapPage regionId={1} />);
    await enterCarve(user);
    const viewport = screen.getByTestId('region-map-viewport');
    fireEvent.pointerDown(viewport, { clientX: 15, clientY: 3, button: 0 });
    fireEvent.pointerCancel(window);
    fireEvent.pointerUp(window, { clientX: 21, clientY: 3 });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(mutateAsync).not.toHaveBeenCalled();
    fireEvent.pointerDown(viewport, { clientX: 15, clientY: 3, button: 0 });
    fireEvent.pointerUp(window, { clientX: 21, clientY: 3 });
    await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Undo' })).toBeEnabled());
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

  describe('its own tab and the wheel (#4993)', () => {
    it('offers a maximize link to the map tab, carrying the selected footprint', () => {
      renderWithProviders(<RegionMapPage regionId={1} focusAreaId={10} />);
      const link = screen.getByTestId('region-map-maximize');
      expect(link).toHaveAttribute('href', '/staff/world-builder/map/1?focus=10');
      expect(link).toHaveAttribute('target', '_blank');
      expect(link).toHaveAttribute('rel', 'noopener');
      expect(link).toHaveAccessibleName('Open the map in its own tab');
    });

    it('leaves the footprint off the link when nothing is selected', () => {
      renderWithProviders(<RegionMapPage regionId={1} />);
      expect(screen.getByTestId('region-map-maximize')).toHaveAttribute(
        'href',
        '/staff/world-builder/map/1'
      );
    });

    it('has no maximize link once it is already in its own tab', () => {
      renderWithProviders(<RegionMapPage regionId={1} standalone />);
      expect(screen.queryByTestId('region-map-maximize')).not.toBeInTheDocument();
    });

    it('zooms the map on Ctrl+scroll and stops the browser zooming the page', () => {
      renderWithProviders(<RegionMapPage regionId={1} />);
      const viewport = screen.getByTestId('region-map-viewport');
      const before = viewport.dataset.zoom;
      // fireEvent returns false when the handler called preventDefault
      expect(fireEvent.wheel(viewport, { deltaY: -500, ctrlKey: true })).toBe(false);
      expect(viewport.dataset.zoom).not.toBe(before);
    });

    it('moves the map on plain scroll, leaving its zoom and the page alone', () => {
      renderWithProviders(<RegionMapPage regionId={1} />);
      const viewport = screen.getByTestId('region-map-viewport');
      const canvas = screen.getByTestId('region-map-canvas');
      const zoom = viewport.dataset.zoom;
      const before = canvas.style.transform;
      expect(fireEvent.wheel(viewport, { deltaY: 120 })).toBe(false);
      expect(viewport.dataset.zoom).toBe(zoom);
      expect(canvas.style.transform).not.toBe(before);
      expect(canvas.style.transform).toContain('-120px');
    });

    it('still zooms when the map loads after the page mounts', () => {
      vi.mocked(useRegionMapPipsQuery).mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      } as unknown as ReturnType<typeof useRegionMapPipsQuery>);
      let rerender = () => {};
      function Harness() {
        const [, bump] = useState(0);
        rerender = () => bump((n) => n + 1);
        return <RegionMapPage regionId={1} />;
      }
      renderWithProviders(<Harness />);
      expect(screen.queryByTestId('region-map-viewport')).not.toBeInTheDocument();

      vi.mocked(useRegionMapPipsQuery).mockReturnValue({
        data: payload,
        isLoading: false,
        isError: false,
      } as unknown as ReturnType<typeof useRegionMapPipsQuery>);
      act(() => rerender());
      const viewport = screen.getByTestId('region-map-viewport');
      const before = viewport.dataset.zoom;
      expect(fireEvent.wheel(viewport, { deltaY: -500, ctrlKey: true })).toBe(false);
      expect(viewport.dataset.zoom).not.toBe(before);
    });
  });

  describe('collapsing the layout (#4993)', () => {
    it('folds the side panel to a rail, keeps the selection, and remembers it', async () => {
      const user = userEvent.setup();
      const { unmount } = renderWithProviders(<RegionMapPage regionId={1} focusAreaId={10} />);
      const toggle = screen.getByTestId('panel-toggle');
      expect(toggle).toHaveAttribute('aria-expanded', 'true');
      expect(screen.getByRole('heading', { name: 'Salvation' })).toBeInTheDocument();

      await user.click(toggle);
      expect(screen.getByTestId('panel-toggle')).toHaveAttribute('aria-expanded', 'false');
      expect(screen.queryByRole('heading', { name: 'Salvation' })).not.toBeInTheDocument();
      expect(screen.queryByTestId('region-map-legend')).not.toBeInTheDocument();
      unmount();

      renderWithProviders(<RegionMapPage regionId={1} focusAreaId={10} />);
      expect(screen.getByTestId('panel-toggle')).toHaveAttribute('aria-expanded', 'false');
      await user.click(screen.getByTestId('panel-toggle'));
      expect(screen.getByRole('heading', { name: 'Salvation' })).toBeInTheDocument();
    });

    it('folds the carve pickers to the domain name and leaves the tools usable', async () => {
      const user = userEvent.setup();
      renderWithProviders(<RegionMapPage regionId={1} />);
      await user.click(screen.getByRole('button', { name: 'Carve' }));
      await user.selectOptions(screen.getByTestId('carve-realm'), '1');
      await user.selectOptions(screen.getByTestId('carve-domain'), '100');
      await user.click(screen.getByRole('button', { name: 'Create domain' }));
      expect(screen.getByTestId('plant-form')).toBeInTheDocument();

      await user.click(screen.getByTestId('pickers-toggle'));
      expect(screen.queryByTestId('carve-realm')).not.toBeInTheDocument();
      expect(screen.queryByTestId('carve-domain')).not.toBeInTheDocument();
      expect(screen.queryByRole('button', { name: 'Create domain' })).not.toBeInTheDocument();
      expect(screen.queryByTestId('plant-form')).not.toBeInTheDocument();
      expect(screen.getByTestId('picked-domain')).toHaveTextContent('Salvation');
      expect(screen.getByRole('button', { name: 'Brush' })).toBeEnabled();

      fireEvent.pointerDown(screen.getByTestId('region-map-viewport'), {
        clientX: 15,
        clientY: 3,
        button: 0,
      });
      fireEvent.pointerUp(window, { clientX: 15, clientY: 3 });
      await waitFor(() => expect(mutateAsync).toHaveBeenCalledTimes(1));
      expect(mutateAsync.mock.calls[0][0].kwargs.title_id).toBe(100);

      await user.click(screen.getByTestId('pickers-toggle'));
      expect(screen.getByTestId('carve-domain')).toHaveValue('100');
    });

    it('says unnamed and the tier when the folded domain has no name', async () => {
      const user = userEvent.setup();
      vi.mocked(useLadder).mockImplementation(
        () =>
          ({
            data: {
              rows: [
                {
                  title_id: 500,
                  name: '',
                  tier: 'county',
                  house_name: '',
                  parent_title_id: null,
                  state: 'Unclaimed',
                },
              ],
              unclaimed_by_tier: {},
            },
            refetch: vi.fn(),
          }) as unknown as ReturnType<typeof useLadder>
      );
      renderWithProviders(<RegionMapPage regionId={1} />);
      await user.click(screen.getByRole('button', { name: 'Carve' }));
      await user.selectOptions(screen.getByTestId('carve-realm'), '1');
      await user.selectOptions(screen.getByTestId('carve-domain'), '500');
      await user.click(screen.getByTestId('pickers-toggle'));
      expect(screen.getByTestId('picked-domain')).toHaveTextContent('unnamed county');
      vi.mocked(useLadder).mockImplementation(realLadder);
    });

    it('folds the select pickers too, showing what is selected', async () => {
      const user = userEvent.setup();
      renderWithProviders(<RegionMapPage regionId={1} focusAreaId={10} />);
      await user.click(screen.getByTestId('pickers-toggle'));
      expect(screen.queryByTestId('select-realm')).not.toBeInTheDocument();
      expect(screen.getByTestId('picked-domain')).toHaveTextContent('Salvation');
    });

    it('survives the stored setting being unreadable', () => {
      window.localStorage.setItem('world-builder-atlas:anon:map-layout', '{not json');
      renderWithProviders(<RegionMapPage regionId={1} />);
      expect(screen.getByTestId('panel-toggle')).toHaveAttribute('aria-expanded', 'true');
    });
  });
});
