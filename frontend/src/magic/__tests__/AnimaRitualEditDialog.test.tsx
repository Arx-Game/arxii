/**
 * AnimaRitualEditDialog tests
 *
 * Covers: field rendering, required-field validation, PATCH body on submit,
 * onSuccess callback, typed error display, and the two resonance picks (#5280): the pickers
 * and "Set resonances" while the ritual has none, the locked view and the Attune dialog after.
 */

import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import { AnimaRitualEditDialog } from '../components/AnimaRitualEditDialog';
import type { RitualWithSchema } from '@/rituals/types';
import * as ritualQueries from '@/rituals/queries';
import type { AnimaRitualChoices } from '@/rituals/api';

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

const mockSetUp = vi.fn();
const mockAttune = vi.fn();

function makeIdle(mutate: typeof mockSetUp) {
  return {
    mutate,
    reset: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  };
}

const unsetChoices: AnimaRitualChoices = {
  primal: [
    { id: 1, name: 'Thrill', affinity_name: 'Primal' },
    { id: 2, name: 'Hunger', affinity_name: 'Primal' },
  ],
  outward: [
    { id: 3, name: 'Dread', affinity_name: 'Abyssal' },
    { id: 4, name: 'Mercy', affinity_name: 'Celestial' },
  ],
  primal_pick: null,
  outward_pick: null,
  locked: false,
  attunement: { anima_cost: 2, resonance_cost: 5, ap_cost: 1, check_type_name: null },
};

const lockedChoices = {
  ...unsetChoices,
  primal_pick: unsetChoices.primal[0],
  outward_pick: unsetChoices.outward[0],
  locked: true,
};

