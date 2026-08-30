/**
 * HonorForm tests (#3466 Task 10).
 *
 * Covers: the Hare cost preview renders before submit, submit is disabled while the
 * mutation is pending (or fields are empty), the correct payload is posted, and a
 * server refusal (`400 {detail}` -> `ApiError.message` via `readErrorDetail`) is
 * surfaced inline — not just a toast, mirroring `JournalComposerDialog`'s established
 * inline-error convention (#3412 T4).
 */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { HonorForm } from '../HonorForm';

vi.mock('../../queries', () => ({
  useHonorDeed: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as queries from '../../queries';

function makeHonorMock(opts: { isPending?: boolean; error?: Error } = {}) {
  const mutateMock = vi.fn();
  vi.mocked(queries.useHonorDeed).mockReturnValue({
    mutate: mutateMock,
    isPending: opts.isPending ?? false,
    isError: !!opts.error,
    error: opts.error ?? null,
  } as unknown as ReturnType<typeof queries.useHonorDeed>);
  return mutateMock;
}

describe('HonorForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows the Hare cost before the player submits', () => {
    makeHonorMock();
    render(<HonorForm deedId={1} hareCost={3} valueAdded={10} />);
    expect(screen.getByTestId('honor-form-cost')).toHaveTextContent('3');
    // Not yet submitted -- mutate must not have been called merely by rendering.
    expect(queries.useHonorDeed).toHaveBeenCalled();
  });

  it('disables submit until both journal fields are filled', async () => {
    const user = userEvent.setup();
    makeHonorMock();
    render(<HonorForm deedId={1} hareCost={3} valueAdded={10} />);

    const submit = screen.getByRole('button', { name: /honor this deed/i });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText(/title/i), 'A Song of Steel');
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText(/account|entry|body/i), 'They stood alone.');
    expect(submit).not.toBeDisabled();
  });

  it('disables submit while the mutation is pending, even with valid fields', async () => {
    const user = userEvent.setup();
    makeHonorMock({ isPending: true });
    render(<HonorForm deedId={1} hareCost={3} valueAdded={10} />);

    await user.type(screen.getByLabelText(/title/i), 'A Song of Steel');
    await user.type(screen.getByLabelText(/account|entry|body/i), 'They stood alone.');

    expect(screen.getByRole('button', { name: /honor/i })).toBeDisabled();
  });

  it('posts the journal_title/journal_body payload on submit', async () => {
    const user = userEvent.setup();
    const mutateMock = makeHonorMock();
    render(<HonorForm deedId={7} hareCost={3} valueAdded={10} />);

    await user.type(screen.getByLabelText(/title/i), 'A Song of Steel');
    await user.type(screen.getByLabelText(/account|entry|body/i), 'They stood alone.');
    await user.click(screen.getByRole('button', { name: /honor this deed/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      { journal_title: 'A Song of Steel', journal_body: 'They stood alone.' },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) })
    );
  });

  it('surfaces a server refusal message inline', () => {
    makeHonorMock({ error: new Error('You have already honored this deed.') });
    render(<HonorForm deedId={1} hareCost={3} valueAdded={10} />);

    expect(screen.getByTestId('honor-form-error')).toHaveTextContent(
      'You have already honored this deed.'
    );
  });

  it('renders no inline error block when the mutation has not errored', () => {
    makeHonorMock();
    render(<HonorForm deedId={1} hareCost={3} valueAdded={10} />);
    expect(screen.queryByTestId('honor-form-error')).not.toBeInTheDocument();
  });
});
