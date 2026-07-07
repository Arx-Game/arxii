/**
 * GrantClearanceDialog, DenyClearanceDialog, ResolveClearanceDialog tests
 * (#2001 Task 8). Mirrors ApproveRejectClaimDialogs.test.tsx's combined-file
 * pattern since all three share the same note-input dialog shape.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { GrantClearanceDialog } from '../components/GrantClearanceDialog';
import { DenyClearanceDialog } from '../components/DenyClearanceDialog';
import { ResolveClearanceDialog } from '../components/ResolveClearanceDialog';

vi.mock('../queries', () => ({
  useGrantClearance: vi.fn(),
  useDenyClearance: vi.fn(),
  useResolveClearance: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

function makeMock(hook: 'useGrantClearance' | 'useDenyClearance' | 'useResolveClearance') {
  const mutate = vi.fn();
  vi.mocked(queries[hook]).mockReturnValue({
    mutate,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return mutate;
}

describe('GrantClearanceDialog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('grants with an optional note', async () => {
    const user = userEvent.setup();
    const mutate = makeMock('useGrantClearance');
    mutate.mockImplementation((_vars, callbacks) => callbacks?.onSuccess?.());

    renderWithProviders(<GrantClearanceDialog clearanceId={9} />);
    await user.click(screen.getByTestId('grant-clearance-btn'));
    await user.type(screen.getByLabelText(/note/i), 'Go ahead');
    await user.click(screen.getByRole('button', { name: /^grant$/i }));

    expect(mutate).toHaveBeenCalledWith(
      { id: 9, body: { response_note: 'Go ahead' } },
      expect.any(Object)
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Clearance granted'));
  });
});

describe('DenyClearanceDialog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('denies with an optional note', async () => {
    const user = userEvent.setup();
    const mutate = makeMock('useDenyClearance');
    mutate.mockImplementation((_vars, callbacks) => callbacks?.onSuccess?.());

    renderWithProviders(<DenyClearanceDialog clearanceId={9} />);
    await user.click(screen.getByTestId('deny-clearance-btn'));
    await user.type(screen.getByLabelText(/note/i), 'Not this time');
    await user.click(screen.getByRole('button', { name: /^deny$/i }));

    expect(mutate).toHaveBeenCalledWith(
      { id: 9, body: { response_note: 'Not this time' } },
      expect.any(Object)
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Clearance denied'));
  });
});

describe('ResolveClearanceDialog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('resolves with grant=true when Grant is clicked', async () => {
    const user = userEvent.setup();
    const mutate = makeMock('useResolveClearance');
    mutate.mockImplementation((_vars, callbacks) => callbacks?.onSuccess?.());

    renderWithProviders(<ResolveClearanceDialog clearanceId={11} />);
    await user.click(screen.getByTestId('resolve-clearance-btn'));
    await user.click(screen.getByTestId('resolve-clearance-grant-btn'));

    expect(mutate).toHaveBeenCalledWith(
      { id: 11, body: { grant: true, response_note: '' } },
      expect.any(Object)
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Escalation resolved: granted'));
  });

  it('resolves with grant=false when Deny is clicked', async () => {
    const user = userEvent.setup();
    const mutate = makeMock('useResolveClearance');
    mutate.mockImplementation((_vars, callbacks) => callbacks?.onSuccess?.());

    renderWithProviders(<ResolveClearanceDialog clearanceId={11} />);
    await user.click(screen.getByTestId('resolve-clearance-btn'));
    await user.click(screen.getByTestId('resolve-clearance-deny-btn'));

    expect(mutate).toHaveBeenCalledWith(
      { id: 11, body: { grant: false, response_note: '' } },
      expect.any(Object)
    );
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('Escalation resolved: denied'));
  });
});
