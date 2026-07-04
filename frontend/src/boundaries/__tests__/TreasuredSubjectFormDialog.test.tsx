/**
 * TreasuredSubjectFormDialog tests (#1771) — flagging a treasured subject for
 * one of the player's tenures, including the "specific characters" sharing
 * surface backed by `visible_to_tenures`.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { TreasuredSubjectFormDialog } from '../components/TreasuredSubjectFormDialog';
import type { TreasuredSubject } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

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

vi.mock('@/components/TenureMultiSearch', () => ({
  TenureMultiSearch: ({
    value,
    onChange,
    label,
  }: {
    value: { value: number; label: string }[];
    onChange: (v: { value: number; label: string }[]) => void;
    label?: string;
  }) => (
    <div>
      <span>{label}</span>
      <button
        type="button"
        onClick={() => onChange([...value, { value: 7, label: 'Test Tenure' }])}
      >
        add-tenure
      </button>
    </div>
  ),
}));

vi.mock('../queries', () => ({
  useCreateTreasuredSubject: vi.fn(),
  useUpdateTreasuredSubject: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';

function makeMutationMock() {
  const createMutate = vi.fn();
  const updateMutate = vi.fn();
  vi.mocked(queries.useCreateTreasuredSubject).mockReturnValue({
    mutate: createMutate,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useUpdateTreasuredSubject).mockReturnValue({
    mutate: updateMutate,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return { createMutate, updateMutate };
}

const defaultProps = {
  open: true,
  onOpenChange: vi.fn(),
  tenureId: 1,
};

describe('TreasuredSubjectFormDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the create form with kind and label fields', () => {
    makeMutationMock();
    renderWithProviders(<TreasuredSubjectFormDialog {...defaultProps} />);

    expect(screen.getByText('Kind')).toBeInTheDocument();
    expect(screen.getByLabelText(/label/i)).toBeInTheDocument();
  });

  it('requires a label before submitting', async () => {
    const { createMutate } = makeMutationMock();
    renderWithProviders(<TreasuredSubjectFormDialog {...defaultProps} />);

    await userEvent.click(screen.getByRole('button', { name: /save|flag it/i }));

    expect(createMutate).not.toHaveBeenCalled();
    expect(screen.getByText(/a label is required/i)).toBeInTheDocument();
  });

  it('does not show the tenure picker for private or public visibility', () => {
    makeMutationMock();
    renderWithProviders(<TreasuredSubjectFormDialog {...defaultProps} />);

    expect(screen.queryByText('Shared with')).not.toBeInTheDocument();
  });

  it('shows the tenure picker for "specific characters" and submits the chosen tenures', async () => {
    const { createMutate } = makeMutationMock();
    renderWithProviders(<TreasuredSubjectFormDialog {...defaultProps} />);

    const selects = screen.getAllByTestId('mock-select');
    // Second select is "visibility"
    await userEvent.selectOptions(selects[1], 'characters');

    expect(screen.getByText('Shared with')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'add-tenure' }));

    await userEvent.type(screen.getByLabelText(/label/i), 'Captain Elara');
    await userEvent.click(screen.getByRole('button', { name: /save|flag it/i }));

    await waitFor(() => {
      expect(createMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          visibility_mode: 'characters',
          visible_to_tenures: [7],
        }),
        expect.any(Object)
      );
    });
  });

  it('prefills fields in edit mode', () => {
    makeMutationMock();
    const existing: TreasuredSubject = {
      id: 9,
      owner: 1,
      subject_kind: 'custom',
      subject_label: 'The old windmill',
      detail: 'A childhood haunt',
      visibility_mode: 'private',
      visible_to_tenures: [],
      visible_to_groups: [],
      excluded_tenures: [],
      created_at: '2026-01-01T00:00:00Z',
    };
    renderWithProviders(<TreasuredSubjectFormDialog {...defaultProps} subject={existing} />);

    expect(screen.getByDisplayValue('The old windmill')).toBeInTheDocument();
  });
});
