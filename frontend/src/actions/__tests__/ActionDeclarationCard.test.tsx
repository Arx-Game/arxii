/**
 * Tests for ActionDeclarationCard — Phase 5.1, 5.2, and 5.3.
 *
 * Mocks:
 * - @/scenes/actionQueries.fetchAvailableActions  (technique list)
 * - @/magic/queries.useApplicablePulls + useThreads
 * - @/magic/components/threads/ThreadPullPicker   (stub to isolate card tests)
 *
 * The chip and cost line read each technique's server-computed `cast_preview`
 * from the actions list (#4799). ThreadPullPicker is stubbed so Phase 5 tests don't break due to Phase 6
 * threading complexity.
 */

import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { ActionDeclarationCard } from '../ActionDeclarationCard';
import type { ActionContext } from '../types';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('@/scenes/actionQueries', async () => {
  const { useQuery } = await import('@tanstack/react-query');
  const fetchAvailableActions = vi.fn();
  return {
    fetchAvailableActions,
    useAvailableActionsQuery: (
      characterId: number | null,
      options: { enabled?: boolean; staleTime?: number; refetchInterval?: number } = {}
    ) =>
      useQuery({
        queryKey: ['available-actions', characterId ?? 0],
        queryFn: () => fetchAvailableActions(characterId),
        enabled: (options.enabled ?? true) && characterId !== null && characterId > 0,
        staleTime: options.staleTime ?? 10_000,
        refetchInterval: options.refetchInterval,
      }),
  };
});

// Mock the entire magic queries module to control useApplicablePulls,
// useThreads, and useCharacterResonances synchronously.
vi.mock('@/magic/queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/magic/queries')>();
  return {
    ...actual,
    useApplicablePulls: vi.fn(),
    useThreads: vi.fn(),
    useCharacterResonances: vi.fn(),
  };
});

// Stub ThreadPullPicker to prevent it from rendering full complexity in card tests.
vi.mock('@/magic/components/threads/ThreadPullPicker', () => ({
  ThreadPullPicker: () => <div data-testid="thread-pull-picker-stub">Thread pulls stub</div>,
}));

import { fetchAvailableActions } from '@/scenes/actionQueries';
import * as magicQueries from '@/magic/queries';

const mockedFetchActions = fetchAvailableActions as ReturnType<typeof vi.fn>;
const mockedUseApplicablePulls = magicQueries.useApplicablePulls as ReturnType<typeof vi.fn>;
const mockedUseThreads = magicQueries.useThreads as ReturnType<typeof vi.fn>;
const mockedUseCharacterResonances = magicQueries.useCharacterResonances as ReturnType<
  typeof vi.fn
>;

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

function emptyContext(overrides?: Partial<ActionContext>): ActionContext {
  return {
    slot: 'focused',
    effort: 'MEDIUM',
    strainCommitment: 0,
    ...overrides,
  };
}

const MOCK_TECHNIQUES = [
  {
    backend: 'MAGIC',
    display_name: 'Tidal Fury',
    description: 'A powerful wave attack',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Attack' },
    action_template: null,
    ref: {
      backend: 'MAGIC',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: 101,
      registry_key: null,
    },
    // The live #4799 case: authored I:20 / C:40, running at I:33 / C:26 for 8 anima.
    cast_preview: { intensity: 33, control: 26, effective_anima_cost: 8 },
  },
  {
    backend: 'MAGIC',
    display_name: 'Storm Surge',
    description: 'A defensive surge',
    difficulty: null,
    prerequisite_met: true,
    prerequisite_reasons: [],
    check_type: { id: 1, name: 'Defense' },
    action_template: null,
    ref: {
      backend: 'MAGIC',
      challenge_instance_id: null,
      approach_id: null,
      technique_id: 102,
      registry_key: null,
    },
    cast_preview: { intensity: 4, control: 7, effective_anima_cost: 0 },
  },
];

