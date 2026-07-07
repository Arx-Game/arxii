/**
 * RequestClearanceDialog tests (#2001 Task 8) — identity-path clearance
 * request dialog reachable from ClearanceInbox.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { RequestClearanceDialog } from '../components/RequestClearanceDialog';

vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
    disabled,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    children?: React.ReactNode;
    disabled?: boolean;
  }) => (
    <select
      value={value}
      disabled={disabled}
      onChange={(e) => onValueChange?.(e.target.value)}
      data-testid="mock-select"
    >
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children?: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
}));

vi.mock('@/events/queries', () => ({
  searchOrganizations: vi.fn().mockResolvedValue([]),
  searchSocieties: vi.fn().mockResolvedValue([]),
}));

vi.mock('../queries', () => ({
  useRequestClearance: vi.fn(),
  useStoryList: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

function makeMocks() {
  const mutate = vi.fn();
  vi.mocked(queries.useRequestClearance).mockReturnValue({
    mutate,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useStoryList).mockReturnValue({
    data: { count: 0, next: null, previous: null, results: [] },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return mutate;
}

describe('RequestClearanceDialog', () => {
  beforeEach(() => vi.clearAllMocks());

  it('opens from the trigger button', async () => {
    const user = userEvent.setup();
    makeMocks();
    renderWithProviders(<RequestClearanceDialog />);

    await user.click(screen.getByTestId('request-clearance-btn'));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Request custody clearance')).toBeInTheDocument();
  });

  it('submits the identity-path body with a custom label subject', async () => {
    const user = userEvent.setup();
    const mutate = makeMocks();
    mutate.mockImplementation((_vars, callbacks) => callbacks?.onSuccess?.([{ id: 1 }]));

    renderWithProviders(<RequestClearanceDialog />);
    await user.click(screen.getByTestId('request-clearance-btn'));

    await user.type(screen.getByLabelText(/^label$/i), 'The old windmill');
    await user.type(screen.getByLabelText(/message/i), 'Need to burn it down');
    await user.click(screen.getByRole('button', { name: /^request$/i }));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          subject_kind: 'custom',
          subject_label: 'The old windmill',
          scope: 'appear',
          message: 'Need to burn it down',
        }),
        expect.any(Object)
      );
    });
  });

  it('shows a toast noting how many protections matched on success', async () => {
    const user = userEvent.setup();
    const mutate = makeMocks();
    mutate.mockImplementation((_vars, callbacks) => callbacks?.onSuccess?.([{ id: 1 }, { id: 2 }]));

    renderWithProviders(<RequestClearanceDialog />);
    await user.click(screen.getByTestId('request-clearance-btn'));
    await user.type(screen.getByLabelText(/^label$/i), 'The Iron Concord');
    await user.click(screen.getByRole('button', { name: /^request$/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Clearance requested (2 protections matched)');
    });
  });
});
