import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

// Top-level mocks BEFORE importing the component (mirrors ActionPanel.test.tsx).
vi.mock('../api', () => ({
  fetchTreatmentCandidates: vi.fn(),
}));

vi.mock('@/scenes/actionQueries', () => ({
  createActionRequest: vi.fn(),
  TREAT_CONDITION_ACTION_KEY: 'treat_condition',
}));

// Mock the roster query — component resolves active character → characterId +
// primary_persona_id for the discovery header and request body.
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'TestChar',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: 77,
        active_persona_id: 77,
      },
    ],
  })),
}));

// Mock the Redux selector — return the active character name used above.
vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({ game: { active: 'TestChar' }, auth: {} })
  ),
}));

import { fetchTreatmentCandidates } from '../api';
import { createActionRequest } from '@/scenes/actionQueries';
import { TreatActionPanel } from './TreatActionPanel';
import type { TreatmentCandidatesResponse } from '../api';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

/** A single condition-target candidate with a bond thread. */
function makeConditionCandidate(
  overrides: Partial<TreatmentCandidatesResponse['candidates'][0]> = {}
): TreatmentCandidatesResponse['candidates'][0] {
  return {
    treatment: {
      id: 10,
      key: 'staunch_bleeding',
      name: 'Staunch Bleeding',
      description: 'Stop the bleeding.',
      target_kind: 'primary',
      requires_bond: false,
      resonance_cost: 0,
      anima_cost: 2,
      scene_required: true,
      target_condition: 5,
    },
    target_effect_type: 'condition',
    target_effect: { id: 88, name: 'Bleeding' },
    bond_thread: null,
    scene_id: 42,
    ...overrides,
  };
}

const MOCK_RESPONSE: TreatmentCandidatesResponse = {
  candidates: [makeConditionCandidate()],
  scene_id: 42,
};

describe('TreatActionPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading then candidates', async () => {
    vi.mocked(fetchTreatmentCandidates).mockResolvedValue(MOCK_RESPONSE);

    render(<TreatActionPanel sceneId="42" targetPersonaId={100} />, {
      wrapper: createWrapper(),
    });

    // Loading state first (query is enabled: targetPersonaId + characterId both set).
    await waitFor(() => {
      expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    // Then the candidate appears.
    await waitFor(() => {
      expect(screen.getByText('Staunch Bleeding')).toBeInTheDocument();
    });
    expect(screen.getByText(/on Bleeding/)).toBeInTheDocument();
    expect(fetchTreatmentCandidates).toHaveBeenCalledWith(100, 42);
  });

  it('clicking Offer calls createActionRequest with the right action_key and ids', async () => {
    vi.mocked(fetchTreatmentCandidates).mockResolvedValue(MOCK_RESPONSE);
    vi.mocked(createActionRequest).mockResolvedValue({ status: 'pending', request_id: 999 });
    const user = userEvent.setup();

    render(<TreatActionPanel sceneId="42" targetPersonaId={100} />, {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /offer/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /offer/i }));

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith(
        '42',
        expect.objectContaining({
          action_key: 'treat_condition',
          initiator_persona: 77,
          target_persona_id: 100,
          treatment_id: 10,
          target_condition_instance_id: 88,
        })
      );
    });
    // Alteration id must NOT be set for a condition candidate.
    const call = vi.mocked(createActionRequest).mock.calls[0][1];
    expect(call).not.toHaveProperty('target_pending_alteration_id');

    // Success confirmation surfaces the request id.
    await waitFor(() => {
      expect(screen.getByText(/awaiting response \(request #999\)/)).toBeInTheDocument();
    });
  });

  it('sends target_pending_alteration_id (not condition) for an alteration candidate', async () => {
    const alterationResponse: TreatmentCandidatesResponse = {
      candidates: [
        makeConditionCandidate({
          target_effect_type: 'alteration',
          target_effect: { id: 200, character_name: 'Touched Scar' },
          bond_thread: 33,
          treatment: {
            id: 11,
            key: 'soothe_alteration',
            name: 'Soothe Alteration',
            description: '',
            target_kind: 'pending_alteration',
            requires_bond: true,
            resonance_cost: 1,
            anima_cost: 3,
            scene_required: false,
            target_condition: null,
          },
        }),
      ],
      scene_id: 42,
    };
    vi.mocked(fetchTreatmentCandidates).mockResolvedValue(alterationResponse);
    vi.mocked(createActionRequest).mockResolvedValue({ status: 'pending' });
    const user = userEvent.setup();

    render(<TreatActionPanel sceneId="42" targetPersonaId={100} />, {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /offer/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /offer/i }));

    await waitFor(() => {
      expect(createActionRequest).toHaveBeenCalledWith(
        '42',
        expect.objectContaining({
          action_key: 'treat_condition',
          treatment_id: 11,
          target_pending_alteration_id: 200,
          bond_thread_id: 33,
        })
      );
    });
    // Condition id must NOT be set for an alteration candidate.
    const call = vi.mocked(createActionRequest).mock.calls[0][1];
    expect(call).not.toHaveProperty('target_condition_instance_id');
  });

  it('renders "No treatable conditions." when the candidate list is empty', async () => {
    vi.mocked(fetchTreatmentCandidates).mockResolvedValue({ candidates: [], scene_id: 42 });

    render(<TreatActionPanel sceneId="42" targetPersonaId={100} />, {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(screen.getByText('No treatable conditions.')).toBeInTheDocument();
    });
  });

  it('renders the destructive error text when the mutation rejects', async () => {
    vi.mocked(fetchTreatmentCandidates).mockResolvedValue(MOCK_RESPONSE);
    vi.mocked(createActionRequest).mockRejectedValue(new Error('You are not in an active scene.'));
    const user = userEvent.setup();

    render(<TreatActionPanel sceneId="42" targetPersonaId={100} />, {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /offer/i })).toBeInTheDocument();
    });
    await user.click(screen.getByRole('button', { name: /offer/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(screen.getByRole('alert')).toHaveTextContent('You are not in an active scene.');
  });

  it('renders the select-target prompt when targetPersonaId is null', () => {
    vi.mocked(fetchTreatmentCandidates).mockResolvedValue(MOCK_RESPONSE);
    render(<TreatActionPanel sceneId="42" targetPersonaId={null} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByText('Select a target to offer treatment.')).toBeInTheDocument();
    expect(fetchTreatmentCandidates).not.toHaveBeenCalled();
  });
});