function mockPickerHooks() {
  // Provide stub returns for Phase 6 hooks so card tests don't break.
  mockedUseApplicablePulls.mockReturnValue({ data: [], isLoading: false, isError: false });
  mockedUseThreads.mockReturnValue({
    data: { results: [], count: 0, next: null, previous: null },
    isLoading: false,
    isError: false,
  });
  mockedUseCharacterResonances.mockReturnValue({ data: [], isLoading: false, isError: false });
}

// ---------------------------------------------------------------------------
// Task 5.1 — skeleton + empty-state tests
// ---------------------------------------------------------------------------

describe('ActionDeclarationCard — Task 5.1 skeleton', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    mockPickerHooks();
  });

  it('renders with empty context (no technique picked yet)', async () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    // Wait for the loading state to clear after React Query resolves.
    await waitFor(() => {
      expect(screen.getByText(/pick a technique/i)).toBeInTheDocument();
    });
  });

  it('renders all section headings', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/^technique$/i)).toBeInTheDocument();
    expect(screen.getByText(/^target$/i)).toBeInTheDocument();
    expect(screen.getByText(/^effort$/i)).toBeInTheDocument();
    expect(screen.getByText(/^cost$/i)).toBeInTheDocument();
    expect(screen.getByText(/^thread pulls$/i)).toBeInTheDocument();
  });

  it('renders the slot name in the header', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ slot: 'passive-physical' })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/passive physical/i)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Task 5.2 — technique + target pickers
// ---------------------------------------------------------------------------

describe('ActionDeclarationCard — Task 5.2 technique picker', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({
      count: MOCK_TECHNIQUES.length,
      next: null,
      previous: null,
      results: MOCK_TECHNIQUES,
    });
    mockPickerHooks();
  });

  it('lists available techniques for selection', async () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => {
      expect(screen.getByText('Tidal Fury')).toBeInTheDocument();
      expect(screen.getByText('Storm Surge')).toBeInTheDocument();
    });
  });

  it('emits onContextChange when a technique is selected', async () => {
    const onContextChange = vi.fn();
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={onContextChange}
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => screen.getByText('Tidal Fury'));
    await userEvent.click(screen.getByText('Tidal Fury'));

    expect(onContextChange).toHaveBeenCalledWith(expect.objectContaining({ techniqueId: 101 }));
  });

  it('highlights the selected technique', async () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ techniqueId: 101 })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    await waitFor(() => screen.getByText('Tidal Fury'));

    const tidalFuryBtn = screen.getByText('Tidal Fury').closest('button');
    expect(tidalFuryBtn).toHaveClass('border-primary');
  });

  it('marks a readied ultimate in the picker (#4098)', async () => {
    mockedFetchActions.mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          ...MOCK_TECHNIQUES[0],
          display_name: 'Cinder Crown',
          is_ultimate: true,
        },
      ],
    });

    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    const button = await screen.findByRole('button', { name: /Cinder Crown/ });
    expect(button).toHaveClass('border-fuchsia-500/60');
    expect(within(button).getByTestId('ultimate-chip-mark')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Task 5.3 — effort selector
// ---------------------------------------------------------------------------

describe('ActionDeclarationCard — Task 5.3 effort selector', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    mockPickerHooks();
  });

  it('renders all five effort pills', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('Very Low')).toBeInTheDocument();
    expect(screen.getByText('Low')).toBeInTheDocument();
    expect(screen.getByText('Medium')).toBeInTheDocument();
    expect(screen.getByText('High')).toBeInTheDocument();
    expect(screen.getByText('Very High')).toBeInTheDocument();
  });

  it('highlights the currently selected effort', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ effort: 'HIGH' })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    const highPill = screen.getByText('High').closest('button');
    expect(highPill).toHaveClass('bg-primary');
  });

  it('emits onContextChange when effort pill is clicked', async () => {
    const onContextChange = vi.fn();
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ effort: 'MEDIUM' })}
        onContextChange={onContextChange}
      />,
      { wrapper: createWrapper() }
    );

    await userEvent.click(screen.getByText('Low'));
    expect(onContextChange).toHaveBeenCalledWith(expect.objectContaining({ effort: 'LOW' }));
  });
});

