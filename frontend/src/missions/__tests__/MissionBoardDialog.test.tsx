/**
 * #3044 — MissionBoardDialog tests.
 *
 * Verifies the dialog lists postings from `useBoardPostings`, dispatches a
 * take with the right payload (`boardObjectId` scoped via `useTakeBoardPosting`,
 * `templateId` from the clicked row), and surfaces a taken-posting journal
 * link on success.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { useBoardPostings, useTakeBoardPosting } from '../queries';
import { MissionBoardDialog } from '../components/MissionBoardDialog';

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useBoardPostings: vi.fn(),
    useTakeBoardPosting: vi.fn(),
  };
});

const mockUseBoardPostings = vi.mocked(useBoardPostings);
const mockUseTakeBoardPosting = vi.mocked(useTakeBoardPosting);

function mockTake(mutate = vi.fn(), isPending = false) {
  mockUseTakeBoardPosting.mockReturnValue({
    mutate,
    isPending,
  } as unknown as ReturnType<typeof useTakeBoardPosting>);
  return mutate;
}

describe('MissionBoardDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('lists postings returned by useBoardPostings', () => {
    mockUseBoardPostings.mockReturnValue({
      isLoading: false,
      data: {
        count: 2,
        results: [
          { template_id: 1, name: 'Clear the Cellar', summary: 'Rats, probably.' },
          { template_id: 2, name: 'Deliver the Letter', summary: '' },
        ],
      },
    } as unknown as ReturnType<typeof useBoardPostings>);
    mockTake();

    renderWithProviders(
      <MissionBoardDialog
        boardObjectId={501}
        boardName="Notice Board"
        open
        onOpenChange={vi.fn()}
      />
    );

    expect(screen.getByText('Notice Board')).toBeInTheDocument();
    expect(screen.getByText('Clear the Cellar')).toBeInTheDocument();
    expect(screen.getByText('Rats, probably.')).toBeInTheDocument();
    expect(screen.getByText('Deliver the Letter')).toBeInTheDocument();
    expect(screen.getByTestId('take-posting-1')).toBeInTheDocument();
    expect(screen.getByTestId('take-posting-2')).toBeInTheDocument();
  });

  it('shows an empty-state message when there are no eligible postings', () => {
    mockUseBoardPostings.mockReturnValue({
      isLoading: false,
      data: { count: 0, results: [] },
    } as unknown as ReturnType<typeof useBoardPostings>);
    mockTake();

    renderWithProviders(
      <MissionBoardDialog
        boardObjectId={501}
        boardName="Notice Board"
        open
        onOpenChange={vi.fn()}
      />
    );

    expect(screen.getByText('No postings for you right now.')).toBeInTheDocument();
  });

  it('takes a posting with the right template id and shows a journal link on success', async () => {
    const user = userEvent.setup();
    mockUseBoardPostings.mockReturnValue({
      isLoading: false,
      data: {
        count: 1,
        results: [{ template_id: 9, name: 'Clear the Cellar', summary: '' }],
      },
    } as unknown as ReturnType<typeof useBoardPostings>);
    const mutate = vi.fn((_templateId: number, opts?: { onSuccess?: (r: unknown) => void }) => {
      opts?.onSuccess?.({ instance_id: 42, template_id: 9 });
    });
    mockTake(mutate);

    renderWithProviders(
      <MissionBoardDialog
        boardObjectId={501}
        boardName="Notice Board"
        open
        onOpenChange={vi.fn()}
      />
    );

    await user.click(screen.getByTestId('take-posting-9'));

    expect(mutate).toHaveBeenCalledWith(
      9,
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
    await waitFor(() => {
      expect(screen.getByTestId('board-take-journal-link')).toBeInTheDocument();
    });
  });
});
