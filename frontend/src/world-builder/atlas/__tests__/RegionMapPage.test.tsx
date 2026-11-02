import { fireEvent, screen, waitFor } from '@testing-library/react';
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
  pips: [
    [0, 0, 'water', false],
    [1, 0, 'plain', true],
  ],
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
