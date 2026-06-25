import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi } from 'vitest';
import { RoundSettingsDialog } from './RoundSettingsDialog';
import type { SceneDetail, SceneRoundState } from '../types';

// Mock the queries module so no real network calls happen
vi.mock('../queries', async (importOriginal) => {
  const original = await importOriginal<typeof import('../queries')>();
  return {
    ...original,
    setRoundMode: vi.fn().mockResolvedValue({}),
  };
});

function renderWith(scene: SceneDetail) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <RoundSettingsDialog scene={scene} />
    </QueryClientProvider>
  );
}

const base: SceneDetail = {
  id: 1,
  name: 'S',
  description: '',
  date_started: '',
  participants: [],
  is_active: true,
  is_owner: true,
  viewer_can_gm: true,
  positions: [],
  position_adjacency: [],
  persona_positions: [],
  active_round: null,
} as unknown as SceneDetail;

const activeRound: SceneRoundState = {
  mode: 'pose_order',
  advance_quorum_pct: 60,
  max_actions_per_round: 1,
  per_target_repeat_lock: false,
  status: 'open',
  round_number: 1,
  is_danger: false,
};

describe('RoundSettingsDialog', () => {
  it('shows the trigger for a GM/owner of an active scene', () => {
    renderWith({ ...base, active_round: null });
    expect(screen.getByRole('button', { name: /round settings/i })).toBeInTheDocument();
  });

  it('renders nothing when the viewer cannot GM', () => {
    const { container } = renderWith({ ...base, viewer_can_gm: false, active_round: null });
    expect(container).toBeEmptyDOMElement();
  });

  it('renders nothing when the scene is not active', () => {
    const { container } = renderWith({ ...base, is_active: false, active_round: null });
    expect(container).toBeEmptyDOMElement();
  });

  it('Save is disabled in the no-active-round state', async () => {
    // Radix Dialog sets pointer-events: none on <body> while closed;
    // disable the userEvent pointer-events guard so we can click in jsdom.
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    renderWith({ ...base, active_round: null });

    // Open the dialog
    await user.click(screen.getByRole('button', { name: /round settings/i }));

    // Wait for the dialog content to appear
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save/i })).toBeInTheDocument();
    });

    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();
  });

  it('shows the "no active round" message when active_round is null', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    renderWith({ ...base, active_round: null });

    await user.click(screen.getByRole('button', { name: /round settings/i }));

    await waitFor(() => {
      expect(screen.getByText(/no active round/i)).toBeInTheDocument();
    });
  });

  it('shows the mode select when there is an active round', async () => {
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    renderWith({ ...base, active_round: activeRound });

    await user.click(screen.getByRole('button', { name: /round settings/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/mode/i)).toBeInTheDocument();
    });
  });

  it('lets a GM reconfigure a danger round (mode select and Save enabled)', async () => {
    // After #1466 a danger round is an ordinary STRICT round: fully reconfigurable.
    const user = userEvent.setup({ pointerEventsCheck: 0 });
    const dangerRound: SceneRoundState = {
      ...activeRound,
      mode: 'strict',
      is_danger: true,
    };
    renderWith({ ...base, active_round: dangerRound });

    await user.click(screen.getByRole('button', { name: /round settings/i }));

    await waitFor(() => {
      expect(screen.getByLabelText(/mode/i)).toBeInTheDocument();
    });

    const trigger = screen.getByLabelText(/mode/i);
    expect(trigger).not.toHaveAttribute('disabled');

    expect(screen.getByRole('button', { name: /save/i })).toBeEnabled();

    // The danger context note is shown, but it never locks the controls.
    expect(screen.getByText(/started by an unfolding danger/i)).toBeInTheDocument();
  });
});
