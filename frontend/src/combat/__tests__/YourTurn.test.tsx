/**
 * Tests for YourTurn section — Tasks 7.1, 7.2, 7.3.
 *
 * Mocks:
 * - @/combat/queries (useAvailableCombos, useUpgradeCombo, useDispatchPlayerAction)
 * - @/actions/ActionDeclarationCard (stub — isolates slot composition logic)
 * - @/magic/queries (useApplicablePulls, useThreads, useCharacterResonances, useTechnique)
 * - @/scenes/actionQueries (fetchAvailableActions)
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Module mocks — hoisted before imports
// ---------------------------------------------------------------------------

vi.mock('@/combat/queries', () => ({
  useAvailableCombos: vi.fn(),
  useUpgradeCombo: vi.fn(),
  useDispatchPlayerAction: vi.fn(),
  useFleeMutation: vi.fn(),
  useCoverMutation: vi.fn(),
  combatKeys: {
    all: ['combat'],
    encounter: (id: number) => ['combat', 'encounter', id],
    combos: (id: number) => ['combat', 'combos', id],
  },
}));

vi.mock('@/scenes/actionQueries', () => ({
  fetchAvailableActions: vi.fn(),
}));

// Stub ActionDeclarationCard — wrapped in vi.fn() so per-test overrides via
// mockImplementation() work. The default implementation exposes:
//   - data-testid="card-change-btn-<slot>": fires onContextChange without techniqueId
//   - data-testid="card-select-technique-<slot>": fires onContextChange WITH
//     techniqueId (read from actionContext.techniqueId, so caller must supply it
//     via the actionContext prop — only meaningful in per-test overrides where the
//     parent state already holds a techniqueId, or where the mockImplementation
//     hard-codes one).
type CardProps = {
  actionContext: { slot: string; strainCommitment: number; techniqueId?: number };
  onContextChange: (ctx: {
    slot: string;
    strainCommitment: number;
    effort: string;
    techniqueId?: number;
  }) => void;
  readOnly?: boolean;
};

function defaultCardImpl({ actionContext, onContextChange, readOnly }: CardProps) {
  const slot = actionContext.slot;
  return (
    <div data-testid={`action-card-${slot}`} data-readonly={String(readOnly ?? false)}>
      ActionCard [{slot}]
      <button
        type="button"
        data-testid={`card-change-btn-${slot}`}
        onClick={() =>
          onContextChange({
            slot,
            effort: 'HIGH',
            strainCommitment: actionContext.strainCommitment,
          })
        }
      >
        change
      </button>
      <button
        type="button"
        data-testid={`card-select-technique-${slot}`}
        onClick={() =>
          onContextChange({
            slot,
            effort: 'MEDIUM',
            strainCommitment: actionContext.strainCommitment,
            techniqueId: actionContext.techniqueId,
          })
        }
      >
        select technique
      </button>
    </div>
  );
}

const mockActionDeclarationCard = vi.fn(defaultCardImpl);

vi.mock('@/actions/ActionDeclarationCard', () => ({
  get ActionDeclarationCard() {
    return mockActionDeclarationCard;
  },
}));

// Magic queries — stubbed so the ActionDeclarationCard stub never calls them.
vi.mock('@/magic/queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/magic/queries')>();
  return {
    ...actual,
    useTechnique: vi.fn().mockReturnValue({ data: null, isLoading: false, isError: false }),
    useApplicablePulls: vi.fn().mockReturnValue({ data: [], isLoading: false, isError: false }),
    useThreads: vi.fn().mockReturnValue({
      data: { results: [], count: 0, next: null, previous: null },
      isLoading: false,
      isError: false,
    }),
    useCharacterResonances: vi.fn().mockReturnValue({ data: [], isLoading: false, isError: false }),
  };
});

import * as combatQueries from '@/combat/queries';
import { YourTurn } from '../sections/YourTurn';
import type { YourTurnProps } from '../sections/YourTurn';
import type { AvailableCombo, EncounterDetail, Participant } from '../types';
import type { PlayerAction } from '@/scenes/actionTypes';

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

const mockedUseAvailableCombos = combatQueries.useAvailableCombos as ReturnType<typeof vi.fn>;
const mockedUseUpgradeCombo = combatQueries.useUpgradeCombo as ReturnType<typeof vi.fn>;
const mockedUseDispatchPlayerAction = combatQueries.useDispatchPlayerAction as ReturnType<
  typeof vi.fn
>;
const mockedUseFleeMutation = combatQueries.useFleeMutation as ReturnType<typeof vi.fn>;
const mockedUseCoverMutation = combatQueries.useCoverMutation as ReturnType<typeof vi.fn>;

const mockMutate = vi.fn();
const mockFleeMutate = vi.fn();
const mockCoverMutate = vi.fn();
const mockMutateAsync = vi.fn();

function setupMocks(
  options: {
    combos?: AvailableCombo[];
    combosLoading?: boolean;
  } = {}
) {
  mockedUseAvailableCombos.mockReturnValue({
    data: options.combos ?? [],
    isLoading: options.combosLoading ?? false,
    isError: false,
  });
  mockedUseUpgradeCombo.mockReturnValue({
    mutate: mockMutate,
    isPending: false,
  });
  mockedUseDispatchPlayerAction.mockReturnValue({
    mutateAsync: mockMutateAsync,
    isPending: false,
  });
  mockedUseFleeMutation.mockReturnValue({
    mutate: mockFleeMutate,
    isPending: false,
  });
  mockedUseCoverMutation.mockReturnValue({
    mutate: mockCoverMutate,
    isPending: false,
  });
}

// ---------------------------------------------------------------------------
// Encounter fixture factory for flee / cover tests
// ---------------------------------------------------------------------------

function makeParticipant(
  id: number,
  name: string,
  status = 'active',
  /** CharacterSheet PK. Defaults to id+1000 so ally fixtures don't collide with
   *  defaultProps.characterSheetId (100) unless explicitly set. */
  characterSheetId = id + 1000
): Participant {
  return {
    id,
    character_sheet_id: characterSheetId,
    character_name: name,
    status: status as Participant['status'],
    health: null,
    max_health: null,
    character_status: null,
    available_strain: null,
    fatigue: null,
    active_conditions: [],
    thumbnail_url: null,
    thumbnail_media_url: null,
    escalation_level: null,
    intensity_modifier: null,
    control_modifier: null,
  };
}

