import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { ActionRequest } from '../actionTypes';

// Mock Radix Select to avoid jsdom portal/pointer-event issues in tests.
vi.mock('@/components/ui/select', () => ({
  Select: ({
    value,
    onValueChange,
    children,
  }: {
    value?: string;
    onValueChange?: (v: string) => void;
    children?: React.ReactNode;
  }) => (
    <select
      value={value}
      onChange={(e) => onValueChange?.(e.target.value)}
      data-testid="mock-resist-select"
    >
      {children}
    </select>
  ),
  SelectTrigger: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectValue: () => null,
  SelectContent: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectItem: ({ value, children }: { value: string; children?: React.ReactNode }) => (
    <option value={value}>{children}</option>
  ),
  SelectLabel: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  SelectSeparator: () => null,
}));

vi.mock('../actionQueries', () => ({
  fetchPendingRequests: vi.fn(),
  fetchPendingTargets: vi.fn(),
  respondToRequest: vi.fn(),
}));

import { fetchPendingRequests, fetchPendingTargets, respondToRequest } from '../actionQueries';
import type { PendingActionTarget } from '../actionTypes';
import { ConsentPrompt } from './ConsentPrompt';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

const MOCK_REQUEST: ActionRequest = {
  id: 7,
  initiator_persona: 1,
  initiator_name: 'Darth Maul',
  action_key: 'Intimidate',
  technique: null,
  technique_name: null,
  created_at: '2026-03-22T12:00:00Z',
  strain_commitment: 0,
};

const MOCK_REQUEST_WITH_TECHNIQUE: ActionRequest = {
  id: 8,
  initiator_persona: 2,
  initiator_name: 'Gandalf',
  action_key: 'Enchant',
  technique: 9,
  technique_name: 'Mind Whisper',
  created_at: '2026-03-22T12:05:00Z',
  strain_commitment: 0,
};

