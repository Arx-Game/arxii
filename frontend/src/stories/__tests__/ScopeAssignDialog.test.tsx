/**
 * ScopeAssignDialog Tests — Task E4
 *
 * Covers:
 *  - offers scope choices character / group / global (NOT unassigned)
 *  - conditional target input: character → CharacterSheet id input;
 *    group → GM table picker; global → no target input
 *  - submit is blocked (button disabled) until the scope-appropriate target
 *    is provided — client-side mirror of the server combo invariant
 *  - on submit calls useAssignStory().mutate with
 *    { storyId, scope, character_sheet? | gm_table? } carrying ONLY the
 *    appropriate target for the chosen scope
 *  - a 400 (e.g. the "already assigned" message under key `scope`, or a combo
 *    error) surfaces INLINE (visible text, not toast-only) — mirrors
 *    PromoteMaturityButton's DRF-error mechanism
 *  - on success: dialog closes (relies on hook invalidation) and a success
 *    toast fires
 *
 * Mirrors the BeatFormDialog / PromoteMaturityButton harness: mock
 * `../queries` so the assign hook returns a controllable mock mutation, mock
 * `sonner`, and drive success/error via the mutation callbacks.
 */

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ScopeAssignDialog } from '../components/ScopeAssignDialog';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useAssignStory: vi.fn(),
}));