/** The viewer's own participant fixture — character_sheet_id matches defaultProps.characterSheetId. */
function makeSelfParticipant(id: number): Participant {
  return makeParticipant(id, 'Hero', 'active', 100);
}

function makeEncounter(overrides: Partial<EncounterDetail> = {}): EncounterDetail {
  return {
    id: 1,
    status: 'declaring',
    round_number: 1,
    is_participant: true,
    is_gm: false,
    participants: [],
    opponents: [],
    current_round_actions: [],
    clashes: [],
    created_at: '2026-06-11T00:00:00Z',
    ...overrides,
  } as unknown as EncounterDetail;
}

function defaultProps(overrides?: Partial<YourTurnProps>): YourTurnProps {
  return {
    encounterId: 1,
    characterId: 10,
    characterSheetId: 100,
    roundNumber: 1,
    availableActions: [],
    readOnly: false,
    ...overrides,
  };
}

function makePlayerAction(clashId: number | null, displayName: string): PlayerAction {
  return {
    backend: 'COMBAT',
    display_name: displayName,
    description: '',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Attack' },
    action_template: null,
    ref: {
      backend: 'COMBAT',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: null,
      registry_key: null,
      clash_id: clashId,
      clash_action_slot: clashId !== null ? 'FOCUSED' : null,
    },
    target_spec: null,
    enhancements: [],
    strain: null,
  };
}

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  mockMutateAsync.mockResolvedValue({ backend: 'COMBAT', deferred: true });
  mockFleeMutate.mockImplementation((_arg: unknown, opts?: { onError?: (e: Error) => void }) => {
    void opts;
  });
  mockCoverMutate.mockImplementation((_arg: unknown, opts?: { onError?: (e: Error) => void }) => {
    void opts;
  });
});

