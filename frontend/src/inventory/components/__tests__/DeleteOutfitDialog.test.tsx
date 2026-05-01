/**
 * DeleteOutfitDialog component tests.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { DeleteOutfitDialog } from '../DeleteOutfitDialog';
import type { Outfit } from '../../types';

vi.mock('../../hooks/useOutfits', () => ({
  useDeleteOutfit: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as outfitsHooks from '../../hooks/useOutfits';
import { toast } from 'sonner';

function makeOutfit(): Outfit {
  return {
    id: 7,
    name: 'Court Attire',
    description: '',
    character_sheet: 5,
    wardrobe: 99,
    slots: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  };
}

function makeDeleteMock() {
  const mutate = vi.fn();
  vi.mocked(outfitsHooks.useDeleteOutfit).mockReturnValue({
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
  } as unknown as ReturnType<typeof outfitsHooks.useDeleteOutfit>);
  return mutate;
}

describe('DeleteOutfitDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing visible when open=false', () => {
    makeDeleteMock();
    renderWithProviders(
      <DeleteOutfitDialog open={false} onOpenChange={vi.fn()} outfit={makeOutfit()} />
    );
    expect(screen.queryByText(/delete this outfit/i)).not.toBeInTheDocument();
  });

  it('renders the confirmation when open=true', () => {
    makeDeleteMock();
    renderWithProviders(
      <DeleteOutfitDialog open={true} onOpenChange={vi.fn()} outfit={makeOutfit()} />
    );
    expect(screen.getByText(/delete this outfit/i)).toBeInTheDocument();
    expect(screen.getByText('Court Attire')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /^delete$/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument();
  });

  it('fires the delete mutation and closes on success', async () => {
    const user = userEvent.setup();
    const mutate = makeDeleteMock();
    mutate.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.(undefined, _vars, undefined);
    });
    const onOpenChange = vi.fn();

    renderWithProviders(
      <DeleteOutfitDialog open={true} onOpenChange={onOpenChange} outfit={makeOutfit()} />
    );

    await user.click(screen.getByRole('button', { name: /^delete$/i }));

    expect(mutate).toHaveBeenCalledWith(
      expect.objectContaining({ id: 7, characterSheetId: 5 }),
      expect.any(Object)
    );
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Outfit deleted.');
    });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('fires error toast and stays open on failure', async () => {
    const user = userEvent.setup();
    const mutate = makeDeleteMock();
    mutate.mockImplementation((_vars, callbacks) => {
      callbacks?.onError?.(new Error('Permission denied.'), _vars, undefined);
    });
    const onOpenChange = vi.fn();

    renderWithProviders(
      <DeleteOutfitDialog open={true} onOpenChange={onOpenChange} outfit={makeOutfit()} />
    );

    await user.click(screen.getByRole('button', { name: /^delete$/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Permission denied.');
    });
    // The dialog must NOT close on failure — onOpenChange(false) shouldn't fire.
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
  });

  it('calls onOpenChange(false) when Cancel is clicked', async () => {
    const user = userEvent.setup();
    makeDeleteMock();
    const onOpenChange = vi.fn();

    renderWithProviders(
      <DeleteOutfitDialog open={true} onOpenChange={onOpenChange} outfit={makeOutfit()} />
    );

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
