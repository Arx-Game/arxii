/**
 * PlayerBoundaryFormDialog tests (#1771) — the player content-boundary
 * authoring form. HARD_LINE requires a theme and is always private;
 * ADVISORY allows no theme and optional sharing.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { PlayerBoundaryFormDialog } from '../components/PlayerBoundaryFormDialog';
import type { PlayerBoundary } from '../types';

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

vi.mock('../queries', () => ({
  useContentThemes: vi.fn(),
  useCreatePlayerBoundary: vi.fn(),
  useUpdatePlayerBoundary: vi.fn(),
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
        onClick={() => onChange([...value, { value: 42, label: 'Test Tenure' }])}
      >
        add-tenure
      </button>
    </div>
  ),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';

function makeMutationMock() {
  const mutate = vi.fn();
  vi.mocked(queries.useCreatePlayerBoundary).mockReturnValue({
    mutate,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useUpdatePlayerBoundary).mockReturnValue({
    mutate: vi.fn(),
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return mutate;
}

const mockThemes = [
  {
    id: 1,
    key: 'child-endangerment',
    name: 'Child endangerment',
    description: '',
    display_order: 1,
    is_active: true,
  },
  {
    id: 2,
    key: 'animal-harm',
    name: 'Animal harm',
    description: '',
    display_order: 2,
    is_active: true,
  },
];

function setupMocks() {
  vi.mocked(queries.useContentThemes).mockReturnValue({
    data: { count: 2, results: mockThemes },
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return makeMutationMock();
}

const defaultProps = {
  open: true,
  onOpenChange: vi.fn(),
};

describe('PlayerBoundaryFormDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the create form with kind and detail fields', () => {
    setupMocks();
    renderWithProviders(<PlayerBoundaryFormDialog {...defaultProps} />);

    expect(screen.getByText('Kind')).toBeInTheDocument();
    expect(screen.getByLabelText(/detail/i)).toBeInTheDocument();
  });

  it('requires a theme when kind is hard_line', async () => {
    const mutate = setupMocks();
    renderWithProviders(<PlayerBoundaryFormDialog {...defaultProps} />);

    const selects = screen.getAllByTestId('mock-select');
    // First select is "kind"
    await userEvent.selectOptions(selects[0], 'hard_line');

    await userEvent.click(screen.getByRole('button', { name: /save|create/i }));

    // No theme chosen yet -> should not submit
    expect(mutate).not.toHaveBeenCalled();
    expect(screen.getByText(/theme is required/i)).toBeInTheDocument();
  });

  it('forces visibility to private and disables the visibility select for hard_line', async () => {
    setupMocks();
    renderWithProviders(<PlayerBoundaryFormDialog {...defaultProps} />);

    const selects = screen.getAllByTestId('mock-select');
    await userEvent.selectOptions(selects[0], 'hard_line');

    await waitFor(() => {
      const visibilitySelect = screen.getAllByTestId('mock-select')[2];
      expect(visibilitySelect).toBeDisabled();
      expect(visibilitySelect).toHaveValue('private');
    });
  });

  it('submits a hard_line boundary with theme + forced private visibility', async () => {
    const mutate = setupMocks();
    renderWithProviders(<PlayerBoundaryFormDialog {...defaultProps} />);

    const selects = screen.getAllByTestId('mock-select');
    await userEvent.selectOptions(selects[0], 'hard_line');
    await userEvent.selectOptions(screen.getAllByTestId('mock-select')[1], '1');
    await userEvent.type(screen.getByLabelText(/detail/i), 'No content involving harm to kids.');

    await userEvent.click(screen.getByRole('button', { name: /save|create/i }));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: 'hard_line',
          theme: 1,
          detail: 'No content involving harm to kids.',
          visibility_mode: 'private',
        }),
        expect.any(Object)
      );
    });
  });

  it('allows an advisory with no theme and public sharing', async () => {
    const mutate = setupMocks();
    renderWithProviders(<PlayerBoundaryFormDialog {...defaultProps} />);

    const selects = screen.getAllByTestId('mock-select');
    await userEvent.selectOptions(selects[0], 'advisory');
    await userEvent.type(screen.getByLabelText(/detail/i), 'Prefer to fade to black on gore.');

    await userEvent.click(screen.getByRole('button', { name: /save|create/i }));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: 'advisory',
          detail: 'Prefer to fade to black on gore.',
        }),
        expect.any(Object)
      );
    });
  });

  it('shows the tenure picker for "specific characters" and submits the chosen tenures', async () => {
    const mutate = setupMocks();
    renderWithProviders(<PlayerBoundaryFormDialog {...defaultProps} />);

    const selects = screen.getAllByTestId('mock-select');
    await userEvent.selectOptions(selects[0], 'advisory');
    await userEvent.selectOptions(screen.getAllByTestId('mock-select')[2], 'characters');

    expect(screen.getByText('Shared with')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'add-tenure' }));
    await userEvent.type(screen.getByLabelText(/detail/i), 'Shared only with allies.');

    await userEvent.click(screen.getByRole('button', { name: /save|create/i }));

    await waitFor(() => {
      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({
          visibility_mode: 'characters',
          visible_to_tenures: [42],
        }),
        expect.any(Object)
      );
    });
  });

  it('does not show the tenure picker for private or public visibility', async () => {
    setupMocks();
    renderWithProviders(<PlayerBoundaryFormDialog {...defaultProps} />);

    expect(screen.queryByText('Shared with')).not.toBeInTheDocument();

    const selects = screen.getAllByTestId('mock-select');
    await userEvent.selectOptions(selects[0], 'advisory');
    await userEvent.selectOptions(screen.getAllByTestId('mock-select')[2], 'public');

    expect(screen.queryByText('Shared with')).not.toBeInTheDocument();
  });

  it('prefills fields in edit mode', () => {
    setupMocks();
    const existing: PlayerBoundary = {
      id: 5,
      owner: 1,
      kind: 'advisory',
      theme: 2,
      detail: 'Existing detail text',
      visibility_mode: 'public',
      visible_to_tenures: [],
      visible_to_groups: [],
      excluded_tenures: [],
      created_at: '2026-01-01T00:00:00Z',
    };
    renderWithProviders(<PlayerBoundaryFormDialog {...defaultProps} boundary={existing} />);

    expect(screen.getByDisplayValue('Existing detail text')).toBeInTheDocument();
  });
});
