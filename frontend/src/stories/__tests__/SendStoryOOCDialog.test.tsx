/**
 * SendStoryOOCDialog Tests
 *
 * Covers:
 *  - Dialog opens/closes on trigger
 *  - Body required — submit disabled when empty
 *  - Submit happy path → mutation called with right payload, dialog closes, toast shown
 *  - Validation error shown inline
 *  - 403 closes dialog and shows permission toast
 *  - Cancel closes dialog
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { SendStoryOOCDialog } from '../components/SendStoryOOCDialog';
import type { Story } from '../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('../queries', () => ({
  useSendStoryOOC: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockStory: Story = {
  id: 42,
  title: 'The Dragon Awakens',
  description: 'A story about dragons.',
  scope: 'group',
  status: 'active',
  privacy: 'invite_only',
  character_sheet: 0,
  primary_table: 7,
  active_gms: [],
  owners: [],
  trust_requirements: '',
  chapters_count: 0,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-04-19T00:00:00Z',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSendMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.useSendStoryOOC).mockReturnValue({
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
  } as unknown as ReturnType<typeof queries.useSendStoryOOC>);
  return mutateMock;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('SendStoryOOCDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Send OOC notice button', () => {
    makeSendMock();
    renderWithProviders(<SendStoryOOCDialog story={mockStory} />);
    expect(screen.getByRole('button', { name: /send ooc notice/i })).toBeInTheDocument();
  });

  it('opens dialog when button is clicked', async () => {
    const user = userEvent.setup();
    makeSendMock();
    renderWithProviders(<SendStoryOOCDialog story={mockStory} />);

    await user.click(screen.getByRole('button', { name: /send ooc notice/i }));

    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/The Dragon Awakens/)).toBeInTheDocument();
  });

  it('disables submit when body is empty', async () => {
    const user = userEvent.setup();
    makeSendMock();
    renderWithProviders(<SendStoryOOCDialog story={mockStory} />);

    await user.click(screen.getByRole('button', { name: /send ooc notice/i }));

    const submitButton = screen.getByRole('button', { name: /send notice/i });
    expect(submitButton).toBeDisabled();
  });

  it('enables submit when body has content', async () => {
    const user = userEvent.setup();
    makeSendMock();
    renderWithProviders(<SendStoryOOCDialog story={mockStory} />);

    await user.click(screen.getByRole('button', { name: /send ooc notice/i }));
    await user.type(screen.getByTestId('ooc-body-input'), 'Session postponed to next week.');

    const submitButton = screen.getByRole('button', { name: /send notice/i });
    expect(submitButton).not.toBeDisabled();
  });

  it('calls mutation with correct payload on submit', async () => {
    const user = userEvent.setup();
    const mutateMock = makeSendMock();

    mutateMock.mockImplementation((_vars: unknown, callbacks: { onSuccess?: () => void }) => {
      callbacks?.onSuccess?.();
    });

    renderWithProviders(<SendStoryOOCDialog story={mockStory} />);

    await user.click(screen.getByRole('button', { name: /send ooc notice/i }));
    await user.type(screen.getByTestId('ooc-body-input'), 'Session postponed.');
    await user.type(screen.getByTestId('ooc-note-input'), 'Internal note for staff.');
    await user.click(screen.getByRole('button', { name: /send notice/i }));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({
        storyId: 42,
        body: 'Session postponed.',
        ooc_note: 'Internal note for staff.',
      }),
      expect.any(Object)
    );
  });

  it('closes dialog and shows success toast on happy path', async () => {
    const user = userEvent.setup();
    const mutateMock = makeSendMock();

    mutateMock.mockImplementation((_vars: unknown, callbacks: { onSuccess?: () => void }) => {
      callbacks?.onSuccess?.();
    });

    renderWithProviders(<SendStoryOOCDialog story={mockStory} />);

    await user.click(screen.getByRole('button', { name: /send ooc notice/i }));
    await user.type(screen.getByTestId('ooc-body-input'), 'Session tomorrow at 8pm.');
    await user.click(screen.getByRole('button', { name: /send notice/i }));

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('OOC notice sent to story participants');
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows inline validation error from DRF', async () => {
    const user = userEvent.setup();
    const mutateMock = makeSendMock();

    const mockErrorResponse = {
      json: () =>
        Promise.resolve({ body: ['Ensure this field has no more than 2000 characters.'] }),
    };

    mutateMock.mockImplementation(
      (_vars: unknown, callbacks: { onError?: (err: unknown) => void }) => {
        callbacks?.onError?.({ response: mockErrorResponse });
      }
    );

    renderWithProviders(<SendStoryOOCDialog story={mockStory} />);
    await user.click(screen.getByRole('button', { name: /send ooc notice/i }));
    await user.type(screen.getByTestId('ooc-body-input'), 'Too long message.');
    await user.click(screen.getByRole('button', { name: /send notice/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/ensure this field has no more than 2000 characters/i)
      ).toBeInTheDocument();
    });
    // Dialog stays open
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });

  it('closes dialog and shows permission toast on 403', async () => {
    const user = userEvent.setup();
    const mutateMock = makeSendMock();

    mutateMock.mockImplementation(
      (_vars: unknown, callbacks: { onError?: (err: unknown) => void }) => {
        callbacks?.onError?.({ status: 403 });
      }
    );

    renderWithProviders(<SendStoryOOCDialog story={mockStory} />);
    await user.click(screen.getByRole('button', { name: /send ooc notice/i }));
    await user.type(screen.getByTestId('ooc-body-input'), 'Unauthorized notice.');
    await user.click(screen.getByRole('button', { name: /send notice/i }));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith(
        'Permission denied. Only Lead GMs and staff can send OOC notices.'
      );
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('closes dialog on Cancel button click', async () => {
    const user = userEvent.setup();
    makeSendMock();
    renderWithProviders(<SendStoryOOCDialog story={mockStory} />);

    await user.click(screen.getByRole('button', { name: /send ooc notice/i }));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /cancel/i }));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
