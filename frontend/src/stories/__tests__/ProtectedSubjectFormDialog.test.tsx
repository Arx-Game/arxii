/**
 * ProtectedSubjectFormDialog tests (#2001 Task 8).
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ProtectedSubjectFormDialog } from '../components/ProtectedSubjectFormDialog';

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
  useCreateProtectedSubject: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

function makeMutationMock() {
  const mutate = vi.fn();
  vi.mocked(queries.useCreateProtectedSubject).mockReturnValue({
    mutate,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return mutate;
}

describe('ProtectedSubjectFormDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('opens the dialog from the trigger button', async () => {
    const user = userEvent.setup();
    makeMutationMock();
    renderWithProviders(<ProtectedSubjectFormDialog storyId={1} />);

    await user.click(screen.getByTestId('add-protected-subject-btn'));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText('Protect a subject')).toBeInTheDocument();
  });

  it('defaults to the custom kind with a freeform label field', async () => {
    const user = userEvent.setup();
    makeMutationMock();
    renderWithProviders(<ProtectedSubjectFormDialog storyId={1} />);

    await user.click(screen.getByTestId('add-protected-subject-btn'));

    expect(screen.getByLabelText(/^label$/i)).toBeInTheDocument();
  });

  it('submits an npc_fate subject with the sheet id and notes', async () => {
    const user = userEvent.setup();
    const mutate = makeMutationMock();
    mutate.mockImplementation((_vars, callbacks) => callbacks?.onSuccess?.(_vars));

    renderWithProviders(<ProtectedSubjectFormDialog storyId={7} />);
    await user.click(screen.getByTestId('add-protected-subject-btn'));

    const kindSelect = screen.getAllByTestId('mock-select')[0];
    await user.selectOptions(kindSelect, 'npc_fate');
    await user.type(screen.getByLabelText(/character sheet id/i), '42');
    await user.type(screen.getByLabelText(/gm notes/i), 'Load-bearing NPC');

    await user.click(screen.getByRole('button', { name: /^add$/i }));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          story: 7,
          subject_kind: 'npc_fate',
          subject_sheet: 42,
          notes: 'Load-bearing NPC',
        }),
        expect.any(Object)
      );
    });
  });

  it('closes and toasts on success', async () => {
    const user = userEvent.setup();
    const mutate = makeMutationMock();
    mutate.mockImplementation((_vars, callbacks) => callbacks?.onSuccess?.({ id: 1, ..._vars }));

    renderWithProviders(<ProtectedSubjectFormDialog storyId={7} />);
    await user.click(screen.getByTestId('add-protected-subject-btn'));
    await user.type(screen.getByLabelText(/^label$/i), 'The old windmill');
    await user.click(screen.getByRole('button', { name: /^add$/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Protected subject added');
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('surfaces non_field_errors inline on a validation error', async () => {
    const user = userEvent.setup();
    const mutate = makeMutationMock();
    const mockErrorResponse = {
      json: () =>
        Promise.resolve({
          non_field_errors: ['Exactly one of subject_sheet/... must be set.'],
        }),
    };
    mutate.mockImplementation((_vars, callbacks) =>
      callbacks?.onError?.({ response: mockErrorResponse })
    );

    renderWithProviders(<ProtectedSubjectFormDialog storyId={7} />);
    await user.click(screen.getByTestId('add-protected-subject-btn'));
    await user.click(screen.getByRole('button', { name: /^add$/i }));

    await waitFor(() => {
      expect(screen.getByText(/exactly one of subject_sheet/i)).toBeInTheDocument();
    });
  });
});