describe('ConsentPrompt', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(fetchPendingTargets).mockResolvedValue({ results: [] });
  });

  it('shows nothing when no pending requests', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [] });

    const { container } = render(<ConsentPrompt sceneId="42" />, {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(fetchPendingRequests).toHaveBeenCalledWith('42');
    });

    // Component returns null when empty
    expect(container.innerHTML).toBe('');
  });

  it('shows prompt when a pending request exists', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Darth Maul')).toBeInTheDocument();
    });
    expect(screen.getByText('Intimidate')).toBeInTheDocument();
  });

  it('displays initiator name and action name', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Darth Maul')).toBeInTheDocument();
    });
    expect(screen.getByText('Intimidate')).toBeInTheDocument();
    expect(screen.getByText(/on your character/)).toBeInTheDocument();
  });

  it('displays technique name when present', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({
      results: [MOCK_REQUEST_WITH_TECHNIQUE],
    });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Gandalf')).toBeInTheDocument();
    });
    expect(screen.getByText(/Mind Whisper/)).toBeInTheDocument();
  });

  it('clicking Deny calls respondToRequest with accept: false', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Deny')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Deny'));

    await waitFor(() => {
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: false,
      });
    });
  });

  it('clicking Accept (neutral) calls respondToRequest with difficulty: normal', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getAllByText('Accept').length).toBeGreaterThan(0);
    });

    // The first Accept button in the primary card is the neutral one.
    await user.click(screen.getAllByText('Accept')[0]);

    await waitFor(() => {
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: true,
        difficulty: 'normal',
      });
    });
  });

  it('clicking "It works" band calls respondToRequest with difficulty: easy', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('It works')).toBeInTheDocument();
    });

    await user.click(screen.getByText('It works'));

    await waitFor(() => {
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: true,
        difficulty: 'easy',
      });
    });
  });

  it('clicking "Hard but possible" band calls respondToRequest with difficulty: hard', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Hard but possible')).toBeInTheDocument();
    });

    await user.click(screen.getByText('Hard but possible'));

    await waitFor(() => {
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: true,
        difficulty: 'hard',
      });
    });
  });

  it('clicking "No way" band calls respondToRequest with difficulty: daunting', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('No way')).toBeInTheDocument();
    });

    await user.click(screen.getByText('No way'));

    await waitFor(() => {
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: true,
        difficulty: 'daunting',
      });
    });
  });

  it('shows a risk warning when combat_risk_level is set', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({
      results: [{ ...MOCK_REQUEST, combat_risk_level: 'lethal' }],
    });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText(/LETHAL/)).toBeInTheDocument();
    });
    expect(screen.getByText(/wades your character into the combat encounter/)).toBeInTheDocument();
  });

  it('does NOT show a risk warning when combat_risk_level is null', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({
      results: [{ ...MOCK_REQUEST, combat_risk_level: null }],
    });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Darth Maul')).toBeInTheDocument();
    });
    expect(screen.queryByText(/wades your character/i)).not.toBeInTheDocument();
  });

  it('renders multiple pending requests', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({
      results: [MOCK_REQUEST, MOCK_REQUEST_WITH_TECHNIQUE],
    });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText('Darth Maul')).toBeInTheDocument();
    });
    expect(screen.getByText('Gandalf')).toBeInTheDocument();
  });
  it('shows strain text when strain_commitment > 0 (#892 merged from __tests__ dup)', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({
      results: [{ ...MOCK_REQUEST, initiator_name: 'Mara', strain_commitment: 3 }],
    });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText(/Mara is committing 3 strain/i)).toBeInTheDocument();
    });
  });

  it('does NOT show strain text when strain_commitment === 0 (#892 merged from __tests__ dup)', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({
      results: [{ ...MOCK_REQUEST, strain_commitment: 0 }],
    });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(screen.getByText(/Darth Maul/)).toBeInTheDocument();
    });
    expect(screen.queryByText(/committing/i)).not.toBeInTheDocument();
  });

  const MOCK_TARGET: PendingActionTarget = {
    action_target_id: 50,
    action_request_id: 12,
    target_persona_id: 99,
    status: 'pending',
    initiator_persona: 3,
    initiator_name: 'Morgan',
    scene: 42,
    action_key: 'Hex',
    action_template: 1,
    technique: null,
    technique_name: null,
    pose_text: 'Morgan raises a hand.',
    strain_commitment: 0,
    created_at: '2026-03-22T12:10:00Z',
  };

  it('renders a pending additional-target prompt', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [] });
    vi.mocked(fetchPendingTargets).mockResolvedValue({ results: [MOCK_TARGET] });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getByText('Morgan')).toBeInTheDocument());
    expect(screen.getByText('Hex')).toBeInTheDocument();
  });

  it('accepting a target (neutral Accept) calls respondToRequest with target_persona_id and difficulty: normal', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [] });
    vi.mocked(fetchPendingTargets).mockResolvedValue({ results: [MOCK_TARGET] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Accept')).toBeInTheDocument());
    await user.click(screen.getByText('Accept'));

    await waitFor(() =>
      expect(respondToRequest).toHaveBeenCalledWith('42', 12, {
        accept: true,
        difficulty: 'normal',
        target_persona_id: 99,
      })
    );
  });

  it('denying a target calls respondToRequest with accept:false + target_persona_id', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [] });
    vi.mocked(fetchPendingTargets).mockResolvedValue({ results: [MOCK_TARGET] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });
    const user = userEvent.setup();

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });
    await waitFor(() => expect(screen.getByText('Deny')).toBeInTheDocument());
    await user.click(screen.getByText('Deny'));

    await waitFor(() =>
      expect(respondToRequest).toHaveBeenCalledWith('42', 12, {
        accept: false,
        target_persona_id: 99,
      })
    );
  });

  it('shows the combat-risk warning on an additional target pulled into a fight', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [] });
    vi.mocked(fetchPendingTargets).mockResolvedValue({
      results: [
        {
          action_target_id: 1,
          action_request_id: 10,
          target_persona_id: 5,
          status: 'pending',
          initiator_persona: 2,
          initiator_name: 'Caster',
          scene: 1,
          action_key: '',
          action_template: null,
          technique: 7,
          technique_name: 'Firestorm',
          pose_text: '',
          strain_commitment: 0,
          combat_risk_level: 'lethal',
          created_at: '2026-06-20T00:00:00Z',
        },
      ],
    });

    render(<ConsentPrompt sceneId="1" />, { wrapper: createWrapper() });

    expect(await screen.findByText(/LETHAL risk/i)).toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Resist effort (Task 9 / C4) — active-resistance "dig in" control
  // ---------------------------------------------------------------------------

  it('selecting resist effort then clicking Accept includes resist_effort in payload', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getAllByText('Accept').length).toBeGreaterThan(0));

    // Select 'high' resistance on the primary card's select.
    const selects = screen.getAllByTestId('mock-resist-select');
    fireEvent.change(selects[0], { target: { value: 'high' } });

    await userEvent.click(screen.getAllByText('Accept')[0]);

    await waitFor(() =>
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: true,
        difficulty: 'normal',
        resist_effort: 'high',
      })
    );
  });

  it('without selecting resist effort, Accept omits resist_effort from payload', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getAllByText('Accept').length).toBeGreaterThan(0));

    // Do NOT change the select — leave it at empty/no resistance.
    await userEvent.click(screen.getAllByText('Accept')[0]);

    await waitFor(() =>
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: true,
        difficulty: 'normal',
      })
    );
  });

  it('selecting resist effort then clicking a plausibility band includes resist_effort', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getByText('It works')).toBeInTheDocument());

    const selects = screen.getAllByTestId('mock-resist-select');
    fireEvent.change(selects[0], { target: { value: 'extreme' } });

    await userEvent.click(screen.getByText('It works'));

    await waitFor(() =>
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: true,
        difficulty: 'easy',
        resist_effort: 'extreme',
      })
    );
  });

  it('deny never sends resist_effort even when resist is selected', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [MOCK_REQUEST] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getByText('Deny')).toBeInTheDocument());

    const selects = screen.getAllByTestId('mock-resist-select');
    fireEvent.change(selects[0], { target: { value: 'medium' } });

    await userEvent.click(screen.getByText('Deny'));

    await waitFor(() =>
      expect(respondToRequest).toHaveBeenCalledWith('42', 7, {
        accept: false,
      })
    );
  });

  it('resist effort on additional-target card is included when accepting via band', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [] });
    vi.mocked(fetchPendingTargets).mockResolvedValue({ results: [MOCK_TARGET] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getByText('Morgan')).toBeInTheDocument());

    const selects = screen.getAllByTestId('mock-resist-select');
    fireEvent.change(selects[0], { target: { value: 'low' } });

    await userEvent.click(screen.getByText('Accept'));

    await waitFor(() =>
      expect(respondToRequest).toHaveBeenCalledWith('42', 12, {
        accept: true,
        difficulty: 'normal',
        resist_effort: 'low',
        target_persona_id: 99,
      })
    );
  });

  it('resist effort on additional-target card omitted when none selected', async () => {
    vi.mocked(fetchPendingRequests).mockResolvedValue({ results: [] });
    vi.mocked(fetchPendingTargets).mockResolvedValue({ results: [MOCK_TARGET] });
    vi.mocked(respondToRequest).mockResolvedValue({ status: 'resolved' });

    render(<ConsentPrompt sceneId="42" />, { wrapper: createWrapper() });

    await waitFor(() => expect(screen.getByText('Accept')).toBeInTheDocument());

    // No resist effort selected — default empty.
    await userEvent.click(screen.getByText('Accept'));

    await waitFor(() =>
      expect(respondToRequest).toHaveBeenCalledWith('42', 12, {
        accept: true,
        difficulty: 'normal',
        target_persona_id: 99,
      })
    );
  });
});
