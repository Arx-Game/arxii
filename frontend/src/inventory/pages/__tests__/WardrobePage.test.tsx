/**
 * WardrobePage page-level tests.
 *
 * Stubs every data hook and the websocket layer so we can assert how the
 * page composes its child components and dispatches actions. We don't try
 * to retest the children themselves — those have their own tests.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { startSession } from '@/store/gameSlice';
import { emitActionResult } from '@/hooks/actionResultBus';
import type { EquippedItem, ItemInstance, Outfit } from '../../types';
import type { MyRosterEntry } from '@/roster/types';

// jsdom doesn't implement scrollIntoView, but cmdk inside EditOutfitDialog calls it.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}

vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(),
}));

vi.mock('../../hooks/useOutfits', () => ({
  useOutfits: vi.fn(),
  useCreateOutfit: vi.fn(),
  useUpdateOutfit: vi.fn(),
  useDeleteOutfit: vi.fn(),
  useCreateOutfitSlot: vi.fn(),
  useDeleteOutfitSlot: vi.fn(),
  outfitKeys: {
    all: ['outfits'],
    list: (id: number) => ['outfits', id],
    detail: (id: number) => ['outfit', id],
    slots: (id: number) => ['outfit-slots', id],
  },
}));

vi.mock('../../hooks/useInventory', () => ({
  useInventory: vi.fn(),
  useEquippedItems: vi.fn(),
  inventoryKeys: {
    all: ['inventory'],
    inventory: (id: number) => ['inventory', id],
    equipped: (id: number) => ['equipped', id],
  },
}));

const executeActionMock = vi.fn();
vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({
    connect: vi.fn(),
    disconnectAll: vi.fn(),
    send: vi.fn(),
    executeAction: executeActionMock,
  }),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as rosterQueries from '@/roster/queries';
import * as outfitsHooks from '../../hooks/useOutfits';
import * as inventoryHooks from '../../hooks/useInventory';
import { toast } from 'sonner';
import { WardrobePage } from '../WardrobePage';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const ACTIVE_NAME = 'Aria';
const CHARACTER_ID = 42;

function makeRosterEntry(overrides: Partial<MyRosterEntry> = {}): MyRosterEntry {
  return {
    id: 1,
    name: ACTIVE_NAME,
    character_id: CHARACTER_ID,
    profile_picture_url: null,
    primary_persona_id: null,
    ...overrides,
  };
}

function makeItem(id: number, name: string): ItemInstance {
  return {
    id,
    template: {
      id: id + 100,
      name,
      weight: '1.00',
      size: 1,
      value: 0,
      is_container: false,
      is_stackable: false,
      is_consumable: false,
      is_craftable: true,
      image_url: '',
    },
    quality_tier: {
      id: 1,
      name: 'Fine',
      color_hex: '#4ade80',
      numeric_min: 0,
      numeric_max: 100,
      stat_multiplier: '1.00',
      sort_order: 1,
    },
    display_name: name,
    display_description: '',
    display_image_url: null,
    contained_in: 1,
    quantity: 1,
    charges: 0,
    is_open: false,
  };
}

function makeOutfit(id: number, name: string): Outfit {
  return {
    id,
    name,
    description: '',
    character_sheet: CHARACTER_ID,
    wardrobe: 99,
    slots: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function makeEquippedRow(itemId: number, id = itemId * 10): EquippedItem {
  return {
    id,
    character: CHARACTER_ID,
    item_instance: itemId,
    body_region: 'torso',
    equipment_layer: 'base',
    body_region_display: 'Torso',
    equipment_layer_display: 'Base',
  };
}

// Construct a stub return shape that satisfies the mutation hook contract
// without dragging in the full @tanstack/react-query types.
function stubMutation() {
  return {
    mutate: vi.fn(),
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    status: 'idle',
    reset: vi.fn(),
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
  } as unknown as ReturnType<typeof outfitsHooks.useCreateOutfit>;
}

function stubQuery<T>(data: T) {
  return {
    data,
    isLoading: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof outfitsHooks.useOutfits>;
}

interface SetupOpts {
  outfits?: Outfit[];
  inventory?: ItemInstance[];
  equipped?: EquippedItem[];
  active?: string | null;
}

function setupHooks({
  outfits = [],
  inventory = [],
  equipped = [],
  active = ACTIVE_NAME,
}: SetupOpts = {}) {
  vi.mocked(rosterQueries.useMyRosterEntriesQuery).mockReturnValue(
    stubQuery([makeRosterEntry()]) as unknown as ReturnType<
      typeof rosterQueries.useMyRosterEntriesQuery
    >
  );
  vi.mocked(outfitsHooks.useOutfits).mockReturnValue(stubQuery(outfits));
  vi.mocked(inventoryHooks.useInventory).mockReturnValue(
    stubQuery(inventory) as unknown as ReturnType<typeof inventoryHooks.useInventory>
  );
  vi.mocked(inventoryHooks.useEquippedItems).mockReturnValue(
    stubQuery(equipped) as unknown as ReturnType<typeof inventoryHooks.useEquippedItems>
  );
  vi.mocked(outfitsHooks.useCreateOutfit).mockReturnValue(stubMutation());
  vi.mocked(outfitsHooks.useUpdateOutfit).mockReturnValue(
    stubMutation() as unknown as ReturnType<typeof outfitsHooks.useUpdateOutfit>
  );
  vi.mocked(outfitsHooks.useDeleteOutfit).mockReturnValue(
    stubMutation() as unknown as ReturnType<typeof outfitsHooks.useDeleteOutfit>
  );
  vi.mocked(outfitsHooks.useCreateOutfitSlot).mockReturnValue(
    stubMutation() as unknown as ReturnType<typeof outfitsHooks.useCreateOutfitSlot>
  );
  vi.mocked(outfitsHooks.useDeleteOutfitSlot).mockReturnValue(
    stubMutation() as unknown as ReturnType<typeof outfitsHooks.useDeleteOutfitSlot>
  );

  // Seed the active session in Redux so useAppSelector returns a name.
  if (active) {
    store.dispatch(startSession(active));
  }
}

describe('WardrobePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset store between tests so an empty-active scenario is reachable.
    store.dispatch({ type: 'game/resetGame' });
  });

  it('renders the no-active-character state when nothing is active', () => {
    setupHooks({ active: null });
    renderWithProviders(<WardrobePage />);
    expect(screen.getByText(/pick a character/i)).toBeInTheDocument();
  });

  it('renders the empty outfits state with a wardrobe-available CTA when inventory has items', () => {
    setupHooks({ outfits: [], inventory: [makeItem(1, 'Plain Tunic')] });
    renderWithProviders(<WardrobePage />);
    expect(screen.getByText(/no saved outfits yet/i)).toBeInTheDocument();
    expect(screen.getByText(/save your current look/i)).toBeInTheDocument();
    // Both header CTA and empty-state CTA live in the document.
    expect(screen.getAllByRole('button', { name: /save look/i }).length).toBeGreaterThanOrEqual(1);
  });

  it('renders the empty outfits state without CTA when no wardrobe items are reachable', () => {
    setupHooks({ outfits: [], inventory: [] });
    renderWithProviders(<WardrobePage />);
    expect(screen.getByText(/no saved outfits yet/i)).toBeInTheDocument();
    expect(screen.getByText(/need a wardrobe item/i)).toBeInTheDocument();
  });

  it('renders one card per outfit when outfits are available', () => {
    setupHooks({
      outfits: [
        makeOutfit(1, 'Court Attire'),
        makeOutfit(2, 'Riding Leathers'),
        makeOutfit(3, 'Casual Day'),
      ],
    });
    renderWithProviders(<WardrobePage />);
    expect(screen.getByText('Court Attire')).toBeInTheDocument();
    expect(screen.getByText('Riding Leathers')).toBeInTheDocument();
    expect(screen.getByText('Casual Day')).toBeInTheDocument();
  });

  it('dispatches apply_outfit when an outfit Wear button is clicked', async () => {
    const user = userEvent.setup();
    setupHooks({ outfits: [makeOutfit(7, 'Court Attire')] });
    renderWithProviders(<WardrobePage />);

    await user.click(screen.getByRole('button', { name: /^wear$/i }));

    expect(executeActionMock).toHaveBeenCalledWith(ACTIVE_NAME, 'apply_outfit', {
      outfit_id: 7,
    });
  });

  it('dispatches undress immediately when 1 item is worn', async () => {
    const user = userEvent.setup();
    const item = makeItem(11, 'Silk Tunic');
    setupHooks({ inventory: [item], equipped: [makeEquippedRow(11)] });
    renderWithProviders(<WardrobePage />);

    await user.click(screen.getByRole('button', { name: /undress/i }));

    expect(executeActionMock).toHaveBeenCalledWith(ACTIVE_NAME, 'undress', {});
  });

  it('hides the undress button when nothing is equipped', () => {
    setupHooks({ inventory: [], equipped: [] });
    renderWithProviders(<WardrobePage />);
    expect(screen.queryByRole('button', { name: /undress/i })).not.toBeInTheDocument();
  });

  it('lists carried items in the inventory section', () => {
    setupHooks({
      inventory: [makeItem(11, 'Silk Tunic'), makeItem(12, 'Leather Boots')],
    });
    renderWithProviders(<WardrobePage />);
    expect(screen.getByText('Silk Tunic')).toBeInTheDocument();
    expect(screen.getByText('Leather Boots')).toBeInTheDocument();
  });

  it('shows the no-inventory message when nothing is carried', () => {
    setupHooks({ inventory: [], equipped: [] });
    renderWithProviders(<WardrobePage />);
    expect(screen.getByText(/aren.t carrying anything/i)).toBeInTheDocument();
  });

  it('shows the no-equipment message when nothing is worn', () => {
    setupHooks({ inventory: [makeItem(1, 'Plain Tunic')], equipped: [] });
    renderWithProviders(<WardrobePage />);
    expect(screen.getByText(/nothing equipped right now/i)).toBeInTheDocument();
  });

  it('surfaces a success toast and invalidates queries on action_result success', async () => {
    setupHooks({ inventory: [makeItem(1, 'Plain Tunic')], equipped: [] });
    renderWithProviders(<WardrobePage />);

    emitActionResult({
      success: true,
      message: 'You put on the silk tunic.',
      data: null,
    });

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('You put on the silk tunic.');
    });
  });

  it('surfaces an error toast on action_result failure', async () => {
    setupHooks({ inventory: [makeItem(1, 'Plain Tunic')], equipped: [] });
    renderWithProviders(<WardrobePage />);

    emitActionResult({
      success: false,
      message: 'You cannot wear that here.',
      data: null,
    });

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('You cannot wear that here.');
    });
  });
});
