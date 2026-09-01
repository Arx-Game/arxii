import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { WorldBuilderArea, WorldBuilderAreaManager } from '../../types';
import { AreaDocument } from '../AreaDocument';

// AreaDocument's tests cover its wiring (draft restore, which action gets
// which kwargs, the metadata door, delete). `EditAreaDialog` has its own
// coverage from #3269, so a thin mock keeps this file from re-testing it.
vi.mock('../../queries', () => ({
  useAreaManagerQuery: vi.fn(),
  useWorldBuilderAction: vi.fn(),
}));
vi.mock('../../useWorldBuilderActor', () => ({ useWorldBuilderActor: vi.fn(() => 1) }));
vi.mock('../../components/EditAreaDialog', () => ({
  EditAreaDialog: ({ open }: { open: boolean }) =>
    open ? <div data-testid="mock-edit-area-dialog" /> : null,
}));

const { useAreaManagerQuery, useWorldBuilderAction } = await import('../../queries');

function makeArea(overrides: Partial<WorldBuilderArea> = {}): WorldBuilderArea {
  return {
    id: 7,
    name: 'The Lowers',
    slug: null,
    level: 30,
    level_display: 'Ward',
    origin: 'authored',
    parent: 3,
    children_count: 2,
    grid_x: null,
    grid_y: null,
    realm: null,
    climate: null,
    dominant_society: null,
    effective_climate: 'temperate',
    art_url: null,
    description: 'A ward of narrow streets.',
    color: '',
    permit_eligibility: 'open',
    ...overrides,
  };
}

function makeManager(area: WorldBuilderArea): WorldBuilderAreaManager {
  return {
    area,
    catalogs: {
      species: [],
      resonances: [],
      distinctions: [],
      fame_tiers: [],
      realms: [],
      climates: [],
      societies: [],
      permit_options: [],
      feature_kinds: [],
      npc_roles: [],
      blueprints: [],
      size_tiers: [],
      starting_areas: [],
      beginnings: [],
    },
    breadcrumb: [],
    rooms: [],
    resonances: [],
    exits: [],
  };
}

