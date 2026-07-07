/**
 * EscalateClearanceButton, RevokeClearanceButton tests (#2001 Task 8).
 * Both are AlertDialog-confirm-only actions, mirroring ExpireBeatsButton.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { EscalateClearanceButton } from '../components/EscalateClearanceButton';
import { RevokeClearanceButton } from '../components/RevokeClearanceButton';

vi.mock('../queries', () => ({
  useEscalateClearance: vi.fn(),
  useRevokeClearance: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

function makeMock(hook: 'useEscalateClearance' | 'useRevokeClearance') {
  const mutate = vi.fn();
  vi.mocked(queries[hook]).mockReturnValue({
    mutate,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return mutate;
}

describe('EscalateClearanceButton', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls escalateClearance on confirm', async () => {
    const user = userEvent.setup();
    const mutate = makeMock('useEscalateClearance');
    mutate.mockImplementation((_id, callbacks) => callbacks?.onSuccess?.());

    renderWithProviders(<EscalateClearanceButton clearanceId={9} />);
    await user.click(screen.getByTestId('escalate-clearance-btn'));
    await user.click(screen.getByRole('button', { name: /^escalate$/i }));

    expect(mutate).toHaveBeenCalledWith(9, expect.any(Object));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Escalated to staff'));
  });
});

describe('RevokeClearanceButton', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls revokeClearance on confirm', async () => {
    const user = userEvent.setup();
    const mutate = makeMock('useRevokeClearance');
    mutate.mockImplementation((_id, callbacks) => callbacks?.onSuccess?.());

    renderWithProviders(<RevokeClearanceButton clearanceId={9} />);
    await user.click(screen.getByTestId('revoke-clearance-btn'));
    await user.click(screen.getByRole('button', { name: /^revoke$/i }));

    expect(mutate).toHaveBeenCalledWith(9, expect.any(Object));
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Clearance revoked'));
  });
});
