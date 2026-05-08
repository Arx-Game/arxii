/**
 * AnimaRitualEditDialog tests
 *
 * Covers: field rendering, required-field validation, PATCH body on submit,
 * onSuccess callback, and typed error display.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { AnimaRitualEditDialog } from '../components/AnimaRitualEditDialog';
import type { RitualWithSchema } from '@/rituals/types';
import * as ritualQueries from '@/rituals/queries';

// ---------------------------------------------------------------------------
// Mock usePatchRitual
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
  } as unknown as ReturnType<typeof ritualQueries.usePatchRitual>;
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
  } as unknown as ReturnType<typeof ritualQueries.usePatchRitual>;
}

vi.mock('@/rituals/queries');
vi.mocked(ritualQueries.usePatchRitual).mockReturnValue(makeMutationIdle());

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
  id: 7,
  name: 'My Anima Ritual',
  description: 'A personal recovery rite.',
  narrative_prose: 'Breath in, breath out, let the soul mend.',
  input_schema: null,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
} as any;

const defaultProps = {
  ritual: baseRitual,
  open: true,
  onOpenChange: vi.fn(),
  onSuccess: vi.fn(),
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('AnimaRitualEditDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(ritualQueries.usePatchRitual).mockReturnValue(makeMutationIdle());
  });

  // 1. Renders the form with all expected fields
  it('renders the form with all expected fields', () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} />
      </Wrapper>
    );

    expect(screen.getByTestId('field-name')).toBeInTheDocument();
    expect(screen.getByTestId('field-description')).toBeInTheDocument();
    expect(screen.getByTestId('field-narrative-prose')).toBeInTheDocument();
    expect(screen.getByTestId('field-stat-id')).toBeInTheDocument();
    expect(screen.getByTestId('field-skill-id')).toBeInTheDocument();
    expect(screen.getByTestId('field-specialization-id')).toBeInTheDocument();
    expect(screen.getByTestId('field-resonance-id')).toBeInTheDocument();
    expect(screen.getByTestId('field-check-type-id')).toBeInTheDocument();
    expect(screen.getByTestId('field-target-difficulty')).toBeInTheDocument();
  });

  // 2. Pre-populates name/description/narrative_prose from ritual prop
  it('pre-populates text fields from the ritual prop', () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} />
      </Wrapper>
    );

    expect(screen.getByTestId('field-name')).toHaveValue('My Anima Ritual');
    expect(screen.getByTestId('field-description')).toHaveValue('A personal recovery rite.');
    expect(screen.getByTestId('field-narrative-prose')).toHaveValue(
      'Breath in, breath out, let the soul mend.'
    );
  });

  // 3. Save button disabled until all required fields are filled
  it('disables Save button until required fields are filled', async () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} />
      </Wrapper>
    );

    const saveBtn = screen.getByTestId('anima-ritual-save-button');
    // name is filled, but stat_id, skill_id, check_type_id are empty → disabled
    expect(saveBtn).toBeDisabled();

    // Fill required FK fields
    await userEvent.type(screen.getByTestId('field-stat-id'), '1');
    await userEvent.type(screen.getByTestId('field-skill-id'), '2');
    await userEvent.type(screen.getByTestId('field-check-type-id'), '3');

    await waitFor(() => {
      expect(screen.getByTestId('anima-ritual-save-button')).not.toBeDisabled();
    });
  });

  // 4. PATCHes correct body on submit
  it('calls mutate with correct body on submit', async () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} />
      </Wrapper>
    );

    await userEvent.type(screen.getByTestId('field-stat-id'), '1');
    await userEvent.type(screen.getByTestId('field-skill-id'), '2');
    await userEvent.type(screen.getByTestId('field-check-type-id'), '3');

    await waitFor(() => expect(screen.getByTestId('anima-ritual-save-button')).not.toBeDisabled());

    await userEvent.click(screen.getByTestId('anima-ritual-save-button'));

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 7,
        body: expect.objectContaining({
          name: 'My Anima Ritual',
          stat_id: 1,
          skill_id: 2,
          check_type_id: 3,
        }),
      }),
      expect.any(Object)
    );
  });

  // 5. calls onSuccess and closes on 200
  it('calls onSuccess and onOpenChange(false) on successful submission', async () => {
    const onSuccess = vi.fn();
    const onOpenChange = vi.fn();

    // Arrange mutate to immediately call its onSuccess callback
    mockMutate.mockImplementation((_args: unknown, callbacks: { onSuccess?: () => void }) => {
      callbacks?.onSuccess?.();
    });

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog
          {...defaultProps}
          onSuccess={onSuccess}
          onOpenChange={onOpenChange}
        />
      </Wrapper>
    );

    await userEvent.type(screen.getByTestId('field-stat-id'), '1');
    await userEvent.type(screen.getByTestId('field-skill-id'), '2');
    await userEvent.type(screen.getByTestId('field-check-type-id'), '3');

    await waitFor(() => expect(screen.getByTestId('anima-ritual-save-button')).not.toBeDisabled());

    await userEvent.click(screen.getByTestId('anima-ritual-save-button'));

    expect(onSuccess).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  // 6. renders typed error from response
  it('displays error message from thrown exception', () => {
    const error = new Error('This ritual cannot be updated right now.');
    vi.mocked(ritualQueries.usePatchRitual).mockReturnValue(makeMutationError(error));

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} />
      </Wrapper>
    );

    expect(screen.getByTestId('anima-ritual-edit-error')).toBeInTheDocument();
    expect(screen.getByText('This ritual cannot be updated right now.')).toBeInTheDocument();
  });

  // 7. Generic error fallback
  it('displays generic error when error has no message', () => {
    const error = new Error();
    vi.mocked(ritualQueries.usePatchRitual).mockReturnValue(makeMutationError(error));

    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} />
      </Wrapper>
    );

    expect(screen.getByText('Failed to update ritual')).toBeInTheDocument();
  });

  // 8. Cancel closes dialog without submitting
  it('calls onOpenChange(false) when cancel is clicked without submitting', async () => {
    const onOpenChange = vi.fn();
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} onOpenChange={onOpenChange} />
      </Wrapper>
    );

    await userEvent.click(screen.getByRole('button', { name: /cancel/i }));

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(mockMutate).not.toHaveBeenCalled();
  });

  // 9. mutation.reset() called on close
  it('calls mutation.reset() when dialog closes', async () => {
    const error = new Error('Previous error');
    vi.mocked(ritualQueries.usePatchRitual).mockReturnValue(makeMutationError(error));

    const onOpenChange = vi.fn();
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} onOpenChange={onOpenChange} />
      </Wrapper>
    );

    expect(screen.getByText('Previous error')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: /cancel/i }));

    expect(mockReset).toHaveBeenCalled();
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