function mockChoices(data: AnimaRitualChoices | undefined) {
  vi.mocked(ritualQueries.useAnimaRitualChoices).mockReturnValue({
    data,
  } as unknown as ReturnType<typeof ritualQueries.useAnimaRitualChoices>);
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
  characterSheetId: 12,
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
    vi.mocked(ritualQueries.useSetUpAnimaRitual).mockReturnValue(
      makeIdle(mockSetUp) as unknown as ReturnType<typeof ritualQueries.useSetUpAnimaRitual>
    );
    vi.mocked(ritualQueries.useAttuneAnimaRitual).mockReturnValue(
      makeIdle(mockAttune) as unknown as ReturnType<typeof ritualQueries.useAttuneAnimaRitual>
    );
    mockChoices(unsetChoices);
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
    expect(screen.queryByTestId('field-resonance-id')).not.toBeInTheDocument();
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

  // 7. Per-site error fallback
  it('displays per-site fallback error when error has no message', () => {
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

  // 10. Unset: two pickers, "None" on the outward one, and Set resonances writes both picks
  it('sets both picks from the pickers while the ritual has none', async () => {
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} />
      </Wrapper>
    );

    const setButton = screen.getByRole('button', { name: 'Set resonances' });
    expect(setButton).toBeDisabled();
    // Nothing is selected yet on the outward picker, "None" included.
    expect(screen.getByRole('button', { name: 'None' })).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('What you feel when you perform it')).toBeInTheDocument();
    expect(screen.getByText('What it does to the other person')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Hunger' }));
    await userEvent.click(screen.getByRole('button', { name: 'Mercy' }));
    expect(setButton).toBeEnabled();
    await userEvent.click(setButton);

    expect(mockSetUp).toHaveBeenCalledWith({
      character_sheet_id: 12,
      primal_resonance_id: 2,
      outward_resonance_id: 4,
    });
    expect(screen.queryByRole('button', { name: 'Attune' })).not.toBeInTheDocument();
  });

  // 11. Locked: read-only picks and an Attune button that opens the dialog with its costs
  it('shows the locked picks and opens the Attune dialog with the staff-set costs', async () => {
    mockChoices(lockedChoices);
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} />
      </Wrapper>
    );

    expect(screen.queryByRole('button', { name: 'Set resonances' })).not.toBeInTheDocument();
    expect(screen.getByText('What you feel')).toBeInTheDocument();
    expect(screen.getByText('What it does to them')).toBeInTheDocument();

    await userEvent.click(screen.getByTestId('anima-ritual-attune-button'));

    expect(screen.getByText('Attune your ritual')).toBeInTheDocument();
    const costs = screen.getByTestId('anima-ritual-attune-costs');
    expect(costs).toHaveTextContent('Anima2');
    expect(costs).toHaveTextContent('Resonance cost5');
    expect(costs).toHaveTextContent('Action points1');
    expect(costs).not.toHaveTextContent('Roll');
  });

  // 12. Attune: a changed pick names itself in the cost row, and the roll shows when staff set one
  it('attunes to the new pick and shows the roll only when a check is set', async () => {
    mockChoices({
      ...lockedChoices,
      attunement: { ...lockedChoices.attunement, check_type_name: 'Willpower + Ritualism' },
    });
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} />
      </Wrapper>
    );

    await userEvent.click(screen.getByTestId('anima-ritual-attune-button'));
    const dialog = screen.getByRole('dialog', { name: 'Attune your ritual' });
    const attuneButton = within(dialog).getByRole('button', { name: 'Attune' });
    expect(attuneButton).toBeDisabled();

    await userEvent.click(within(dialog).getByRole('button', { name: 'Hunger' }));
    expect(screen.getByTestId('anima-ritual-attune-costs')).toHaveTextContent(
      'Resonance cost (Hunger)5'
    );
    expect(screen.getByTestId('anima-ritual-attune-costs')).toHaveTextContent(
      'RollWillpower + Ritualism'
    );
    await userEvent.click(attuneButton);

    expect(mockAttune).toHaveBeenCalledWith(
      { character_sheet_id: 12, primal_resonance_id: 2, outward_resonance_id: 3 },
      expect.any(Object)
    );
  });

  // 13. A refusal reads as the dialog's own error
  it('shows an attunement refusal as the dialog error', async () => {
    mockChoices(lockedChoices);
    vi.mocked(ritualQueries.useAttuneAnimaRitual).mockReturnValue({
      ...makeIdle(mockAttune),
      isError: true,
      error: new Error('You do not have enough Hunger to attune your ritual.'),
    } as unknown as ReturnType<typeof ritualQueries.useAttuneAnimaRitual>);
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} />
      </Wrapper>
    );

    await userEvent.click(screen.getByTestId('anima-ritual-attune-button'));

    expect(screen.getByTestId('anima-ritual-attune-error')).toHaveTextContent(
      'You do not have enough Hunger to attune your ritual.'
    );
  });

  // 14. The choices query failing shows its error rather than nothing
  it('shows the error when the ritual choices fail to load', () => {
    vi.mocked(ritualQueries.useAnimaRitualChoices).mockReturnValue({
      data: undefined,
      isError: true,
      error: new Error('You have no anima ritual to set up.'),
    } as unknown as ReturnType<typeof ritualQueries.useAnimaRitualChoices>);
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} />
      </Wrapper>
    );

    expect(screen.getByTestId('anima-ritual-choices-error')).toHaveTextContent(
      'You have no anima ritual to set up.'
    );
  });

  // 15. A current pick she no longer holds shows selected and disabled, and Attune waits for
  // that slot to change, because the server refuses an attunement that keeps an unheld pick
  it('shows an unheld current pick as a disabled selected pill and waits for a change', async () => {
    mockChoices({
      ...lockedChoices,
      primal: [unsetChoices.primal[1]],
      primal_pick: unsetChoices.primal[0],
    });
    const Wrapper = createWrapper();
    render(
      <Wrapper>
        <AnimaRitualEditDialog {...defaultProps} />
      </Wrapper>
    );

    await userEvent.click(screen.getByTestId('anima-ritual-attune-button'));
    const dialog = screen.getByRole('dialog', { name: 'Attune your ritual' });
    const kept = within(dialog).getByRole('button', { name: 'Thrill' });
    expect(kept).toBeDisabled();
    expect(kept).toHaveAttribute('aria-pressed', 'true');
    // Changing only the outward pick still keeps the unheld Primal one, so it is not offered.
    await userEvent.click(within(dialog).getByRole('button', { name: 'Mercy' }));
    expect(within(dialog).getByRole('button', { name: 'Attune' })).toBeDisabled();

    await userEvent.click(within(dialog).getByRole('button', { name: 'Hunger' }));
    expect(within(dialog).getByRole('button', { name: 'Attune' })).toBeEnabled();
  });
});
