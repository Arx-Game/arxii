import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { DispatchResult } from '@/combat/types';

interface DispatchBody {
  ref: { backend: string; registry_key: string };
  kwargs: Record<string, unknown>;
}

const mutateAsync = vi.fn(
  (_body: DispatchBody): Promise<DispatchResult> =>
    Promise.resolve({
      backend: 'registry',
      deferred: false,
      success: true,
      message: 'Suggestion submitted to staff for review.',
    })
);
vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn((_characterId: number) => ({
    mutateAsync,
    isPending: false,
  })),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { CatalogSuggestionDialog } from '../CatalogSuggestionDialog';
import { toast } from 'sonner';

beforeEach(() => {
  mutateAsync.mockClear();
  mutateAsync.mockImplementation(() =>
    Promise.resolve({
      backend: 'registry',
      deferred: false,
      success: true,
      message: 'Suggestion submitted to staff for review.',
    })
  );
  (toast.success as ReturnType<typeof vi.fn>).mockClear();
  (toast.error as ReturnType<typeof vi.fn>).mockClear();
});

describe('CatalogSuggestionDialog', () => {
  it('dispatches gm_submit_catalog_suggestion with kind, text and the kind ref', async () => {
    const user = userEvent.setup();
    render(
      <CatalogSuggestionDialog open onOpenChange={vi.fn()} characterId={42} kindName="Chase" />
    );

    await user.selectOptions(screen.getByTestId('suggestion-proposal-kind'), 'check_fit');
    await user.type(screen.getByTestId('suggestion-text'), 'Sprint fits a chase');
    await user.click(screen.getByTestId('suggestion-submit'));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'gm_submit_catalog_suggestion' },
        kwargs: {
          proposal_kind: 'check_fit',
          proposal_text: 'Sprint fits a chase',
          situation_kind_ref: 'Chase',
        },
      });
    });
    expect(toast.success).toHaveBeenCalled();
  });

  it('reports a refusal from the server as an error toast and keeps the dialog open', async () => {
    const user = userEvent.setup();
    mutateAsync.mockImplementation(() =>
      Promise.resolve({
        backend: 'registry',
        deferred: false,
        success: false,
        message: 'Suggesting a pool_guide needs Experienced trust or higher.',
      })
    );
    const onOpenChange = vi.fn();

    render(
      <CatalogSuggestionDialog open onOpenChange={onOpenChange} characterId={42} kindName="Chase" />
    );

    await user.type(screen.getByTestId('suggestion-text'), 'Pools should favor stealth');
    await user.click(screen.getByTestId('suggestion-submit'));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        'Suggesting a pool_guide needs Experienced trust or higher.'
      );
    });
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(screen.getByTestId('suggestion-dialog')).toBeInTheDocument();
  });

  it('omits situation_kind_ref when no kind was given', async () => {
    const user = userEvent.setup();
    render(<CatalogSuggestionDialog open onOpenChange={vi.fn()} characterId={42} />);

    await user.type(screen.getByTestId('suggestion-text'), 'A whole new kind of trouble');
    await user.click(screen.getByTestId('suggestion-submit'));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'gm_submit_catalog_suggestion' },
        kwargs: {
          proposal_kind: 'new_situation',
          proposal_text: 'A whole new kind of trouble',
        },
      });
    });
  });
});
