/**
 * CreateGMCharacterDialog tests (#3478 fix round — Finding 2). Mirrors
 * `stories/__tests__/StoryFormDialog.test.tsx`'s convention: mock the
 * owning query module's mutation hook directly and drive its `mutate`
 * mock's `onSuccess` callback to exercise the dialog's success path.
 */
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { CreateGMCharacterDialog } from '../CreateGMCharacterDialog';
import { renderWithProviders } from '@/test/utils/renderWithProviders';

const mintMock = vi.fn();
let mintIsPending = false;

vi.mock('../queries', () => ({
  useMintGMCharacterMutation: () => ({ mutate: mintMock, isPending: mintIsPending }),
}));

describe('CreateGMCharacterDialog', () => {
  afterEach(() => {
    mintIsPending = false;
    vi.clearAllMocks();
  });

  it('disables Create while the name field is empty', () => {
    renderWithProviders(<CreateGMCharacterDialog open onOpenChange={vi.fn()} />);
    expect(screen.getByTestId('create-gm-character-submit')).toBeDisabled();
  });

  it('enables Create once a name is typed, and submits the trimmed name', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    renderWithProviders(<CreateGMCharacterDialog open onOpenChange={onOpenChange} />);

    await user.type(screen.getByLabelText(/name/i), '  Warden Vex  ');
    const submit = screen.getByTestId('create-gm-character-submit');
    expect(submit).not.toBeDisabled();

    await user.click(submit);

    expect(mintMock).toHaveBeenCalledWith('Warden Vex', expect.any(Object));
  });

  it('closes the dialog when the mutation succeeds', async () => {
    const user = userEvent.setup();
    const onOpenChange = vi.fn();
    mintMock.mockImplementation((_name: string, callbacks: { onSuccess?: () => void }) => {
      callbacks.onSuccess?.();
    });
    renderWithProviders(<CreateGMCharacterDialog open onOpenChange={onOpenChange} />);

    await user.type(screen.getByLabelText(/name/i), 'Warden Vex');
    await user.click(screen.getByTestId('create-gm-character-submit'));

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it('disables Create while the mutation is pending, even with a name typed', async () => {
    const user = userEvent.setup();
    mintIsPending = true;
    renderWithProviders(<CreateGMCharacterDialog open onOpenChange={vi.fn()} />);

    await user.type(screen.getByLabelText(/name/i), 'Warden Vex');

    expect(screen.getByTestId('create-gm-character-submit')).toBeDisabled();
  });
});