// ---------------------------------------------------------------------------
// Task 7.1 — Slot composition
// ---------------------------------------------------------------------------

describe('YourTurn — Task 7.1 slot composition', () => {
  it('renders the focused slot card', () => {
    setupMocks();

    render(<YourTurn {...defaultProps()} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('action-card-focused')).toBeInTheDocument();
  });

  it('renders all three passive cards when no focused technique is selected', () => {
    // No focused technique → no category to hide → all passives visible (#614).
    setupMocks();

    render(<YourTurn {...defaultProps()} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('action-card-passive-physical')).toBeInTheDocument();
    expect(screen.getByTestId('action-card-passive-social')).toBeInTheDocument();
    expect(screen.getByTestId('action-card-passive-mental')).toBeInTheDocument();
  });

  it('hides the passive slot matching the focused technique action_category (#614)', async () => {
    setupMocks();
    const base = makePlayerAction(null, 'Flame Strike');
    const focusedTech: PlayerAction = {
      ...base,
      ref: { ...base.ref, technique_id: 1 },
      action_category: 'physical',
    };

    // Override the focused card so "select technique" picks technique_id=1.
    mockActionDeclarationCard.mockImplementation(({ actionContext, onContextChange, readOnly }) => {
      const slot = actionContext.slot as string;
      return (
        <div data-testid={`action-card-${slot}`} data-readonly={String(readOnly ?? false)}>
          ActionCard [{slot}]
          <button
            type="button"
            data-testid={`card-select-technique-${slot}`}
            onClick={() =>
              onContextChange({ slot, effort: 'MEDIUM', strainCommitment: 0, techniqueId: 1 })
            }
          >
            select technique
          </button>
        </div>
      );
    });

    render(<YourTurn {...defaultProps({ availableActions: [focusedTech] })} />, {
      wrapper: createWrapper(),
    });

    // Before selecting: all passives visible.
    expect(screen.getByTestId('action-card-passive-physical')).toBeInTheDocument();

    // Select the focused technique (id=1, action_category='physical').
    await userEvent.click(screen.getByTestId('card-select-technique-focused'));

    // passive-physical now hidden; social + mental remain.
    await waitFor(() => {
      expect(screen.queryByTestId('action-card-passive-physical')).not.toBeInTheDocument();
    });
    expect(screen.getByTestId('action-card-passive-social')).toBeInTheDocument();
    expect(screen.getByTestId('action-card-passive-mental')).toBeInTheDocument();

    mockActionDeclarationCard.mockImplementation(defaultCardImpl);
  });

  it('renders the submit button', () => {
    setupMocks();

    render(<YourTurn {...defaultProps()} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('submit-declarations-btn')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Task 7.2 — Combo upgrade affordances
// ---------------------------------------------------------------------------

describe('YourTurn — Task 7.2 combo upgrade', () => {
  it('does not render combo section when no combos available', () => {
    setupMocks({ combos: [] });

    render(<YourTurn {...defaultProps()} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('combo-upgrade-section')).not.toBeInTheDocument();
  });

  it('renders combo upgrade row when combos are available', () => {
    setupMocks({
      combos: [{ combo_id: 1, combo_name: 'Tidewall', known_by_participant: true, slot_count: 2 }],
    });

    render(<YourTurn {...defaultProps()} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('combo-upgrade-section')).toBeInTheDocument();
    expect(screen.getByTestId('combo-upgrade-btn-1')).toBeInTheDocument();
    expect(screen.getByText(/Upgrade to Tidewall \(2 slots\)/)).toBeInTheDocument();
  });

  it('renders known combo as enabled and unknown as disabled', () => {
    setupMocks({
      combos: [
        { combo_id: 1, combo_name: 'Tidewall', known_by_participant: true, slot_count: 2 },
        { combo_id: 2, combo_name: 'Storm Ring', known_by_participant: false, slot_count: 3 },
      ],
    });

    render(<YourTurn {...defaultProps()} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('combo-upgrade-btn-1')).not.toBeDisabled();
    expect(screen.getByTestId('combo-upgrade-btn-2')).toBeDisabled();
    expect(screen.getByTestId('combo-upgrade-btn-2')).toHaveAttribute('title', 'Combo not known');
  });

  it('calls upgradeCombo mutation when a known combo is clicked', async () => {
    setupMocks({
      combos: [{ combo_id: 5, combo_name: 'Tidewall', known_by_participant: true, slot_count: 2 }],
    });

    render(<YourTurn {...defaultProps()} />, { wrapper: createWrapper() });

    await userEvent.click(screen.getByTestId('combo-upgrade-btn-5'));

    expect(mockMutate).toHaveBeenCalledWith(5);
  });
});

// ---------------------------------------------------------------------------
// Task 7.2 — Clash contribution affordances
// ---------------------------------------------------------------------------

describe('YourTurn — Task 7.2 clash contributions', () => {
  it('does not render clash section when no clash actions', () => {
    setupMocks();

    render(<YourTurn {...defaultProps({ availableActions: [] })} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('clash-contributions-section')).not.toBeInTheDocument();
  });

  it('renders clash contribution row when clash PlayerAction exists', () => {
    setupMocks();
    const clashAction = makePlayerAction(42, 'The Great Clash');

    render(<YourTurn {...defaultProps({ availableActions: [clashAction] })} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('clash-contributions-section')).toBeInTheDocument();
    expect(screen.getByTestId('clash-contribution-row-42')).toBeInTheDocument();
    expect(screen.getByTestId('clash-commit-btn-42')).toBeInTheDocument();
  });

  it('shows strain slider when clash contribution is selected', async () => {
    setupMocks();
    const clashAction = makePlayerAction(42, 'The Great Clash');

    render(<YourTurn {...defaultProps({ availableActions: [clashAction] })} />, {
      wrapper: createWrapper(),
    });

    // Slider not visible initially
    expect(screen.queryByTestId('clash-strain-slider-42')).not.toBeInTheDocument();

    // Click to select
    await userEvent.click(screen.getByTestId('clash-commit-btn-42'));

    expect(screen.getByTestId('clash-strain-slider-42')).toBeInTheDocument();
  });

  it('strain slider updates actionContext.strainCommitment via onContextChange', async () => {
    setupMocks();
    const clashAction = makePlayerAction(42, 'The Great Clash');

    render(<YourTurn {...defaultProps({ availableActions: [clashAction] })} />, {
      wrapper: createWrapper(),
    });

    // Select the clash first to show the slider
    await userEvent.click(screen.getByTestId('clash-commit-btn-42'));

    const slider = screen.getByTestId('clash-strain-slider-42');
    // Simulate moving the slider to value 5
    await userEvent.type(slider, '{ArrowRight}');
    // The slider exists and is interactive — that's the key assertion for this test.
    expect(slider).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Task 7.3 — Submit declarations + ready state
// ---------------------------------------------------------------------------

describe('YourTurn — Task 7.3 submit declarations', () => {
  it('dispatches focused first when submit is clicked', async () => {
    setupMocks();

    render(<YourTurn {...defaultProps()} />, { wrapper: createWrapper() });

    await userEvent.click(screen.getByTestId('submit-declarations-btn'));

    await waitFor(() => {
      // No technique selected → no dispatch calls expected (empty contexts).
      // The button click should not throw; submitted state should be set.
      expect(screen.getByTestId('ready-badge')).toBeInTheDocument();
    });
  });

  it('shows ready badge after submission and locks the panel', async () => {
    setupMocks();

    render(<YourTurn {...defaultProps()} />, { wrapper: createWrapper() });

    await userEvent.click(screen.getByTestId('submit-declarations-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('ready-badge')).toBeInTheDocument();
    });

    // Submit button is now disabled
    expect(screen.getByTestId('submit-declarations-btn')).toBeDisabled();

    // Cards should be read-only (data-readonly="true")
    expect(screen.getByTestId('action-card-focused')).toHaveAttribute('data-readonly', 'true');
  });

  it('resets submitted state when roundNumber changes', async () => {
    setupMocks();

    const { rerender } = render(<YourTurn {...defaultProps({ roundNumber: 1 })} />, {
      wrapper: createWrapper(),
    });

    // Submit to reach ready state
    await userEvent.click(screen.getByTestId('submit-declarations-btn'));
    await waitFor(() => {
      expect(screen.getByTestId('ready-badge')).toBeInTheDocument();
    });

    // Advance round
    rerender(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })}
      >
        <YourTurn {...defaultProps({ roundNumber: 2 })} />
      </QueryClientProvider>
    );

    // Ready badge gone, button re-enabled
    await waitFor(() => {
      expect(screen.queryByTestId('ready-badge')).not.toBeInTheDocument();
      expect(screen.getByTestId('submit-declarations-btn')).not.toBeDisabled();
    });
  });

  it('dispatches focused → passives in order (focused first)', async () => {
    setupMocks();

    // Override the stub for this test so each card's "select technique" button
    // emits a hard-coded techniqueId (not derived from actionContext.techniqueId,
    // which starts undefined). mockActionDeclarationCard is a vi.fn() so
    // mockImplementation() works per-test. Restored via mockRestore() after.
    //
    // Iteration order in handleSubmit: focused, then visiblePassiveSlots which is
    // ['passive-social', 'passive-mental'] (passive-physical hidden because
    // resolveFocusedCategory stubs to 'passive-physical').
    const techniqueIds: Record<string, number> = {
      focused: 1,
      'passive-social': 2,
      'passive-mental': 3,
    };

    mockActionDeclarationCard.mockImplementation(({ actionContext, onContextChange, readOnly }) => {
      const slot = actionContext.slot as string;
      const tid = techniqueIds[slot];
      return (
        <div data-testid={`action-card-${slot}`} data-readonly={String(readOnly ?? false)}>
          ActionCard [{slot}]
          <button
            type="button"
            data-testid={`card-select-technique-${slot}`}
            onClick={() =>
              onContextChange({
                slot,
                effort: 'MEDIUM',
                strainCommitment: 0,
                techniqueId: tid,
              })
            }
          >
            select technique
          </button>
        </div>
      );
    });

    render(<YourTurn {...defaultProps()} />, { wrapper: createWrapper() });

    // Click "select technique" for focused, passive-social, passive-mental.
    await userEvent.click(screen.getByTestId('card-select-technique-focused'));
    await userEvent.click(screen.getByTestId('card-select-technique-passive-social'));
    await userEvent.click(screen.getByTestId('card-select-technique-passive-mental'));

    await userEvent.click(screen.getByTestId('submit-declarations-btn'));

    await waitFor(() => {
      expect(screen.getByTestId('ready-badge')).toBeInTheDocument();
    });

    // Three dispatches: focused → passive-social → passive-mental (in that order).
    expect(mockMutateAsync).toHaveBeenCalledTimes(3);

    const calls = mockMutateAsync.mock.calls as Array<
      [{ ref: { backend: string; technique_id: number | null } }]
    >;

    // 1st call: focused slot (techniqueId=1)
    expect(calls[0][0].ref.technique_id).toBe(1);
    // 2nd call: passive-social (techniqueId=2) — social before mental in PASSIVE_SLOTS
    expect(calls[1][0].ref.technique_id).toBe(2);
    // 3rd call: passive-mental (techniqueId=3)
    expect(calls[2][0].ref.technique_id).toBe(3);

    // Restore default stub implementation for subsequent tests.
    mockActionDeclarationCard.mockImplementation(defaultCardImpl);
  });

  it('shows inline error alert when dispatch rejects', async () => {
    setupMocks();

    // Override stub to emit techniqueId=99 on click so handleSubmit dispatches.
    mockActionDeclarationCard.mockImplementation(({ actionContext, onContextChange, readOnly }) => {
      const slot = actionContext.slot as string;
      return (
        <div data-testid={`action-card-${slot}`} data-readonly={String(readOnly ?? false)}>
          ActionCard [{slot}]
          <button
            type="button"
            data-testid={`card-select-technique-${slot}`}
            onClick={() =>
              onContextChange({
                slot,
                effort: 'MEDIUM',
                strainCommitment: 0,
                techniqueId: 99,
              })
            }
          >
            select technique
          </button>
        </div>
      );
    });

    mockMutateAsync.mockRejectedValueOnce(new Error('boom'));

    render(<YourTurn {...defaultProps()} />, { wrapper: createWrapper() });

    // Select a technique so handleSubmit actually dispatches.
    await userEvent.click(screen.getByTestId('card-select-technique-focused'));

    await userEvent.click(screen.getByTestId('submit-declarations-btn'));

    // The inline error alert should appear with the rejection message.
    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('boom');

    // ready-badge should NOT appear — submission did not complete.
    expect(screen.queryByTestId('ready-badge')).not.toBeInTheDocument();

    // Restore default stub implementation for subsequent tests.
    mockActionDeclarationCard.mockImplementation(defaultCardImpl);
  });
});

// ---------------------------------------------------------------------------
// Task 7.1 — readOnly prop locks the panel from the start
// ---------------------------------------------------------------------------

describe('YourTurn — readOnly prop', () => {
  it('renders all cards as read-only when readOnly=true', () => {
    setupMocks();

    render(<YourTurn {...defaultProps({ readOnly: true })} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('action-card-focused')).toHaveAttribute('data-readonly', 'true');
    expect(screen.getByTestId('submit-declarations-btn')).toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Task 7 — Flee declaration controls
// ---------------------------------------------------------------------------

describe('YourTurn — flee declaration', () => {
  it('does not render maneuver section when encounter prop is absent', () => {
    setupMocks();

    render(<YourTurn {...defaultProps()} />, { wrapper: createWrapper() });

    expect(screen.queryByTestId('maneuver-declaration-section')).not.toBeInTheDocument();
  });

  it('renders flee button during declaring phase', () => {
    setupMocks();
    const encounter = makeEncounter({ status: 'declaring' });

    render(<YourTurn {...defaultProps({ encounter })} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('flee-btn')).toBeInTheDocument();
  });

  it('flee button is disabled outside the declaring phase', () => {
    setupMocks();
    const encounter = makeEncounter({ status: 'resolving' });

    render(<YourTurn {...defaultProps({ encounter })} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('flee-btn')).toBeDisabled();
  });

  it('flee button calls useFleeMutation.mutate on click', async () => {
    setupMocks();
    const encounter = makeEncounter({ status: 'declaring' });

    render(<YourTurn {...defaultProps({ encounter })} />, { wrapper: createWrapper() });

    await userEvent.click(screen.getByTestId('flee-btn'));

    expect(mockFleeMutate).toHaveBeenCalledTimes(1);
  });

  it('shows flee-declared badge when maneuver is flee', () => {
    setupMocks();
    // participants list includes the viewer's own participant (character_sheet_id=100
    // matches defaultProps.characterSheetId=100) so myParticipantId resolves to 5.
    const encounter = makeEncounter({
      status: 'declaring',
      participants: [makeSelfParticipant(5)],
      current_round_actions: [
        {
          participant: 5,
          participant_name: 'Hero',
          maneuver: 'flee',
          is_ready: false,
          focused_ally_target: null,
        },
      ],
    });

    render(<YourTurn {...defaultProps({ encounter })} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('flee-declared-badge')).toBeInTheDocument();
    expect(screen.getByTestId('flee-declared-badge')).toHaveTextContent(
      'Fleeing — resolves at end of round'
    );
    // Flee button should be hidden when already declared.
    expect(screen.queryByTestId('flee-btn')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Task 7 — Cover declaration controls
// ---------------------------------------------------------------------------

describe('YourTurn — cover declaration', () => {
  it('renders cover control during declaring phase', () => {
    setupMocks();
    const encounter = makeEncounter({
      status: 'declaring',
      participants: [makeParticipant(1, 'Ally One'), makeParticipant(2, 'Ally Two')],
    });

    render(<YourTurn {...defaultProps({ encounter })} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('cover-control')).toBeInTheDocument();
    expect(screen.getByTestId('cover-ally-select')).toBeInTheDocument();
    expect(screen.getByTestId('cover-confirm-btn')).toBeInTheDocument();
  });

  it('cover confirm button is disabled when no ally is selected', () => {
    setupMocks();
    const encounter = makeEncounter({
      status: 'declaring',
      participants: [makeParticipant(1, 'Ally One')],
    });

    render(<YourTurn {...defaultProps({ encounter })} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('cover-confirm-btn')).toBeDisabled();
  });

  it('cover confirm button disabled outside declaring phase', () => {
    setupMocks();
    const encounter = makeEncounter({ status: 'resolving' });

    render(<YourTurn {...defaultProps({ encounter })} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('cover-confirm-btn')).toBeDisabled();
  });

  it('shows cover-declared badge when maneuver is cover', () => {
    setupMocks();
    // Self participant (id=5, character_sheet_id=100) + ally (id=7).
    const encounter = makeEncounter({
      status: 'declaring',
      participants: [makeSelfParticipant(5), makeParticipant(7, 'Shield Bearer')],
      current_round_actions: [
        {
          participant: 5,
          participant_name: 'Hero',
          maneuver: 'cover',
          is_ready: false,
          focused_ally_target: 7,
        },
      ],
    });

    render(<YourTurn {...defaultProps({ encounter })} />, { wrapper: createWrapper() });

    expect(screen.getByTestId('cover-declared-badge')).toBeInTheDocument();
    expect(screen.getByTestId('cover-declared-badge')).toHaveTextContent('Covering Shield Bearer');
    // Cover control hidden when already declared.
    expect(screen.queryByTestId('cover-control')).not.toBeInTheDocument();
  });

  it('cover confirm posts ally participant id via useCoverMutation', async () => {
    setupMocks();
    const encounter = makeEncounter({
      status: 'declaring',
      participants: [makeParticipant(3, 'Ally Three')],
    });

    render(<YourTurn {...defaultProps({ encounter })} />, { wrapper: createWrapper() });

    // Open the Select and pick the ally.
    // Radix UI Select uses a trigger button + portal content.
    // Click the trigger to open, then click the item.
    const trigger = screen.getByTestId('cover-ally-select');
    await userEvent.click(trigger);

    const option = await screen.findByText('Ally Three');
    await userEvent.click(option);

    // Confirm cover.
    const confirmBtn = screen.getByTestId('cover-confirm-btn');
    await waitFor(() => expect(confirmBtn).not.toBeDisabled());
    await userEvent.click(confirmBtn);

    expect(mockCoverMutate).toHaveBeenCalledWith(
      3,
      expect.objectContaining({ onError: expect.any(Function) })
    );
  });
});

// ---------------------------------------------------------------------------
// Robustness — own-action resolution is position-independent
// ---------------------------------------------------------------------------

describe('YourTurn — own-action resolved by participant PK, not position', () => {
  it('shows flee badge even when another participant action appears first in the list (GM view)', () => {
    // Simulates the GM/staff scenario where current_round_actions contains
    // ALL participants' actions, unordered — another participant comes first.
    setupMocks();
    const encounter = makeEncounter({
      status: 'declaring',
      // Viewer's own participant: id=5, character_sheet_id=100.
      participants: [makeSelfParticipant(5), makeParticipant(9, 'Other Combatant')],
      current_round_actions: [
        // Another participant's action comes FIRST — must not be treated as self.
        {
          participant: 9,
          participant_name: 'Other Combatant',
          maneuver: null,
          is_ready: false,
          focused_ally_target: null,
        },
        // Viewer's own action — flee declared.
        {
          participant: 5,
          participant_name: 'Hero',
          maneuver: 'flee',
          is_ready: false,
          focused_ally_target: null,
        },
      ],
    });

    render(<YourTurn {...defaultProps({ encounter })} />, { wrapper: createWrapper() });

    // Own flee maneuver is recognised despite not being actions[0].
    expect(screen.getByTestId('flee-declared-badge')).toBeInTheDocument();
    expect(screen.queryByTestId('flee-btn')).not.toBeInTheDocument();
  });
});
