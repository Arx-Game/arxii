/**
 * JournalComposerDialog tests (#2160, rebuilt for #3941).
 *
 * Covers the create flow: the composer posts the exact payload the backend
 * expects (title/body/is_public/tags/about) — including tags pre-seeded via
 * `initialTags`, which the card action relies on — via a mocked
 * `useCreateJournalEntry` mutation. No real network/api module involved.
 *
 * Since #3941 the dialog renders the same `JournalEntryFields` as the page's
 * desk, so which journal you are writing in is a pair of pills rather than a
 * switch, and white (public) is what you get unless you say otherwise.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../queries', () => ({
  useCreateJournalEntry: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/roster/usePersonaSearch', () => ({
  usePersonaSearch: () => ({ results: [], isFetching: false }),
}));

import { JournalComposerDialog } from '../components/JournalComposerDialog';
import * as queries from '../queries';
import { toast } from 'sonner';

function makeCreateMock(errorState?: { error: Error }) {
  const mutateMock = vi.fn();
  vi.mocked(queries.useCreateJournalEntry).mockReturnValue({
    mutate: mutateMock,
    isPending: false,
    isError: !!errorState,
    error: errorState?.error ?? null,
  } as unknown as ReturnType<typeof queries.useCreateJournalEntry>);
  return mutateMock;
}

describe('JournalComposerDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not render when closed', () => {
    makeCreateMock();
    render(<JournalComposerDialog open={false} onClose={vi.fn()} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('offers the two journals and no help text', () => {
    makeCreateMock();
    render(<JournalComposerDialog open onClose={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'White journal · Public' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(screen.getByRole('button', { name: 'Black journal · Private' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    expect(screen.queryByText(/visible only to you/i)).toBeNull();
    expect(screen.queryByText(/Read by anyone/)).toBeNull();
  });

  it('pre-seeds the tag chip list from initialTags', () => {
    makeCreateMock();
    render(
      <JournalComposerDialog open onClose={vi.fn()} initialTags={['grief', 'court intrigue']} />
    );

    const tagList = screen.getByTestId('journal-tag-list');
    expect(tagList).toHaveTextContent('grief');
    expect(tagList).toHaveTextContent('court intrigue');
  });

  it('posts the correct payload on submit, including pre-seeded tags — never comma-split', async () => {
    const user = userEvent.setup();
    const mutateMock = makeCreateMock();

    render(<JournalComposerDialog open onClose={vi.fn()} initialTags={['grief', 'a, b']} />);

    await user.type(screen.getByLabelText('Title'), 'A Quiet Evening');
    await user.type(screen.getByLabelText('Entry'), 'The rain fell softly on the manor roof.');

    // Add one more tag via the chip input (typed then Enter — not comma-split).
    await user.type(screen.getByLabelText('Tags'), 'rain{Enter}');

    await user.click(screen.getByRole('button', { name: /post entry/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      {
        title: 'A Quiet Evening',
        body: 'The rain fell softly on the manor roof.',
        is_public: true,
        tags: ['grief', 'a, b', 'rain'],
        about: null,
      },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) })
    );
  });

  it('choosing the black journal flips is_public in the submitted payload', async () => {
    const user = userEvent.setup();
    const mutateMock = makeCreateMock();

    render(<JournalComposerDialog open onClose={vi.fn()} />);

    await user.type(screen.getByLabelText('Title'), 'Private Thoughts');
    await user.type(screen.getByLabelText('Entry'), 'Body text here.');
    await user.click(screen.getByRole('button', { name: 'Black journal · Private' }));

    // Only a black entry is asked what becomes of it afterwards.
    expect(screen.getByLabelText('After your death')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /post entry/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({ is_public: false }),
      expect.any(Object)
    );
  });

  it('shows a success toast and closes on successful submit', async () => {
    const user = userEvent.setup();
    const mutateMock = makeCreateMock();
    const onClose = vi.fn();
    mutateMock.mockImplementation((_vars, callbacks) => {
      callbacks?.onSuccess?.();
    });

    render(<JournalComposerDialog open onClose={onClose} />);

    await user.type(screen.getByLabelText('Title'), 'Title');
    await user.type(screen.getByLabelText('Entry'), 'Body');
    await user.click(screen.getByRole('button', { name: /post entry/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Journal entry recorded.');
    });
    expect(onClose).toHaveBeenCalled();
  });

  it('renders a gate refusal reason inline (not just a toast) — #3412 T4', () => {
    makeCreateMock({
      error: new Error('You are captured; smuggle a message out to reach the world.'),
    });
    render(<JournalComposerDialog open onClose={vi.fn()} />);

    expect(screen.getByTestId('journal-composer-error')).toHaveTextContent(
      'You are captured; smuggle a message out to reach the world.'
    );
  });

  it('renders no inline error block when the mutation has not errored', () => {
    makeCreateMock();
    render(<JournalComposerDialog open onClose={vi.fn()} />);

    expect(screen.queryByTestId('journal-composer-error')).not.toBeInTheDocument();
  });

  it('disables submit until both title and body are filled', async () => {
    const user = userEvent.setup();
    makeCreateMock();
    render(<JournalComposerDialog open onClose={vi.fn()} />);

    expect(screen.getByRole('button', { name: /post entry/i })).toBeDisabled();

    await user.type(screen.getByLabelText('Title'), 'Title only');
    expect(screen.getByRole('button', { name: /post entry/i })).toBeDisabled();

    await user.type(screen.getByLabelText('Entry'), 'Now with body text.');
    expect(screen.getByRole('button', { name: /post entry/i })).not.toBeDisabled();
  });
});
