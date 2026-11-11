import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ThreadPullDialog } from '../ThreadPullDialog';
import { previewPull } from '../../../api';

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
      resonance_name: 'Flamevein',
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
      id: 4,
      name: 'Step Strand',
      target_kind: 'TECHNIQUE',
      target_technique_id: 41,
      target_trait_id: null,
      resonance: 7,
      owner: 12,
      retired_at: null,
      level: 10,
    },
    {
      id: 5,
      name: 'Lash Strand',
      target_kind: 'TECHNIQUE',
      target_technique_id: 99,
      target_trait_id: null,
      resonance: 7,
      owner: 12,
      retired_at: null,
      level: 10,
    },
    {
      id: 6,
      name: 'Tide Bond',
      target_kind: 'FACET',
      resonance: 9,
      resonance_name: 'Tidecall',
      owner: 12,
      retired_at: null,
      level: 4,
    },
    {
      id: 7,
      name: 'Stone Bond',
      target_kind: 'FACET',
      resonance: 8,
      resonance_name: 'Stoneheart',
      owner: 12,
      retired_at: null,
      level: 4,
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
  { resonance: 9, resonance_name: 'Tidecall', balance: 5 },
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

  it('lists eligible threads of every resonance with a balance, no resonance to pick', () => {
    render(<ThreadPullDialog {...defaultProps} />);
    expect(screen.queryByTestId('resonance-selector')).not.toBeInTheDocument();
    expect(screen.getByTestId('thread-checkbox-1')).toHaveTextContent('Flamevein');
    expect(screen.getByTestId('thread-checkbox-6')).toHaveTextContent('Tidecall');
    // Stoneheart has balance 0: its thread is not offered.
    expect(screen.queryByTestId('thread-checkbox-7')).not.toBeInTheDocument();
  });

  it('TRAIT thread not shown for always-in-action filter (no combat prop)', () => {
    render(<ThreadPullDialog {...defaultProps} />);
    expect(screen.getByTestId('thread-checkbox-1')).toBeInTheDocument();
    expect(screen.queryByTestId('thread-checkbox-2')).not.toBeInTheDocument();
  });

  it('in combat, offers a technique thread only when its technique is involved (#5066)', () => {
    render(
      <ThreadPullDialog
        {...defaultProps}
        combat={{
          encounterId: 1,
          participantId: 1,
          involvedTraitIds: [],
          involvedTechniqueIds: [41],
        }}
      />
    );
    expect(screen.getByTestId('thread-checkbox-4')).toBeInTheDocument();
    expect(screen.queryByTestId('thread-checkbox-5')).not.toBeInTheDocument();
    expect(screen.queryByTestId('thread-checkbox-2')).not.toBeInTheDocument();
  });

  it('selects threads of two resonances in one pull (#5066)', async () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    render(<ThreadPullDialog {...defaultProps} onSelect={onSelect} onClose={onClose} />);

    fireEvent.click(within(screen.getByTestId('thread-checkbox-1')).getByRole('checkbox'));
    fireEvent.click(within(screen.getByTestId('thread-checkbox-6')).getByRole('checkbox'));

    await waitFor(() => {
      expect(screen.getByTestId('commit-pull-btn')).not.toBeDisabled();
    });
    expect(previewPull).toHaveBeenLastCalledWith({
      character_sheet_id: 12,
      tier: 1,
      thread_ids: [1, 6],
    });

    fireEvent.click(screen.getByTestId('commit-pull-btn'));

    expect(onSelect).toHaveBeenCalledWith({
      tier: 1,
      thread_ids: [1, 6],
      resonances: [
        { id: 7, name: 'Flamevein' },
        { id: 9, name: 'Tidecall' },
      ],
    });
    expect(onClose).toHaveBeenCalled();
  });

  it('retired threads are never shown', () => {
    render(<ThreadPullDialog {...defaultProps} />);
    expect(screen.queryByTestId('thread-checkbox-3')).not.toBeInTheDocument();
  });

  it('commit button disabled until a thread is selected and affordable', async () => {
    render(<ThreadPullDialog {...defaultProps} />);
    expect(screen.getByTestId('commit-pull-btn')).toBeDisabled();

    fireEvent.click(within(screen.getByTestId('thread-checkbox-1')).getByRole('checkbox'));

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
