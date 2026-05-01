/**
 * SaveOutfitDialog component tests.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { SaveOutfitDialog } from '../SaveOutfitDialog';
import type { ItemInstance } from '../../types';

vi.mock('../../hooks/useOutfits', () => ({
  useCreateOutfit: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as outfitsHooks from '../../hooks/useOutfits';
import { toast } from 'sonner';

function makeWardrobe(id: number, name: string): ItemInstance {
  return {
    id,
    template: {
      id: id + 1000,
      name,
      weight: '5.00',
      size: 5,
      value: 100,
      is_container: true,
      is_stackable: false,
      is_consumable: false,
      is_craftable: false,
      image_url: '',
    },
    quality_tier: {
      id: 1,
      name: 'Fine',
      color_hex: '#888888',
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

function makeCreateMock() {
  const mutate = vi.fn();
  vi.mocked(outfitsHooks.useCreateOutfit).mockReturnValue({
    mutate,
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
  } as unknown as ReturnType<typeof outfitsHooks.useCreateOutfit>);
  return mutate;
}

describe('SaveOutfitDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing visible when open=false', () => {
    makeCreateMock();
    renderWithProviders(
      <SaveOutfitDialog
        open={false}
        onOpenChange={vi.fn()}
        characterSheetId={1}
        reachableWardrobes={[makeWardrobe(50, 'Oak Wardrobe')]}
      />
    );
    expect(screen.queryByText('Save current look')).not.toBeInTheDocument();
  });

  it('renders the form when open=true', () => {
    makeCreateMock();
    renderWithProviders(
      <SaveOutfitDialog
        open={true}
        onOpenChange={vi.fn()}
        characterSheetId={1}
        reachableWardrobes={[makeWardrobe(50, 'Oak Wardrobe')]}
      />
    );
    expect(screen.getByText('Save current look')).toBeInTheDocument();
    expect(screen.getByLabelText(/name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/description/i)).toBeInTheDocument();
  });

  it('shows the empty wardrobe state when no wardrobes are reachable', () => {
    makeCreateMock();
    renderWithProviders(
      <SaveOutfitDialog
        open={true}
        onOpenChange={vi.fn()}
        characterSheetId={1}
        reachableWardrobes={[]}
      />
    );
    expect(screen.getByText(/you need a wardrobe/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/name/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /save outfit/i })).not.toBeInTheDocument();
  });

  it('disables the Save button when name is empty', () => {
    makeCreateMock();
    renderWithProviders(
      <SaveOutfitDialog
        open={true}
        onOpenChange={vi.fn()}
        characterSheetId={1}
        reachableWardrobes={[makeWardrobe(50, 'Oak Wardrobe')]}
      />
    );
    const submit = screen.getByRole('button', { name: /save outfit/i });
    expect(submit).toBeDisabled();
  });

  it('calls the create mutation with the right payload on submit', async () => {
    const user = userEvent.setup();
    const mutate = makeCreateMock();
    mutate.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.({}, _vars, undefined);
    });
    const onOpenChange = vi.fn();

    renderWithProviders(
      <SaveOutfitDialog
        open={true}
        onOpenChange={onOpenChange}
        characterSheetId={42}
        reachableWardrobes={[makeWardrobe(50, 'Oak Wardrobe')]}
      />
    );

    await user.type(screen.getByLabelText(/name/i), 'Court Attire');
    await user.type(screen.getByLabelText(/description/i), 'Silks and silver.');
    await user.click(screen.getByRole('button', { name: /save outfit/i }));

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({
        character_sheet: 42,
        wardrobe: 50,
        name: 'Court Attire',
        description: 'Silks and silver.',
      }),
      expect.any(Object)
    );

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Outfit saved.');
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('fires an error toast and stays open when the mutation fails', async () => {
    const user = userEvent.setup();
    const mutate = makeCreateMock();
    mutate.mockImplementation((_vars, callbacks) => {
      callbacks?.onError?.(new Error('Outfit name already in use.'), _vars, undefined);
    });
    const onOpenChange = vi.fn();

    renderWithProviders(
      <SaveOutfitDialog
        open={true}
        onOpenChange={onOpenChange}
        characterSheetId={1}
        reachableWardrobes={[makeWardrobe(50, 'Oak Wardrobe')]}
      />
    );

    await user.type(screen.getByLabelText(/name/i), 'Court Attire');
    await user.click(screen.getByRole('button', { name: /save outfit/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Outfit name already in use.');
    });
    // Dialog must remain open — onOpenChange(false) should NOT be called.
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });
});
