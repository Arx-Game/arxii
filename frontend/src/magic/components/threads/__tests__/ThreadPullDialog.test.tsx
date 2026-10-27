import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ThreadPullDialog } from '../ThreadPullDialog';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockThreads = {
  results: [
    {
      id: 1,
      name: 'Bond of Flame',
      target_kind: 'FACET',
      resonance: 7,
      owner: 12,
      retired_at: null,
      level: 5,
    },
    {
      id: 2,
      name: 'Earth Covenant',
      target_kind: 'TRAIT', // not always-in-action — ephemeral ineligible
      resonance: 7,
      owner: 12,
      retired_at: null,
      level: 3,
    },
    {
      id: 3,
      name: 'Fire Retired',
      target_kind: 'FACET',
      resonance: 7,
      owner: 12,
      retired_at: '2026-01-01T00:00:00Z', // retired — excluded
      level: 2,
    },
  ],
};

const mockResonances = [
  { resonance: 7, resonance_name: 'Flamevein', balance: 20, lifetime_earned: 100 },
  { resonance: 8, resonance_name: 'Stoneheart', balance: 0 }, // balance 0 — excluded
];

vi.mock('../../../queries', () => ({
  useThreads: () => ({ data: mockThreads }),
  useCharacterResonances: () => ({ data: mockResonances }),
}));

vi.mock('../../../api', () => ({
  previewPull: vi.fn().mockResolvedValue({
    resonance_cost: 6,
    anima_cost: 2,
    affordable: true,
    capped_intensity: false,
    resolved_effects: [{ kind: 'INTENSITY_BUMP', scaled_value: 20, inactive: false }],
  }),
}));

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ThreadPullDialog', () => {
  const defaultProps = {
    characterSheetId: 12,
    open: true,
    onClose: vi.fn(),
    onSelect: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the dialog when open', () => {
    render(<ThreadPullDialog {...defaultProps} />);
    expect(screen.getByTestId('thread-pull-dialog')).toBeInTheDocument();
    expect(screen.getByText('Pull Threads')).toBeInTheDocument();
  });

  it('only shows resonances with balance > 0 and eligible threads', () => {
    render(<ThreadPullDialog {...defaultProps} />);
    // Flamevein has balance 20 and eligible FACET thread → shown
    expect(screen.getByTestId('resonance-btn-7')).toBeInTheDocument();
    // Stoneheart has balance 0 → not shown
    expect(screen.queryByTestId('resonance-btn-8')).not.toBeInTheDocument();
  });

  it('TRAIT thread not shown for always-in-action filter (no combat prop)', async () => {
    render(<ThreadPullDialog {...defaultProps} />);
    fireEvent.click(screen.getByTestId('resonance-btn-7'));
    // Thread #1 (FACET) shown; Thread #2 (TRAIT) not in ALWAYS_IN_ACTION_KINDS
    await waitFor(() => {
      expect(screen.getByTestId('thread-checkbox-1')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('thread-checkbox-2')).not.toBeInTheDocument();
  });

  it('calls onSelect with resonance/tier/thread_ids when Select Pull is clicked', async () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    render(<ThreadPullDialog {...defaultProps} onSelect={onSelect} onClose={onClose} />);

    fireEvent.click(screen.getByTestId('resonance-btn-7'));
    await waitFor(() => screen.getByTestId('thread-checkbox-1'));
    fireEvent.click(screen.getByTestId('thread-checkbox-1'));

    // Wait for preview to resolve and button to be enabled
    await waitFor(() => {
      expect(screen.getByTestId('commit-pull-btn')).not.toBeDisabled();
    });

    fireEvent.click(screen.getByTestId('commit-pull-btn'));

    expect(onSelect).toHaveBeenCalledWith({
      resonance_id: 7,
      tier: 1,
      thread_ids: [1],
    });
    expect(onClose).toHaveBeenCalled();
  });

  it('retired threads are never shown', () => {
    render(<ThreadPullDialog {...defaultProps} />);
    fireEvent.click(screen.getByTestId('resonance-btn-7'));
    expect(screen.queryByTestId('thread-checkbox-3')).not.toBeInTheDocument();
  });

  it('commit button disabled until resonance + thread selected and affordable', async () => {
    render(<ThreadPullDialog {...defaultProps} />);
    const commitBtn = screen.getByTestId('commit-pull-btn');
    expect(commitBtn).toBeDisabled();

    fireEvent.click(screen.getByTestId('resonance-btn-7'));
    await waitFor(() => screen.getByTestId('thread-checkbox-1'));
    fireEvent.click(screen.getByTestId('thread-checkbox-1'));

    // After preview resolves (affordable: true), button should be enabled
    await waitFor(() => {
      expect(screen.getByTestId('commit-pull-btn')).not.toBeDisabled();
    });
  });

  it('calls onClose when Cancel is clicked', () => {
    const onClose = vi.fn();
    render(<ThreadPullDialog {...defaultProps} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));
    expect(onClose).toHaveBeenCalled();
  });
});
