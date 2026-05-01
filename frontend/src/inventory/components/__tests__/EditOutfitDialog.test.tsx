/**
 * EditOutfitDialog component tests.
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { EditOutfitDialog } from '../EditOutfitDialog';
import type { ItemInstance, Outfit, OutfitSlot } from '../../types';

// jsdom doesn't implement Element.scrollIntoView, but cmdk calls it whenever
// a Command.Item mounts/selects. Stub it before any test renders.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn();
}

vi.mock('../../hooks/useOutfits', () => ({
  useUpdateOutfit: vi.fn(),
  useCreateOutfitSlot: vi.fn(),
  useDeleteOutfitSlot: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as outfitsHooks from '../../hooks/useOutfits';
import { toast } from 'sonner';

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

function makeSlot(id: number, item: ItemInstance): OutfitSlot {
  return {
    id,
    outfit: 1,
    item_instance: item,
    body_region: 'torso',
    equipment_layer: 'base',
  };
}

function makeOutfit(slots: OutfitSlot[] = []): Outfit {
  return {
    id: 1,
    name: 'Court Attire',
    description: 'Silks and silver.',
    character_sheet: 5,
    wardrobe: 99,
    slots,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

interface MutationMocks {
  update: ReturnType<typeof vi.fn>;
  createSlot: ReturnType<typeof vi.fn>;
  deleteSlot: ReturnType<typeof vi.fn>;
}

function makeMutationMocks(): MutationMocks {
  const update = vi.fn();
  const createSlot = vi.fn();
  const deleteSlot = vi.fn();

  const stub = (m: ReturnType<typeof vi.fn>) =>
    ({
      mutate: m,
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
    }) as unknown as ReturnType<typeof outfitsHooks.useUpdateOutfit>;

  vi.mocked(outfitsHooks.useUpdateOutfit).mockReturnValue(stub(update));
  vi.mocked(outfitsHooks.useCreateOutfitSlot).mockReturnValue(
    stub(createSlot) as unknown as ReturnType<typeof outfitsHooks.useCreateOutfitSlot>
  );
  vi.mocked(outfitsHooks.useDeleteOutfitSlot).mockReturnValue(
    stub(deleteSlot) as unknown as ReturnType<typeof outfitsHooks.useDeleteOutfitSlot>
  );

  return { update, createSlot, deleteSlot };
}

describe('EditOutfitDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing visible when open=false', () => {
    makeMutationMocks();
    renderWithProviders(
      <EditOutfitDialog
        open={false}
        onOpenChange={vi.fn()}
        outfit={makeOutfit()}
        carriedItems={[]}
      />
    );
    expect(screen.queryByText('Edit outfit')).not.toBeInTheDocument();
  });

  it('renders the outfit name pre-populated when open=true', () => {
    makeMutationMocks();
    renderWithProviders(
      <EditOutfitDialog
        open={true}
        onOpenChange={vi.fn()}
        outfit={makeOutfit()}
        carriedItems={[]}
      />
    );
    expect(screen.getByText('Edit outfit')).toBeInTheDocument();
    const nameInput = screen.getByLabelText(/name/i) as HTMLInputElement;
    expect(nameInput.value).toBe('Court Attire');
  });

  it('disables the Save button when the form is not dirty', () => {
    makeMutationMocks();
    renderWithProviders(
      <EditOutfitDialog
        open={true}
        onOpenChange={vi.fn()}
        outfit={makeOutfit()}
        carriedItems={[]}
      />
    );
    const saveBtn = screen.getByRole('button', { name: /^save$/i });
    expect(saveBtn).toBeDisabled();
  });

  it('disables the Save button when the name is whitespace', async () => {
    const user = userEvent.setup();
    makeMutationMocks();
    renderWithProviders(
      <EditOutfitDialog
        open={true}
        onOpenChange={vi.fn()}
        outfit={makeOutfit()}
        carriedItems={[]}
      />
    );
    const nameInput = screen.getByLabelText(/name/i);
    await user.clear(nameInput);
    await user.type(nameInput, '   ');
    expect(screen.getByRole('button', { name: /^save$/i })).toBeDisabled();
  });

  it('fires update mutation with trimmed payload on Save', async () => {
    const user = userEvent.setup();
    const { update } = makeMutationMocks();
    update.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });

    renderWithProviders(
      <EditOutfitDialog
        open={true}
        onOpenChange={vi.fn()}
        outfit={makeOutfit()}
        carriedItems={[]}
      />
    );

    const nameInput = screen.getByLabelText(/name/i);
    await user.clear(nameInput);
    await user.type(nameInput, 'Festival Robes');

    await user.click(screen.getByRole('button', { name: /^save$/i }));

    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 1,
        payload: expect.objectContaining({
          name: 'Festival Robes',
        }),
      }),
      expect.any(Object)
    );
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Outfit updated.');
    });
  });

  it('lists existing slot rows', () => {
    makeMutationMocks();
    const slot = makeSlot(10, makeItem(7, 'Silk Tunic'));
    renderWithProviders(
      <EditOutfitDialog
        open={true}
        onOpenChange={vi.fn()}
        outfit={makeOutfit([slot])}
        carriedItems={[]}
      />
    );
    expect(screen.getByText('Silk Tunic')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /remove silk tunic/i })).toBeInTheDocument();
  });

  it('fires deleteSlot when a Remove button is clicked', async () => {
    const user = userEvent.setup();
    const { deleteSlot } = makeMutationMocks();
    deleteSlot.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.(undefined, _vars, undefined);
    });
    const slot = makeSlot(10, makeItem(7, 'Silk Tunic'));

    renderWithProviders(
      <EditOutfitDialog
        open={true}
        onOpenChange={vi.fn()}
        outfit={makeOutfit([slot])}
        carriedItems={[]}
      />
    );

    await user.click(screen.getByRole('button', { name: /remove silk tunic/i }));

    expect(deleteSlot).toHaveBeenCalledWith(
      expect.objectContaining({ id: 10, outfitId: 1 }),
      expect.any(Object)
    );
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Removed "Silk Tunic".');
    });
  });

  it('fires createSlot when a carried item is added', async () => {
    // Radix Popover sets `pointer-events: none` on the body when closed —
    // user-event guards against that, so we relax the check here so we can
    // open the popover-backed cmdk Combobox in jsdom.
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const { createSlot } = makeMutationMocks();
    createSlot.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });
    const carried = makeItem(99, 'Velvet Cloak');

    renderWithProviders(
      <EditOutfitDialog
        open={true}
        onOpenChange={vi.fn()}
        outfit={makeOutfit()}
        carriedItems={[carried]}
      />
    );

    // The cmdk picker, body-region select, and equipment-layer select all share
    // the "combobox" ARIA role. Scope to the add-slot row and pick the cmdk
    // trigger (the first by markup order).
    const addRow = document.querySelector('[data-add-slot-row]') as HTMLElement;
    expect(addRow).toBeTruthy();
    const comboboxes = within(addRow).getAllByRole('combobox');
    await user.click(comboboxes[0]);
    await user.click(await screen.findByText('Velvet Cloak'));

    await user.click(screen.getByRole('button', { name: /^add$/i }));

    expect(createSlot).toHaveBeenCalledWith(
      expect.objectContaining({
        outfit: 1,
        item_instance: 99,
        body_region: 'torso',
        equipment_layer: 'base',
      }),
      expect.any(Object)
    );
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Piece added.');
    });
  });

  it('shows the no-carried-items hint when carriedItems is empty', () => {
    makeMutationMocks();
    renderWithProviders(
      <EditOutfitDialog
        open={true}
        onOpenChange={vi.fn()}
        outfit={makeOutfit()}
        carriedItems={[]}
      />
    );
    expect(screen.getByText(/no carried items available/i)).toBeInTheDocument();
  });
});