// ---------------------------------------------------------------------------
// #3446 — strain slider (push-yourself anima overcommit)
// ---------------------------------------------------------------------------

describe('ActionDeclarationCard — #3446 strain slider', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    mockPickerHooks();
  });

  it('renders no strain slider without strainMax (scene ActionPanel owns its own)', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ techniqueId: 5 })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.queryByTestId('focused-strain-slider')).not.toBeInTheDocument();
  });

  it('renders no strain slider before a technique is picked', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
        strainMax={12}
      />,
      { wrapper: createWrapper() }
    );
    expect(screen.queryByTestId('focused-strain-slider')).not.toBeInTheDocument();
  });

  it('emits onContextChange with the new strainCommitment', () => {
    const onContextChange = vi.fn();
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ techniqueId: 5 })}
        onContextChange={onContextChange}
        strainMax={12}
      />,
      { wrapper: createWrapper() }
    );

    const slider = screen.getByTestId('focused-strain-slider');
    expect(slider).toHaveAttribute('max', '12');
    fireEvent.change(slider, { target: { value: '7' } });
    expect(onContextChange).toHaveBeenCalledWith(expect.objectContaining({ strainCommitment: 7 }));
  });

  it('shows the pull burn beside the anima strain, with the power of both (#4736)', () => {
    const onBurnChange = vi.fn();
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ techniqueId: 5, strainCommitment: 2 })}
        onContextChange={() => {}}
        strainMax={12}
        strainPreview={{
          cap: 12,
          default: 0,
          base_effective_cost: 4,
          conversion_base: 3,
          diminishing_step: 5,
          diminishing_floor: 1,
        }}
        strainBurn={{
          preview: {
            ceiling: 5,
            strain_units_per_point: '1.5',
            hasty_fall: false,
            available: true,
            resonance_name: 'Dawnlight',
            off_affinity: false,
            corruption_affinity_name: null,
            ceiling_tier_name: 'Amplified',
          },
          value: 3,
          onChange: onBurnChange,
        }}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('pull-burn-label')).toHaveTextContent('Dawnlight (yours)');
    expect(screen.getByTestId('pull-burn-ceiling')).toHaveTextContent(
      'Burn ceiling at Amplified: 5 resonance'
    );
    // 2 anima strain + floor(3 x 1.5) = 6 units: 5 at 3 power, 1 at 2.
    expect(screen.getByTestId('pull-burn-power')).toHaveTextContent('up to +17 power');
    fireEvent.change(screen.getByTestId('pull-burn-input'), { target: { value: '4' } });
    expect(onBurnChange).toHaveBeenLastCalledWith(4);
  });
});

// ---------------------------------------------------------------------------
// Task 5.3 — intensity/control chip
// ---------------------------------------------------------------------------

describe('ActionDeclarationCard — runtime I/C chip (#4799)', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({
      count: MOCK_TECHNIQUES.length,
      next: null,
      previous: null,
      results: MOCK_TECHNIQUES,
    });
    mockPickerHooks();
  });

  function renderCard(techniqueId?: number) {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ techniqueId })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );
  }

  it('shows the intensity and control the cast runs at, not its authored stats', async () => {
    renderCard(101);

    const chip = await screen.findByTestId('ic-chip');
    expect(chip).toHaveTextContent('I:33 / C:26');
    expect(chip).toHaveClass('bg-amber-500/20');
  });

  it('shows a neutral chip when control meets intensity', async () => {
    renderCard(102);

    const chip = await screen.findByTestId('ic-chip');
    expect(chip).toHaveTextContent('I:4 / C:7');
    expect(chip).not.toHaveClass('bg-amber-500/20');
  });

  it('does not render the chip when no technique is selected', async () => {
    renderCard();

    expect(await screen.findByText('(select a technique first)')).toBeInTheDocument();
    expect(screen.queryByTestId('ic-chip')).not.toBeInTheDocument();
  });
});

