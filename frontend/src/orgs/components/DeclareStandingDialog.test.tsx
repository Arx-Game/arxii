/**
 * DeclareStandingDialog tests (#3290).
 *
 * Covers: form gating (submit disabled without a persona + citation), the
 * dispatch payload shape (registry key, target/organization/direction/citation
 * kwargs), and surfacing a refused declaration's message (e.g. consent-block,
 * rate-limit, or rank refusal — all typed StandingDeclarationError subclasses
 * that the backend action turns into `ActionResult(success=False, message=...)`).
 */

import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { DeclareStandingDialog } from './DeclareStandingDialog';

const mutateAsyncMock = vi.fn();

vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn(() => ({
    mutateAsync: mutateAsyncMock,
    isPending: false,
  })),
}));

vi.mock('@/roster/usePersonaSearch', () => ({
  usePersonaSearch: vi.fn(() => ({
    results: [{ id: 3, name: 'Serenity Vale', character_sheet: 30 }],
    isFetching: false,
  })),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('DeclareStandingDialog', () => {
  beforeEach(() => {
    mutateAsyncMock.mockReset();
  });

  it('disables Declare until a persona and citation are provided', async () => {
    render(
      <DeclareStandingDialog
        organizationId={7}
        organizationName="The Gilded Compass"
        characterId={42}
      >
        <button>Declare Standing</button>
      </DeclareStandingDialog>,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByRole('button', { name: 'Declare Standing' }));

    const declareButton = screen.getByRole('button', { name: /^Declare$/ });
    expect(declareButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText(/Search for a persona/i), {
      target: { value: 'Serenity' },
    });
    fireEvent.click(await screen.findByText('Serenity Vale'));

    // Still disabled — no citation yet.
    expect(declareButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText(/Why is this declared/i), {
      target: { value: 'For tireless service to the guild.' },
    });

    expect(declareButton).not.toBeDisabled();
  });

  it('dispatches declare_standing with the expected kwargs', async () => {
    mutateAsyncMock.mockResolvedValue({ backend: 'registry', deferred: false, success: true });

    render(
      <DeclareStandingDialog
        organizationId={7}
        organizationName="The Gilded Compass"
        characterId={42}
      >
        <button>Declare Standing</button>
      </DeclareStandingDialog>,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByRole('button', { name: 'Declare Standing' }));
    fireEvent.change(screen.getByPlaceholderText(/Search for a persona/i), {
      target: { value: 'Serenity' },
    });
    fireEvent.click(await screen.findByText('Serenity Vale'));
    fireEvent.change(screen.getByPlaceholderText(/Why is this declared/i), {
      target: { value: 'For tireless service to the guild.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Declare$/ }));

    await waitFor(() => expect(mutateAsyncMock).toHaveBeenCalledTimes(1));
    expect(mutateAsyncMock).toHaveBeenCalledWith({
      ref: { backend: 'registry', registry_key: 'declare_standing' },
      kwargs: {
        target: 3,
        organization_id: 7,
        direction: 'favor',
        citation: 'For tireless service to the guild.',
      },
    });
  });

  it('surfaces a refused declaration (e.g. consent block / rate limit) inline', async () => {
    mutateAsyncMock.mockResolvedValue({
      backend: 'registry',
      deferred: false,
      success: false,
      message: 'They have not opened themselves to being antagonised.',
    });

    render(
      <DeclareStandingDialog
        organizationId={7}
        organizationName="The Gilded Compass"
        characterId={42}
      >
        <button>Declare Standing</button>
      </DeclareStandingDialog>,
      { wrapper: createWrapper() }
    );

    fireEvent.click(screen.getByRole('button', { name: 'Declare Standing' }));
    fireEvent.change(screen.getByPlaceholderText(/Search for a persona/i), {
      target: { value: 'Serenity' },
    });
    fireEvent.click(await screen.findByText('Serenity Vale'));
    fireEvent.change(screen.getByPlaceholderText(/Why is this declared/i), {
      target: { value: 'Marking them.' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Declare$/ }));

    expect(
      await screen.findByText(/have not opened themselves to being antagonised/i)
    ).toBeInTheDocument();
  });
});
