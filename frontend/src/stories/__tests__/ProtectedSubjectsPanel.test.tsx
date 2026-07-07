/**
 * ProtectedSubjectsPanel tests (#2001 Task 8).
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { ProtectedSubjectsPanel } from '../components/ProtectedSubjectsPanel';
import type { ProtectedSubject } from '../types';

vi.mock('../components/ProtectedSubjectFormDialog', () => ({
  ProtectedSubjectFormDialog: () => <button>Add Protected Subject</button>,
}));

vi.mock('../queries', () => ({
  useProtectedSubjects: vi.fn(),
  useDeactivateProtectedSubject: vi.fn(),
  useUpdateProtectedSubject: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

const activeSubject: ProtectedSubject = {
  id: 1,
  story: 7,
  subject_kind: 'npc_fate',
  subject_sheet: 42,
  subject_item: null,
  subject_society: null,
  subject_organization: null,
  subject_label: '',
  is_active: true,
  notes: 'Load-bearing NPC',
  created_at: '2026-01-01T00:00:00Z',
};

const inactiveSubject: ProtectedSubject = {
  ...activeSubject,
  id: 2,
  is_active: false,
  subject_kind: 'custom',
  subject_sheet: null,
  subject_label: 'The old windmill',
};

function mockList(results: ProtectedSubject[], isLoading = false) {
  vi.mocked(queries.useProtectedSubjects).mockReturnValue({
    data: { count: results.length, next: null, previous: null, results },
    isLoading,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function makeActionMocks() {
  const deactivate = vi.fn();
  const update = vi.fn();
  vi.mocked(queries.useDeactivateProtectedSubject).mockReturnValue({
    mutate: deactivate,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  vi.mocked(queries.useUpdateProtectedSubject).mockReturnValue({
    mutate: update,
    isPending: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return { deactivate, update };
}

describe('ProtectedSubjectsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows an empty state with no protected subjects', () => {
    mockList([]);
    makeActionMocks();
    renderWithProviders(<ProtectedSubjectsPanel storyId={7} />);

    expect(screen.getByTestId('protected-subjects-empty')).toBeInTheDocument();
  });

  it('renders active and deactivated rows with the right badges', () => {
    mockList([activeSubject, inactiveSubject]);
    makeActionMocks();
    renderWithProviders(<ProtectedSubjectsPanel storyId={7} />);

    const rows = screen.getAllByTestId('protected-subject-row');
    expect(rows).toHaveLength(2);
    expect(screen.getByText('Deactivated')).toBeInTheDocument();
    expect(screen.getByText('Character sheet #42')).toBeInTheDocument();
    expect(screen.getByText('The old windmill')).toBeInTheDocument();
  });

  it('deactivates an active subject', async () => {
    const user = userEvent.setup();
    mockList([activeSubject]);
    const { deactivate } = makeActionMocks();
    deactivate.mockImplementation((_id, callbacks) => callbacks?.onSuccess?.());

    renderWithProviders(<ProtectedSubjectsPanel storyId={7} />);
    await user.click(screen.getByTestId('deactivate-protected-subject-btn'));

    expect(deactivate).toHaveBeenCalledWith(1, expect.any(Object));
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Protected subject deactivated');
    });
  });

  it('reactivates a deactivated subject', async () => {
    const user = userEvent.setup();
    mockList([inactiveSubject]);
    const { update } = makeActionMocks();
    update.mockImplementation((_vars, callbacks) => callbacks?.onSuccess?.());

    renderWithProviders(<ProtectedSubjectsPanel storyId={7} />);
    await user.click(screen.getByTestId('reactivate-protected-subject-btn'));

    expect(update).toHaveBeenCalledWith({ id: 2, body: { is_active: true } }, expect.any(Object));
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Protected subject reactivated');
    });
  });

  it('shows a loading skeleton while fetching', () => {
    mockList([], true);
    makeActionMocks();
    renderWithProviders(<ProtectedSubjectsPanel storyId={7} />);

    expect(screen.getByTestId('protected-subjects-loading')).toBeInTheDocument();
  });
});