describe('ActionDeclarationCard — runtime cost line (#4799)', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({
      count: MOCK_TECHNIQUES.length,
      next: null,
      previous: null,
      results: MOCK_TECHNIQUES,
    });
    mockPickerHooks();
  });

  function renderCard(techniqueId?: number) {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ techniqueId })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );
  }

  it('shows the anima the cast will cost', async () => {
    renderCard(101);

    expect(await screen.findByText('Cost: 8 anima')).toBeInTheDocument();
  });

  it('shows a free cast as costing nothing', async () => {
    renderCard(102);

    expect(await screen.findByText('Cost: 0 anima')).toBeInTheDocument();
  });

  it('hides the cost line when no technique is selected', async () => {
    renderCard();

    expect(await screen.findByText('(select a technique first)')).toBeInTheDocument();
    expect(screen.queryByText(/anima$/)).not.toBeInTheDocument();
  });

  it('says the cost is unavailable when the technique has no preview', async () => {
    renderCard(999);

    expect(await screen.findByText('Cost unavailable')).toBeInTheDocument();
    expect(screen.queryByTestId('ic-chip')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Task 6.4 — ThreadPullPicker integration
// ---------------------------------------------------------------------------

describe('ActionDeclarationCard — Task 6.4 ThreadPullPicker section', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({
      count: MOCK_TECHNIQUES.length,
      next: null,
      previous: null,
      results: MOCK_TECHNIQUES,
    });
    mockPickerHooks();
  });

  it('renders the ThreadPullPicker stub inside the Thread Pulls section', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('thread-pull-picker-stub')).toBeInTheDocument();
  });

  it('does not render the picker when characterSheetId is 0', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={0}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByTestId('thread-pull-picker-stub')).not.toBeInTheDocument();
    expect(screen.getByText(/no sheet context/i)).toBeInTheDocument();
  });

  it('renders with a technique selected and provides characterSheetId context', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={5}
        actionContext={emptyContext({ techniqueId: 101 })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    // The stubbed picker should be visible
    expect(screen.getByTestId('thread-pull-picker-stub')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// #1001a — single-target focused picker
// ---------------------------------------------------------------------------

describe('ActionDeclarationCard — #1001a combatant target picker', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    mockPickerHooks();
  });

  const TARGETS = [
    { id: 7, kind: 'opponent' as const, name: 'Bandit Captain', objectId: 42 },
    { id: 9, kind: 'ally' as const, name: 'Sir Alaric' },
  ];

  it('falls back to the kind-only selector when no targets are provided', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByTestId('combatant-target-picker')).not.toBeInTheDocument();
    expect(screen.getByRole('option', { name: /no target/i })).toBeInTheDocument();
  });

  it('lists opponents and allies when targets are provided', () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
        targets={TARGETS}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByTestId('combatant-target-picker')).toBeInTheDocument();
    expect(screen.getByText('Bandit Captain')).toBeInTheDocument();
    expect(screen.getByText('Sir Alaric')).toBeInTheDocument();
  });

  it('emits the picked opponent kind + dispatch PK on selection', async () => {
    const onContextChange = vi.fn();
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={onContextChange}
        targets={TARGETS}
      />,
      { wrapper: createWrapper() }
    );

    await userEvent.click(screen.getByText('Bandit Captain'));
    expect(onContextChange).toHaveBeenCalledWith(
      expect.objectContaining({ targetKind: 'opponent', targetId: 7 })
    );
  });

  it('emits the picked ally kind + participant PK on selection', async () => {
    const onContextChange = vi.fn();
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={onContextChange}
        targets={TARGETS}
      />,
      { wrapper: createWrapper() }
    );

    await userEvent.click(screen.getByText('Sir Alaric'));
    expect(onContextChange).toHaveBeenCalledWith(
      expect.objectContaining({ targetKind: 'ally', targetId: 9 })
    );
  });

  it('shows the hop distance on a target disabled by reach (#3555)', () => {
    const adjacency = [
      { position_id: 1, adjacent_position_ids: [2] },
      { position_id: 2, adjacent_position_ids: [1, 3] },
      { position_id: 3, adjacent_position_ids: [2] },
      { position_id: 9, adjacent_position_ids: [] },
    ];
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
        targets={[
          { id: 7, kind: 'opponent', name: 'Bandit Captain', positionId: 3 },
          { id: 8, kind: 'opponent', name: 'Bandit Archer', positionId: 9 },
          { id: 9, kind: 'ally', name: 'Sir Alaric', positionId: 1 },
        ]}
        reach="same"
        actorPositionId={1}
        positionAdjacency={adjacency}
      />,
      { wrapper: createWrapper() }
    );

    const captain = screen.getByRole('button', { name: /Bandit Captain/ });
    expect(captain).toBeDisabled();
    expect(captain).toHaveAttribute('title', 'Out of reach for this technique (2 positions away)');
    expect(captain).toHaveTextContent('2 positions away');

    const archer = screen.getByRole('button', { name: /Bandit Archer/ });
    expect(archer).toBeDisabled();
    expect(archer).toHaveAttribute('title', 'Out of reach for this technique (no path)');
    expect(archer).not.toHaveTextContent('away');

    const alaric = screen.getByRole('button', { name: /Sir Alaric/ });
    expect(alaric).toBeEnabled();
    expect(alaric).not.toHaveAttribute('title');
  });

  it('clears the selected target', async () => {
    const onContextChange = vi.fn();
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ targetKind: 'opponent', targetId: 7 })}
        onContextChange={onContextChange}
        targets={TARGETS}
      />,
      { wrapper: createWrapper() }
    );

    await userEvent.click(screen.getByText(/clear target/i));
    expect(onContextChange).toHaveBeenCalledWith(
      expect.objectContaining({ targetKind: undefined, targetId: undefined })
    );
  });
});

