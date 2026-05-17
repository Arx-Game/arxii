/**
 * GMNotesPanel Tests — Task E5
 *
 * Surfaces the backbone's story-scoped append-only StoryNote ledger as the
 * "viewable list for other GMs with timestamps" from the design. Read-only
 * list + append form; no edit/delete (the API is append-only).
 *
 * Covers:
 *  - given storyId, renders the timestamped notes list from useStoryNotes
 *    (each row shows the note body, its created_at formatted, and the
 *    author_account the schema provides)
 *  - loading state while pending; empty state when there are no notes
 *  - append form (textarea + submit button); submitting a non-empty body
 *    calls useCreateStoryNote().mutate with { story: storyId, body }
 *  - empty / whitespace body does not submit (button disabled / guarded)
 *  - on success: clears the textarea, relies on hook invalidation (no manual
 *    refetch), success toast
 *  - on error: surfaces a minimal INLINE error (mirrors PromoteMaturityButton's
 *    DRF-error pattern — err.response.json() → body / non_field_errors / detail)
 *
 * Mirrors the PromoteMaturityButton / ScopeAssignDialog harness: mock
 * `../queries` so useStoryNotes returns controllable data/loading/empty and
 * useCreateStoryNote a controllable mock mutation; mock `sonner`.
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { GMNotesPanel } from '../components/GMNotesPanel';
import type { StoryNote } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useStoryNotes: vi.fn(),
  useCreateStoryNote: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const NOTES: StoryNote[] = [
  {
    id: 2,
    story: 3,
    author_account: 42,
    body: 'Second note — newest first per API ordering.',
    created_at: '2026-05-15T12:00:00Z',
  },
  {
    id: 1,
    story: 3,
    author_account: null,
    body: 'First note about the villain motivation.',
    created_at: '2026-05-14T09:30:00Z',
  },
];

function mockStoryNotes(state: 'loading' | 'empty' | 'list', notes: StoryNote[] = NOTES) {
  if (state === 'loading') {
    vi.mocked(queries.useStoryNotes).mockReturnValue({
      data: undefined,
      isLoading: true,
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } as any);
    return;
  }
  vi.mocked(queries.useStoryNotes).mockReturnValue({
    data: {
      count: state === 'empty' ? 0 : notes.length,
      next: null,
      previous: null,
      results: state === 'empty' ? [] : notes,
    },
    isLoading: false,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
}

function makeCreateMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.useCreateStoryNote).mockReturnValue({
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('GMNotesPanel — Task E5', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the timestamped notes list with body, created_at, and author', () => {
    mockStoryNotes('list');
    makeCreateMock();

    renderWithProviders(<GMNotesPanel storyId={3} />);

    expect(screen.getByText('Second note — newest first per API ordering.')).toBeInTheDocument();
    expect(screen.getByText('First note about the villain motivation.')).toBeInTheDocument();

    // author_account surfaced (numeric id when present)
    expect(screen.getByText(/42/)).toBeInTheDocument();

    // created_at rendered (formatted relative time — at minimum a time element
    // carrying the ISO timestamp via dateTime attr)
    const times = screen.getAllByTestId('gm-note-time');
    expect(times).toHaveLength(2);
    expect(times[0]).toHaveAttribute('datetime', '2026-05-15T12:00:00Z');
  });

  it('shows a loading state while pending', () => {
    mockStoryNotes('loading');
    makeCreateMock();

    renderWithProviders(<GMNotesPanel storyId={3} />);

    expect(screen.getByTestId('gm-notes-loading')).toBeInTheDocument();
  });

  it('shows an empty state when there are no notes', () => {
    mockStoryNotes('empty');
    makeCreateMock();

    renderWithProviders(<GMNotesPanel storyId={3} />);

    expect(screen.getByTestId('gm-notes-empty')).toBeInTheDocument();
  });

  it('renders an append form with a textarea and submit button', () => {
    mockStoryNotes('list');
    makeCreateMock();

    renderWithProviders(<GMNotesPanel storyId={3} />);

    expect(screen.getByTestId('gm-note-body')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /add note/i })).toBeInTheDocument();
  });

  it('does not submit an empty body (submit guarded / disabled)', async () => {
    const user = userEvent.setup();
    mockStoryNotes('list');
    const mutateMock = makeCreateMock();

    renderWithProviders(<GMNotesPanel storyId={3} />);

    const submit = screen.getByRole('button', { name: /add note/i });
    expect(submit).toBeDisabled();

    await user.click(submit);
    expect(mutateMock).not.toHaveBeenCalled();
  });

  it('does not submit a whitespace-only body', async () => {
    const user = userEvent.setup();
    mockStoryNotes('list');
    const mutateMock = makeCreateMock();

    renderWithProviders(<GMNotesPanel storyId={3} />);

    await user.type(screen.getByTestId('gm-note-body'), '   ');

    const submit = screen.getByRole('button', { name: /add note/i });
    expect(submit).toBeDisabled();
    await user.click(submit);
    expect(mutateMock).not.toHaveBeenCalled();
  });

  it('submits a non-empty body with { story, body }', async () => {
    const user = userEvent.setup();
    mockStoryNotes('list');
    const mutateMock = makeCreateMock();

    renderWithProviders(<GMNotesPanel storyId={3} />);

    await user.type(screen.getByTestId('gm-note-body'), 'Remember to foreshadow the betrayal.');
    await user.click(screen.getByRole('button', { name: /add note/i }));

    await waitFor(() => {
      expect(mutateMock).toHaveBeenCalledWith(
        { story: 3, body: 'Remember to foreshadow the betrayal.' },
        expect.any(Object)
      );
    });
  });

  it('clears the textarea and toasts on success (relies on invalidation)', async () => {
    const user = userEvent.setup();
    mockStoryNotes('list');
    const mutateMock = makeCreateMock();

    mutateMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: (data: unknown) => void };
      cb.onSuccess?.({ id: 99, story: 3, author_account: 42, body: 'x', created_at: 'now' });
    });

    renderWithProviders(<GMNotesPanel storyId={3} />);

    const textarea = screen.getByTestId('gm-note-body') as HTMLTextAreaElement;
    await user.type(textarea, 'A new authorial note.');
    await user.click(screen.getByRole('button', { name: /add note/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(textarea.value).toBe('');
    });
  });

  it('surfaces a 400 { body: "<message>" } error INLINE', async () => {
    const user = userEvent.setup();
    mockStoryNotes('list');
    const mutateMock = makeCreateMock();

    const fieldMsg = 'This field may not be blank.';
    const mockErrorResponse = {
      json: () => Promise.resolve({ body: [fieldMsg] }),
    };
    mutateMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onError?: (err: unknown) => void };
      cb.onError?.({ response: mockErrorResponse });
    });

    renderWithProviders(<GMNotesPanel storyId={3} />);

    await user.type(screen.getByTestId('gm-note-body'), 'Some text the server rejects.');
    await user.click(screen.getByRole('button', { name: /add note/i }));

    await waitFor(() => {
      expect(screen.getByText(fieldMsg)).toBeInTheDocument();
    });
  });

  it('surfaces a 400 non_field_errors / detail error INLINE', async () => {
    const user = userEvent.setup();
    mockStoryNotes('list');
    const mutateMock = makeCreateMock();

    const detailMsg = 'You do not have permission to add notes to this story.';
    const mockErrorResponse = {
      json: () => Promise.resolve({ detail: detailMsg }),
    };
    mutateMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onError?: (err: unknown) => void };
      cb.onError?.({ response: mockErrorResponse });
    });

    renderWithProviders(<GMNotesPanel storyId={3} />);

    await user.type(screen.getByTestId('gm-note-body'), 'Attempted note.');
    await user.click(screen.getByRole('button', { name: /add note/i }));

    await waitFor(() => {
      expect(screen.getByText(detailMsg)).toBeInTheDocument();
    });
  });
});
