/**
 * JournalComposerDialog tests (#2160).
 *
 * Covers the create flow: the composer posts the exact payload the backend
 * expects (title/body/is_public/tags) — including tags pre-seeded via
 * `initialTags`, which Task 4's card action relies on — via a mocked
 * `useCreateJournalEntry` mutation. No real network/api module involved.
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi, beforeEach } from 'vitest';

import { JournalComposerDialog } from '../components/JournalComposerDialog';

vi.mock('../queries', () => ({
  useCreateJournalEntry: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

function makeCreateMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.useCreateJournalEntry).mockReturnValue({
    mutate: mutateMock,
    isPending: false,
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

    await user.type(screen.getByLabelText(/title/i), 'A Quiet Evening');
    await user.type(screen.getByLabelText('Entry'), 'The rain fell softly on the manor roof.');

    // Add one more tag via the chip input (typed then Enter — not comma-split).
    const tagInput = screen.getByLabelText(/tags/i);
    await user.type(tagInput, 'rain{Enter}');

    await user.click(screen.getByRole('button', { name: /post entry/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      {
        title: 'A Quiet Evening',
        body: 'The rain fell softly on the manor roof.',
        is_public: false,
        tags: ['grief', 'a, b', 'rain'],
      },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) })
    );
  });

  it('toggling public flips is_public in the submitted payload', async () => {
    const user = userEvent.setup();
    const mutateMock = makeCreateMock();

    render(<JournalComposerDialog open onClose={vi.fn()} />);

    await user.type(screen.getByLabelText(/title/i), 'Public Thoughts');
    await user.type(screen.getByLabelText('Entry'), 'Body text here.');
    await user.click(screen.getByLabelText(/public/i));

    await user.click(screen.getByRole('button', { name: /post entry/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({ is_public: true }),
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

    await user.type(screen.getByLabelText(/title/i), 'Title');
    await user.type(screen.getByLabelText('Entry'), 'Body');
    await user.click(screen.getByRole('button', { name: /post entry/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Journal entry recorded.');
    });
    expect(onClose).toHaveBeenCalled();
  });

  it('disables submit until both title and body are filled', async () => {
    const user = userEvent.setup();
    makeCreateMock();
    render(<JournalComposerDialog open onClose={vi.fn()} />);

    expect(screen.getByRole('button', { name: /post entry/i })).toBeDisabled();

    await user.type(screen.getByLabelText(/title/i), 'Title only');
    expect(screen.getByRole('button', { name: /post entry/i })).toBeDisabled();

    await user.type(screen.getByLabelText('Entry'), 'Now with body text.');
    expect(screen.getByRole('button', { name: /post entry/i })).not.toBeDisabled();
  });
});