describe('ActionDeclarationCard: a leading pick (combat Strike, #4858)', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({
      count: MOCK_TECHNIQUES.length,
      next: null,
      previous: null,
      results: MOCK_TECHNIQUES,
    });
    mockPickerHooks();
  });

  it('puts the pick first in the row, ahead of the techniques', async () => {
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
        leadingPick={{ label: 'Strike', selected: false, onSelect: () => {}, panel: null }}
      />,
      { wrapper: createWrapper() }
    );

    await screen.findByText('Tidal Fury');
    expect(screen.getByText('Your action')).toBeInTheDocument();
    const row = screen.getByTestId('leading-pick').parentElement as HTMLElement;
    expect(row.firstElementChild).toBe(screen.getByTestId('leading-pick'));
    expect(within(row).getByText('Tidal Fury')).toBeInTheDocument();
  });

  it('shows its panel under the row when picked, and drops the technique-only sections', async () => {
    const onSelect = vi.fn();
    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
        targets={[]}
        leadingPick={{
          label: 'Strike',
          selected: true,
          onSelect,
          panel: <div data-testid="strike-panel">With</div>,
        }}
      />,
      { wrapper: createWrapper() }
    );

    await screen.findByText('Tidal Fury');
    expect(screen.getByTestId('strike-panel')).toBeInTheDocument();
    expect(screen.getByTestId('leading-pick')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Target')).toBeInTheDocument();
    expect(screen.queryByText('Effort')).not.toBeInTheDocument();
    expect(screen.queryByText('Thread Pulls')).not.toBeInTheDocument();
    await userEvent.click(screen.getByTestId('leading-pick'));
    expect(onSelect).toHaveBeenCalled();
  });
});