describe('AreaDocument', () => {
  let runMutation: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    runMutation = vi.fn();
    vi.mocked(useWorldBuilderAction).mockReturnValue({ mutate: runMutation } as never);
  });

  it('shows a loading state before the manager payload loads', () => {
    vi.mocked(useAreaManagerQuery).mockReturnValue({ data: undefined } as never);
    renderWithProviders(<AreaDocument areaId={7} onDeleted={vi.fn()} />);
    expect(screen.getByTestId('area-document-loading')).toBeInTheDocument();
  });

  it('starts from the server name/description when no draft exists', () => {
    vi.mocked(useAreaManagerQuery).mockReturnValue({ data: makeManager(makeArea()) } as never);
    renderWithProviders(<AreaDocument areaId={7} onDeleted={vi.fn()} />);
    expect(screen.getByTestId('area-name-input')).toHaveValue('The Lowers');
    expect(screen.getByTestId('area-description-input')).toHaveValue('A ward of narrow streets.');
  });

  it('restores a left-over draft, keyed apart from a same-id ROOM draft', () => {
    // Room 7 and area 7 share the numeric id segment — only the field
    // namespace separates them. The room's draft must NOT leak in.
    window.localStorage.setItem('world-builder-draft:7:name', 'A room named seven');
    window.localStorage.setItem('world-builder-draft:7:area-name', 'The Renamed Lowers');
    vi.mocked(useAreaManagerQuery).mockReturnValue({ data: makeManager(makeArea()) } as never);

    renderWithProviders(<AreaDocument areaId={7} onDeleted={vi.fn()} />);

    expect(screen.getByTestId('area-name-input')).toHaveValue('The Renamed Lowers');
  });

  it('Save dispatches edit_area with the drafted text and clears drafts on success', async () => {
    vi.mocked(useAreaManagerQuery).mockReturnValue({ data: makeManager(makeArea()) } as never);
    renderWithProviders(<AreaDocument areaId={7} onDeleted={vi.fn()} />);

    const nameInput = screen.getByTestId('area-name-input');
    await userEvent.clear(nameInput);
    await userEvent.type(nameInput, 'The Renamed Lowers');
    await userEvent.click(screen.getByTestId('area-save-button'));

    expect(runMutation).toHaveBeenCalledWith(
      {
        key: 'edit_area',
        kwargs: {
          area_id: 7,
          name: 'The Renamed Lowers',
          description: 'A ward of narrow streets.',
        },
      },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );

    const [, callbacks] = runMutation.mock.calls[0];
    callbacks.onSuccess({ success: true, message: 'ok' });
    expect(window.localStorage.getItem('world-builder-draft:7:area-name')).toBeNull();
  });

  it('Save does NOT clear the draft on a business-rule refusal', async () => {
    vi.mocked(useAreaManagerQuery).mockReturnValue({ data: makeManager(makeArea()) } as never);
    renderWithProviders(<AreaDocument areaId={7} onDeleted={vi.fn()} />);
    await userEvent.type(screen.getByTestId('area-name-input'), ' extra');
    await userEvent.click(screen.getByTestId('area-save-button'));

    const [, callbacks] = runMutation.mock.calls[0];
    callbacks.onSuccess({ success: false, message: 'Name the area.' });
    expect(window.localStorage.getItem('world-builder-draft:7:area-name')).not.toBeNull();
  });

  it('the marginalia door opens the reused EditAreaDialog', async () => {
    vi.mocked(useAreaManagerQuery).mockReturnValue({ data: makeManager(makeArea()) } as never);
    renderWithProviders(<AreaDocument areaId={7} onDeleted={vi.fn()} />);

    expect(screen.queryByTestId('mock-edit-area-dialog')).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId('edit-metadata-button'));
    expect(screen.getByTestId('mock-edit-area-dialog')).toBeInTheDocument();
  });

  it('marginalia shows the inherited climate when the area sets none', () => {
    vi.mocked(useAreaManagerQuery).mockReturnValue({ data: makeManager(makeArea()) } as never);
    renderWithProviders(<AreaDocument areaId={7} onDeleted={vi.fn()} />);
    expect(screen.getByText('temperate (inherited)')).toBeInTheDocument();
  });

  it("marginalia shows the area's own climate untagged when set", () => {
    vi.mocked(useAreaManagerQuery).mockReturnValue({
      data: makeManager(makeArea({ climate: 'alpine' })),
    } as never);
    renderWithProviders(<AreaDocument areaId={7} onDeleted={vi.fn()} />);
    expect(screen.getByText('alpine')).toBeInTheDocument();
  });

  it('delete: confirming dispatches staff_remove_area and reports the parent on success', async () => {
    vi.mocked(useAreaManagerQuery).mockReturnValue({ data: makeManager(makeArea()) } as never);
    const onDeleted = vi.fn();

    renderWithProviders(<AreaDocument areaId={7} onDeleted={onDeleted} />);
    await userEvent.click(screen.getByTestId('area-delete-button'));
    await userEvent.click(screen.getByTestId('confirm-area-delete-button'));

    expect(runMutation).toHaveBeenCalledWith(
      { key: 'staff_remove_area', kwargs: { area_id: 7 } },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );

    const [, callbacks] = runMutation.mock.calls[0];
    callbacks.onSuccess({ success: true, message: 'Area removed.' });
    expect(onDeleted).toHaveBeenCalledWith(3);
  });

  it('delete: a root area reports null as its parent', async () => {
    vi.mocked(useAreaManagerQuery).mockReturnValue({
      data: makeManager(makeArea({ parent: null })),
    } as never);
    const onDeleted = vi.fn();

    renderWithProviders(<AreaDocument areaId={7} onDeleted={onDeleted} />);
    await userEvent.click(screen.getByTestId('area-delete-button'));
    await userEvent.click(screen.getByTestId('confirm-area-delete-button'));

    const [, callbacks] = runMutation.mock.calls[0];
    callbacks.onSuccess({ success: true, message: 'Area removed.' });
    expect(onDeleted).toHaveBeenCalledWith(null);
  });

  it('delete: a refusal does not call onDeleted', async () => {
    vi.mocked(useAreaManagerQuery).mockReturnValue({ data: makeManager(makeArea()) } as never);
    const onDeleted = vi.fn();

    renderWithProviders(<AreaDocument areaId={7} onDeleted={onDeleted} />);
    await userEvent.click(screen.getByTestId('area-delete-button'));
    await userEvent.click(screen.getByTestId('confirm-area-delete-button'));

    const [, callbacks] = runMutation.mock.calls[0];
    callbacks.onSuccess({ success: false, message: 'The area still holds rooms.' });
    expect(onDeleted).not.toHaveBeenCalled();
  });
});
