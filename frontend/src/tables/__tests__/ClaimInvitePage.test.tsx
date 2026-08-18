/**
 * ClaimInvitePage Tests (#3268)
 *
 * Covers: the code input pre-fills from `?code=`, a successful claim shows
 * the success panel, and a field error on `code` renders verbatim under the
 * input.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { ApiError } from '@/lib/errors';
import { ClaimInvitePage } from '../pages/ClaimInvitePage';

vi.mock('../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../queries')>();
  return {
    ...actual,
    useClaimInvite: vi.fn(),
  };
});

import * as queries from '../queries';

interface MutateOpts {
  onSuccess?: (data: { application_id: number }) => void;
  onError?: (err: unknown) => void;
}

function Wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderPage(initialEntries: string[] = ['/invites/claim']) {
  return render(
    <Wrapper>
      <MemoryRouter initialEntries={initialEntries}>
        <ClaimInvitePage />
      </MemoryRouter>
    </Wrapper>
  );
}

describe('ClaimInvitePage', () => {
  it('pre-fills the code input from ?code=', () => {
    vi.mocked(queries.useClaimInvite).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof queries.useClaimInvite>);

    renderPage(['/invites/claim?code=sunny-day-1']);

    expect(screen.getByLabelText(/invite code/i)).toHaveValue('sunny-day-1');
  });

  it('leaves the code input blank with no ?code=', () => {
    vi.mocked(queries.useClaimInvite).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof queries.useClaimInvite>);

    renderPage();

    expect(screen.getByLabelText(/invite code/i)).toHaveValue('');
  });

  it('claims the entered code on submit', async () => {
    const mutateFn = vi.fn();
    vi.mocked(queries.useClaimInvite).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useClaimInvite>);

    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/invite code/i), 'sunny-day-1');
    await user.click(screen.getByRole('button', { name: /claim invite/i }));

    expect(mutateFn).toHaveBeenCalledWith('sunny-day-1', expect.any(Object));
  });

  it('shows a success panel on a successful claim', async () => {
    const mutateFn = vi.fn((_code: string, opts: MutateOpts) => {
      opts.onSuccess?.({ application_id: 42 });
    });
    vi.mocked(queries.useClaimInvite).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useClaimInvite>);

    const user = userEvent.setup();
    renderPage(['/invites/claim?code=sunny-day-1']);

    await user.click(screen.getByRole('button', { name: /claim invite/i }));

    expect(await screen.findByText(/application submitted/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/invite code/i)).not.toBeInTheDocument();
  });

  it('renders a code field error verbatim under the input', async () => {
    const mutateFn = vi.fn((_code: string, opts: MutateOpts) => {
      opts.onError?.(
        new ApiError('Invalid invite code.', {
          status: 400,
          fieldErrors: { code: ['Invalid invite code.'] },
        })
      );
    });
    vi.mocked(queries.useClaimInvite).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useClaimInvite>);

    const user = userEvent.setup();
    renderPage(['/invites/claim?code=bad-code']);

    await user.click(screen.getByRole('button', { name: /claim invite/i }));

    expect(await screen.findByText('Invalid invite code.')).toBeInTheDocument();
    // The form stays up (not the success panel) so the player can retry.
    expect(screen.getByLabelText(/invite code/i)).toBeInTheDocument();
  });

  it('renders a non_field_errors detail verbatim (e.g. an already-claimed invite)', async () => {
    const mutateFn = vi.fn((_code: string, opts: MutateOpts) => {
      opts.onError?.(
        new ApiError('You already have a finalized application for this character.', {
          status: 400,
          fieldErrors: {
            non_field_errors: ['You already have a finalized application for this character.'],
          },
        })
      );
    });
    vi.mocked(queries.useClaimInvite).mockReturnValue({
      mutate: mutateFn,
      isPending: false,
    } as unknown as ReturnType<typeof queries.useClaimInvite>);

    const user = userEvent.setup();
    renderPage(['/invites/claim?code=claimed-code']);

    await user.click(screen.getByRole('button', { name: /claim invite/i }));

    expect(
      await screen.findByText('You already have a finalized application for this character.')
    ).toBeInTheDocument();
  });
});
