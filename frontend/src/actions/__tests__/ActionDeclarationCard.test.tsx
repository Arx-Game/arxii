/**
 * Tests for ActionDeclarationCard — Phase 5.1, 5.2, and 5.3.
 *
 * Mocks:
 * - @/scenes/actionQueries.fetchAvailableActions  (technique list)
 * - @/magic/queries.useTechnique + useApplicablePulls + useThreads
 * - @/magic/components/threads/ThreadPullPicker   (stub to isolate card tests)
 *
 * The card uses useTechnique (a React Query hook), so we mock the queries
 * module directly to control what technique detail the card sees synchronously.
 * ThreadPullPicker is stubbed so Phase 5 tests don't break due to Phase 6
 * threading complexity.
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';
import { ActionDeclarationCard } from '../ActionDeclarationCard';
import type { ActionContext } from '../types';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('@/scenes/actionQueries', () => ({
  fetchAvailableActions: vi.fn(),
}));

// Mock the entire magic queries module to control useTechnique, useApplicablePulls,
// useThreads, and useCharacterResonances synchronously.
vi.mock('@/magic/queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/magic/queries')>();
  return {
    ...actual,
    useTechnique: vi.fn(),
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
const mockedUseTechnique = magicQueries.useTechnique as ReturnType<typeof vi.fn>;
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
  },
];

// intensity=8, control=5 → overburn (I > C)
const TECHNIQUE_OVERBURN = {
  id: 101,
  name: 'Tidal Fury',
  gift: 1,
  style: 1,
  effect_type: 1,
  level: 1,
  intensity: 8,
  control: 5,
  anima_cost: 3,
  tier: 1,
};

// intensity=4, control=7 → comfortable (C >= I)
const TECHNIQUE_COMFORTABLE = {
  id: 102,
  name: 'Storm Surge',
  gift: 1,
  style: 1,
  effect_type: 1,
  level: 1,
  intensity: 4,
  control: 7,
  anima_cost: 1,
  tier: 1,
};

function mockUseTechnique(data: typeof TECHNIQUE_OVERBURN | null) {
  mockedUseTechnique.mockReturnValue({ data, isLoading: false, isError: false });
}

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
    mockUseTechnique(null);
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
    mockUseTechnique(null);
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
});

// ---------------------------------------------------------------------------
// Task 5.3 — effort selector
// ---------------------------------------------------------------------------

describe('ActionDeclarationCard — Task 5.3 effort selector', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({ count: 0, next: null, previous: null, results: [] });
    mockUseTechnique(null);
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
// Task 5.3 — intensity/control chip
// ---------------------------------------------------------------------------

describe('ActionDeclarationCard — Task 5.3 I/C chip', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({
      count: MOCK_TECHNIQUES.length,
      next: null,
      previous: null,
      results: MOCK_TECHNIQUES,
    });
    mockPickerHooks();
  });

  it('shows warning chip when intensity exceeds control', () => {
    mockUseTechnique(TECHNIQUE_OVERBURN); // I:8 > C:5

    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ techniqueId: 101 })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    const chip = screen.getByTestId('ic-chip');
    expect(chip).toBeInTheDocument();
    expect(chip).toHaveTextContent('I:8 / C:5');
    expect(chip).toHaveClass('bg-amber-500/20');
  });

  it('shows neutral chip when control >= intensity', () => {
    mockUseTechnique(TECHNIQUE_COMFORTABLE); // I:4, C:7

    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ techniqueId: 102 })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    const chip = screen.getByTestId('ic-chip');
    expect(chip).toHaveTextContent('I:4 / C:7');
    expect(chip).not.toHaveClass('bg-amber-500/20');
  });

  it('does not render chip when no technique is selected', () => {
    mockUseTechnique(null);

    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByTestId('ic-chip')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Task 5.3 — cost preview line
// ---------------------------------------------------------------------------

describe('ActionDeclarationCard — Task 5.3 cost preview', () => {
  beforeEach(() => {
    mockedFetchActions.mockResolvedValue({
      count: MOCK_TECHNIQUES.length,
      next: null,
      previous: null,
      results: MOCK_TECHNIQUES,
    });
    mockPickerHooks();
  });

  it('hides the cost line when no technique is selected', () => {
    mockUseTechnique(null);

    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext()}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.queryByText(/0 anima/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/overburn/i)).not.toBeInTheDocument();
  });

  it('shows comfortable cost line when control >= intensity', () => {
    mockUseTechnique(TECHNIQUE_COMFORTABLE); // I:4, C:7

    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ techniqueId: 102 })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/0 anima/i)).toBeInTheDocument();
    expect(screen.getByText(/comfortable/i)).toBeInTheDocument();
  });

  it('shows overburn cost line when intensity > control', () => {
    mockUseTechnique(TECHNIQUE_OVERBURN); // I:8 > C:5

    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ techniqueId: 101 })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/overburn/i)).toBeInTheDocument();
  });

  it('shows "Cost unavailable" when useTechnique errors instead of "Loading cost..."', () => {
    mockedUseTechnique.mockReturnValue({ data: undefined, isLoading: false, isError: true });

    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ techniqueId: 101 })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText(/cost unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText(/loading cost/i)).not.toBeInTheDocument();
  });

  it('does not render I/C chip when useTechnique errors', () => {
    mockedUseTechnique.mockReturnValue({ data: undefined, isLoading: false, isError: true });

    render(
      <ActionDeclarationCard
        characterId={1}
        characterSheetId={1}
        actionContext={emptyContext({ techniqueId: 101 })}
        onContextChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

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
    mockUseTechnique(null);
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
