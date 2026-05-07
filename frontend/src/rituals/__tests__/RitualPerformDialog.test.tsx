/**
 * RitualPerformDialog tests
 *
 * Tests for the dialog shell that wraps RitualForm, validates required fields,
 * submits to the perform endpoint, and surfaces typed errors.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { RitualPerformDialog } from '../components/RitualPerformDialog';
import type { RitualWithSchema, PerformRitualResponse } from '../types';
import * as queries from '@/rituals/queries';

// ---------------------------------------------------------------------------
// Mock usePerformRitual
// ---------------------------------------------------------------------------

const mockMutate = vi.fn();
const mockReset = vi.fn();

function makeMutationIdle() {
  return {
    mutate: mockMutate,
    reset: mockReset,
    isPending: false,
    isSuccess: false,
    isIdle: true,
    isError: false,
    error: null,
    data: undefined,
    status: 'idle' as const,
  } as unknown as ReturnType<typeof queries.usePerformRitual>;
}

function makeMutationError(error: Error) {
  return {
    mutate: mockMutate,
    reset: mockReset,
    isPending: false,
    isSuccess: false,
    isIdle: false,
    isError: true,
    error,
    data: undefined,
    status: 'error' as const,
  } as unknown as ReturnType<typeof queries.usePerformRitual>;
}

vi.mock('@/rituals/queries');
vi.mocked(queries.usePerformRitual).mockReturnValue(makeMutationIdle());

// Mock domain field backing APIs (required by field components rendered via RitualForm)
vi.mock('@/events/queries', () => ({ searchPersonas: vi.fn() }));
vi.mock('@/scenes/queries', () => ({ fetchScenes: vi.fn() }));
vi.mock('@/evennia_replacements/api', () => ({ apiFetch: vi.fn() }));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const baseRitual: RitualWithSchema = {
  id: 1,
  name: 'Soul Tether',
  description: 'Binds a soul to this plane.',
  narrative_prose: 'The sineater reaches across the veil, fingers trailing mist.',
  input_schema: null,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any;

const ritualWithSchema: RitualWithSchema = {
  ...baseRitual,
  input_schema: {
    fields: [
      { name: 'target_name', label: 'Target Name', type: 'text', required: true },
      { name: 'notes', label: 'Notes', type: 'text', required: false },
    ],
  },
};

const defaultProps = {
  ritual: baseRitual,
  characterSheetId: 42,
  open: true,
  onOpenChange: vi.fn(),
  onSuccess: vi.fn(),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('RitualPerformDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(queries.usePerformRitual).mockReturnValue(makeMutationIdle());
  });

  // 1. Renders ritual name + description
  it('renders ritual name and description when open', () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualPerformDialog {...defaultProps} />
      </Wrapper>
    );

    expect(screen.getByText('Soul Tether')).toBeInTheDocument();
    expect(screen.getByText('Binds a soul to this plane.')).toBeInTheDocument();
  });

  // 2. Renders narrative_prose as a prose block
  it('renders narrative_prose as a distinct prose region', () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualPerformDialog {...defaultProps} />
      </Wrapper>
    );

    const prose = screen.getByTestId('ritual-narrative-prose');
    expect(prose).toBeInTheDocument();
    expect(prose).toHaveTextContent('The sineater reaches across the veil, fingers trailing mist.');
  });

  // 3. Renders form when input_schema is non-null
  it('renders form when input_schema is non-null', () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualPerformDialog {...defaultProps} ritual={ritualWithSchema} />
      </Wrapper>
    );

    expect(screen.getByText('Target Name')).toBeInTheDocument();
    expect(screen.getByText('Notes')).toBeInTheDocument();
  });

  // 4. Hides form when input_schema is null
  it('does not render form when input_schema is null', () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualPerformDialog {...defaultProps} ritual={baseRitual} />
      </Wrapper>
    );

    // No form fields
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    // Perform button still visible
    expect(screen.getByRole('button', { name: /perform/i })).toBeInTheDocument();
  });

  // 5. Perform button is disabled while required fields are empty
  it('disables Perform button when required fields are empty', () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualPerformDialog {...defaultProps} ritual={ritualWithSchema} />
      </Wrapper>
    );

    const performBtn = screen.getByRole('button', { name: /perform/i });
    expect(performBtn).toBeDisabled();
  });

  // 6. Perform button enables once all required fields are filled
  it('enables Perform button once all required fields are filled', async () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualPerformDialog {...defaultProps} ritual={ritualWithSchema} />
      </Wrapper>
    );

    const performBtn = screen.getByRole('button', { name: /perform/i });
    expect(performBtn).toBeDisabled();

    // Fill the required field
    const textInputs = screen.getAllByRole('textbox');
    await userEvent.type(textInputs[0], 'Alice');

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /perform/i })).not.toBeDisabled();
    });
  });

  // 7. Submit POSTs correct body
  it('calls mutate with correct body including ritual_id, character_sheet_id, and kwargs', async () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualPerformDialog {...defaultProps} ritual={ritualWithSchema} />
      </Wrapper>
    );

    // Fill required field to enable submit
    const textInputs = screen.getAllByRole('textbox');
    await userEvent.type(textInputs[0], 'Alice');

    const performBtn = await screen.findByRole('button', { name: /perform/i });
    await userEvent.click(performBtn);

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        ritual_id: 1,
        character_sheet_id: 42,
        kwargs: expect.objectContaining({ target_name: 'Alice' }),
      }),
      expect.any(Object)
    );
  });

  // 8. onSuccess fires + dialog closes on 200
  it('calls onSuccess and onOpenChange(false) on successful submission', async () => {
    const onSuccess = vi.fn();
    const onOpenChange = vi.fn();

    // Arrange mutate to immediately call its onSuccess callback
    const successResponse: PerformRitualResponse = {
      ritual_id: 1,
      execution_kind: 'SERVICE',
    };
    mockMutate.mockImplementation(
      (_body, callbacks: { onSuccess?: (r: PerformRitualResponse) => void }) => {
        callbacks?.onSuccess?.(successResponse);
      }
    );

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualPerformDialog
          {...defaultProps}
          ritual={baseRitual}
          onSuccess={onSuccess}
          onOpenChange={onOpenChange}
        />
      </Wrapper>
    );

    const performBtn = screen.getByRole('button', { name: /perform/i });
    await userEvent.click(performBtn);

    expect(onSuccess).toHaveBeenCalledWith(successResponse);
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  // 9. Typed error shows in dialog
  it('displays error message from thrown exception', () => {
    const error = new Error('Test error message from server');
    vi.mocked(queries.usePerformRitual).mockReturnValue(makeMutationError(error));

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualPerformDialog {...defaultProps} ritual={baseRitual} />
      </Wrapper>
    );

    expect(screen.getByText('Test error message from server')).toBeInTheDocument();
  });

  // 9b. Falls back to generic message when error has no detail field and no message
  it('displays a generic error message when error has no detail or message', () => {
    const error = new Error();
    vi.mocked(queries.usePerformRitual).mockReturnValue(makeMutationError(error));

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualPerformDialog {...defaultProps} ritual={baseRitual} />
      </Wrapper>
    );

    expect(screen.getByText('Failed to perform ritual')).toBeInTheDocument();
  });

  // 9c. Shows the Error.message when there is no detail field but there is a message
  it('displays error.message when error is a plain Error with no detail', () => {
    const error = new Error('network error');
    vi.mocked(queries.usePerformRitual).mockReturnValue(makeMutationError(error));

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualPerformDialog {...defaultProps} ritual={baseRitual} />
      </Wrapper>
    );

    expect(screen.getByText('network error')).toBeInTheDocument();
  });

  // 10. Mutation error state resets on dialog close
  it('calls mutation.reset() when dialog closes', async () => {
    const error = new Error('Previous error');
    vi.mocked(queries.usePerformRitual).mockReturnValue(makeMutationError(error));

    const onOpenChange = vi.fn();
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <RitualPerformDialog {...defaultProps} onOpenChange={onOpenChange} ritual={baseRitual} />
      </Wrapper>
    );

    // Verify error is displayed
    expect(screen.getByText('Previous error')).toBeInTheDocument();

    // Close the dialog
    const cancelBtn = screen.getByRole('button', { name: /cancel/i });
    await userEvent.click(cancelBtn);

    // Verify reset was called
    expect(mockReset).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