vi.mock('@/tables/queries', () => ({
  useTables: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';
import * as tablesQueries from '@/tables/queries';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeAssignMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.useAssignStory).mockReturnValue({
    mutate: mutateMock,
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    status: 'idle',
    reset: vi.fn(),
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return mutateMock;
}

function mockTables() {
  vi.mocked(tablesQueries.useTables).mockReturnValue({
    data: {
      count: 2,
      next: null,
      previous: null,
      results: [
        { id: 11, name: 'Table Alpha' },
        { id: 22, name: 'Table Beta' },
      ],
    },
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof tablesQueries.useTables>);
}

function setup() {
  const mutateMock = makeAssignMock();
  mockTables();
  return mutateMock;
}

// Opens the dialog via its trigger button.
async function openDialog(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /assign scope/i }));
  await waitFor(() => {
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ScopeAssignDialog — Task E4', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('offers scope choices character / group / global (NOT unassigned)', async () => {
    const user = userEvent.setup();
    setup();
    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    expect(within(group).getByRole('radio', { name: /character/i })).toBeInTheDocument();
    expect(within(group).getByRole('radio', { name: /group/i })).toBeInTheDocument();
    expect(within(group).getByRole('radio', { name: /global/i })).toBeInTheDocument();
    expect(within(group).queryByRole('radio', { name: /unassigned/i })).not.toBeInTheDocument();
  });

  it('shows a CharacterSheet id input only when scope is character', async () => {
    const user = userEvent.setup();
    setup();
    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    await user.click(within(group).getByRole('radio', { name: /character/i }));

    expect(screen.getByLabelText(/character sheet/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/gm table/i)).not.toBeInTheDocument();
  });

  it('shows a GM table picker only when scope is group', async () => {
    const user = userEvent.setup();
    setup();
    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    await user.click(within(group).getByRole('radio', { name: /group/i }));

    const tableSelect = screen.getByLabelText(/gm table/i);
    expect(tableSelect).toBeInTheDocument();
    expect(within(tableSelect).getByRole('option', { name: /table alpha/i })).toBeInTheDocument();
    expect(within(tableSelect).getByRole('option', { name: /table beta/i })).toBeInTheDocument();
    expect(screen.queryByLabelText(/character sheet/i)).not.toBeInTheDocument();
  });

  it('shows no target input when scope is global', async () => {
    const user = userEvent.setup();
    setup();
    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    await user.click(within(group).getByRole('radio', { name: /global/i }));

    expect(screen.queryByLabelText(/character sheet/i)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/gm table/i)).not.toBeInTheDocument();
  });

  it('blocks submit until the character target is provided', async () => {
    const user = userEvent.setup();
    setup();
    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    await user.click(within(group).getByRole('radio', { name: /character/i }));

    const submit = screen.getByRole('button', { name: /^assign$/i });
    expect(submit).toBeDisabled();

    await user.type(screen.getByLabelText(/character sheet/i), '7');
    expect(submit).toBeEnabled();
  });

  it('blocks submit until a GM table is selected', async () => {
    const user = userEvent.setup();
    setup();
    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    await user.click(within(group).getByRole('radio', { name: /group/i }));

    const submit = screen.getByRole('button', { name: /^assign$/i });
    expect(submit).toBeDisabled();

    await user.selectOptions(screen.getByLabelText(/gm table/i), '22');
    expect(submit).toBeEnabled();
  });

  it('allows submit immediately for global (no target needed)', async () => {
    const user = userEvent.setup();
    setup();
    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    await user.click(within(group).getByRole('radio', { name: /global/i }));

    expect(screen.getByRole('button', { name: /^assign$/i })).toBeEnabled();
  });

  it('submits character scope with ONLY character_sheet', async () => {
    const user = userEvent.setup();
    const mutateMock = setup();
    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    await user.click(within(group).getByRole('radio', { name: /character/i }));
    await user.type(screen.getByLabelText(/character sheet/i), '7');

    await user.click(screen.getByRole('button', { name: /^assign$/i }));

    await waitFor(() => {
      expect(mutateMock).toHaveBeenCalledWith(
        { storyId: 3, scope: 'character', character_sheet: 7 },
        expect.any(Object)
      );
    });
    const [[payload]] = mutateMock.mock.calls;
    expect(payload).not.toHaveProperty('gm_table');
  });

  it('submits group scope with ONLY gm_table', async () => {
    const user = userEvent.setup();
    const mutateMock = setup();
    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    await user.click(within(group).getByRole('radio', { name: /group/i }));
    await user.selectOptions(screen.getByLabelText(/gm table/i), '22');

    await user.click(screen.getByRole('button', { name: /^assign$/i }));

    await waitFor(() => {
      expect(mutateMock).toHaveBeenCalledWith(
        { storyId: 3, scope: 'group', gm_table: 22 },
        expect.any(Object)
      );
    });
    const [[payload]] = mutateMock.mock.calls;
    expect(payload).not.toHaveProperty('character_sheet');
  });

  it('submits global scope with neither target', async () => {
    const user = userEvent.setup();
    const mutateMock = setup();
    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    await user.click(within(group).getByRole('radio', { name: /global/i }));

    await user.click(screen.getByRole('button', { name: /^assign$/i }));

    await waitFor(() => {
      expect(mutateMock).toHaveBeenCalledWith({ storyId: 3, scope: 'global' }, expect.any(Object));
    });
    const [[payload]] = mutateMock.mock.calls;
    expect(payload).not.toHaveProperty('character_sheet');
    expect(payload).not.toHaveProperty('gm_table');
  });

  it('surfaces a 400 { scope: "already assigned" } error INLINE', async () => {
    const user = userEvent.setup();
    const mutateMock = setup();

    const alreadyMsg = 'This story is already assigned to a scope and cannot be re-assigned.';
    const mockErrorResponse = {
      json: () => Promise.resolve({ scope: alreadyMsg }),
    };
    mutateMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onError?: (err: unknown) => void };
      cb.onError?.({ response: mockErrorResponse });
    });

    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    await user.click(within(group).getByRole('radio', { name: /global/i }));
    await user.click(screen.getByRole('button', { name: /^assign$/i }));

    await waitFor(() => {
      expect(screen.getByText(alreadyMsg)).toBeInTheDocument();
    });
    // Dialog stays open so the user can see the error.
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('surfaces a 400 combo error (non_field_errors) INLINE', async () => {
    const user = userEvent.setup();
    const mutateMock = setup();

    const comboMsg = 'character scope requires character_sheet and forbids gm_table.';
    const mockErrorResponse = {
      json: () => Promise.resolve({ non_field_errors: [comboMsg] }),
    };
    mutateMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onError?: (err: unknown) => void };
      cb.onError?.({ response: mockErrorResponse });
    });

    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    await user.click(within(group).getByRole('radio', { name: /global/i }));
    await user.click(screen.getByRole('button', { name: /^assign$/i }));

    await waitFor(() => {
      expect(screen.getByText(comboMsg)).toBeInTheDocument();
    });
  });

  it('closes and toasts on success (relies on invalidation)', async () => {
    const user = userEvent.setup();
    const mutateMock = setup();

    mutateMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 3, scope: 'global' });
    });

    renderWithProviders(<ScopeAssignDialog storyId={3} />);
    await openDialog(user);

    const group = screen.getByTestId('scope-assign-scope-group');
    await user.click(within(group).getByRole('radio', { name: /global/i }));
    await user.click(screen.getByRole('button', { name: /^assign$/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    });
  });
});
