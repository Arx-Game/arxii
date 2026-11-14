import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { ThreadPullDialog } from '../ThreadPullDialog';
import { previewPull } from '../../../api';
import type { PayerOption, PullPreviewResponse } from '../../../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockThreads = {
  results: [
    {
      id: 1,
      name: 'Bond of Flame',
      display_name: 'Bond of Flame',
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
      display_name: 'Earth Covenant',
      target_kind: 'TRAIT', // not always-in-action — ephemeral ineligible
      resonance: 7,
      owner: 12,
      retired_at: null,
      level: 3,
    },
    {
      id: 4,
      name: 'Step Strand',
      display_name: 'Step Strand',
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
      display_name: 'Lash Strand',
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
      display_name: 'Tide Bond',
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
      display_name: 'Stone Bond',
      target_kind: 'FACET',
      resonance: 8,
      resonance_name: 'Stoneheart',
      owner: 12,
      retired_at: null,
      level: 4,
    },
    {
      id: 10,
      name: 'Pyromancy',
      display_name: 'Pyromancy',
      target_kind: 'GIFT',
      resonance: 7,
      resonance_name: 'Flamevein',
      resonances: [
        { resonance_id: 7, resonance_name: 'Flamevein', amount: 30, leads: true },
        { resonance_id: 9, resonance_name: 'Tidecall', amount: 10, leads: false },
      ],
      owner: 12,
      retired_at: null,
      level: 3,
    },
    {
      id: 8,
      name: 'Pyre Bond',
      display_name: 'Pyre Bond',
      target_kind: 'FACET',
      resonance: 7,
      resonance_name: 'Flamevein',
      resonances: [
        { resonance_id: 7, resonance_name: 'Flamevein', amount: 30, leads: true },
        { resonance_id: 9, resonance_name: 'Tidecall', amount: 10, leads: false },
      ],
      owner: 12,
      retired_at: null,
      level: 3,
    },
    {
      id: 3,
      name: 'Fire Retired',
      display_name: 'Fire Retired',
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

  it('carries the sheet rust for a visitor with no realm, the Settle dialog way', () => {
    render(<ThreadPullDialog {...defaultProps} />);
    // The dialog portals out of `.refsheet`, so its own class holds the fallback `--primary`
    // behind the selected tier and Select Pull.
    expect(screen.getByTestId('thread-pull-dialog')).toHaveClass('thread-pull-dialog');
    const css = readFileSync(
      path.resolve(
        path.dirname(fileURLToPath(import.meta.url)),
        '..',
        '..',
        '..',
        '..',
        'character_sheets',
        'sheet.css'
      ),
      'utf8'
    );
    expect(css).toMatch(
      /:root:not\(\[data-realm\]\) \.thread-pull-dialog,\s*:root:not\(\[data-realm\]\) \.aura-settle-dialog \{\s*--primary: 10 60% 34%/
    );
    expect(css).toMatch(
      /:root:not\(\[data-realm\]\)\.dark \.thread-pull-dialog,\s*:root:not\(\[data-realm\]\)\.dark \.aura-settle-dialog \{\s*--primary: 43 45% 50%/
    );
  });

  it('renders the dialog when open', () => {
    render(<ThreadPullDialog {...defaultProps} />);
    expect(screen.getByTestId('thread-pull-dialog')).toBeInTheDocument();
    expect(screen.getByText('Pull Threads')).toBeInTheDocument();
  });

  it('lists eligible threads, and a thread stays offered while any held resonance can pay', () => {
    render(<ThreadPullDialog {...defaultProps} />);
    expect(screen.queryByTestId('resonance-selector')).not.toBeInTheDocument();
    expect(screen.getByTestId('thread-checkbox-1')).toHaveTextContent('Flamevein');
    expect(screen.getByTestId('thread-checkbox-6')).toHaveTextContent('Tidecall');
    // Stoneheart has no balance, but Flamevein can pay for its thread.
    expect(screen.getByTestId('thread-checkbox-7')).toBeInTheDocument();
  });

  it('TRAIT thread not shown for always-in-action filter (no combat prop)', () => {
    render(<ThreadPullDialog {...defaultProps} />);
    expect(screen.getByTestId('thread-checkbox-1')).toBeInTheDocument();
    expect(screen.queryByTestId('thread-checkbox-2')).not.toBeInTheDocument();
  });

  it('offers a Gift thread, the one thread every mixed character starts with (#5123)', () => {
    // The server always counts a Gift thread in action for a cast; only a social pull
    // excludes it (`exclude_gift`, #1919), and this combat dialog is not one.
    render(<ThreadPullDialog {...defaultProps} />);
    expect(screen.getByTestId('thread-checkbox-10')).toHaveTextContent('Pyromancy');
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
      payers: {},
    });
    expect(onClose).toHaveBeenCalled();
  });

  describe('payers (#5123)', () => {
    const effect = (kind: string, value: number): PayerOption['effects'][number] => ({
      kind,
      authored_value: value,
      level_multiplier: 1,
      scaled_value: value,
      vital_target: null,
      source_thread_id: 8,
      source_thread_level: 3,
      source_tier: 1,
      narrative_snippet: '',
      inactive: false,
      inactive_reason: null,
      capability_name: null,
      capability_value: null,
      resistance_damage_type_name: null,
    });
    const option = (
      id: number,
      name: string,
      balance: number,
      effects: PayerOption['effects']
    ): PayerOption => ({
      resonance_id: id,
      resonance_name: name,
      cost: 3,
      balance,
      affordable: balance >= 3,
      effects,
      level_read: 3,
    });
    const previewOf = (perThread: PullPreviewResponse['per_thread']): PullPreviewResponse => ({
      resonance_cost: 3,
      anima_cost: 1,
      affordable: true,
      capped_intensity: false,
      resolved_effects: [],
      burn: null,
      per_thread: perThread,
    });
    const pyre = (flamevein: number) => ({
      thread_id: 8,
      options: [
        option(7, 'Flamevein', flamevein, [effect('FLAT_BONUS', 4)]),
        option(9, 'Tidecall', 5, []),
      ],
    });

    beforeEach(() => {
      vi.mocked(previewPull).mockResolvedValue(previewOf([pyre(20)]));
    });

    afterEach(() => {
      vi.mocked(previewPull).mockResolvedValue({ ...previewOf([]), resonance_cost: 6 });
    });

    it('shows each payer with its perks, starting on the leading resonance', async () => {
      render(<ThreadPullDialog {...defaultProps} />);
      fireEvent.click(within(screen.getByTestId('thread-checkbox-8')).getByRole('checkbox'));
      expect(await screen.findByTestId('payer-options-8')).toBeInTheDocument();
      expect(screen.getByTestId('payer-8-7')).toHaveAttribute('aria-checked', 'true');
      expect(screen.getByTestId('payer-8-9')).toHaveAttribute('aria-checked', 'false');
      expect(screen.getByTestId('payer-perks-8-7')).toHaveTextContent('Bonus to this cast+4');
      expect(screen.getByTestId('payer-no-perks-8')).toHaveTextContent('No perks on this thread');
      expect(screen.getByTestId('thread-makeup-8')).toHaveTextContent('Level 3 · mostly Flamevein');
    });

    it('sends the picked payer in the preview and the selection', async () => {
      const onSelect = vi.fn();
      render(<ThreadPullDialog {...defaultProps} onSelect={onSelect} />);
      fireEvent.click(within(screen.getByTestId('thread-checkbox-8')).getByRole('checkbox'));
      fireEvent.click(await screen.findByTestId('payer-8-9'));
      await waitFor(() =>
        expect(previewPull).toHaveBeenLastCalledWith({
          character_sheet_id: 12,
          tier: 1,
          thread_ids: [8],
          payers: { 8: 9 },
        })
      );
      await waitFor(() => expect(screen.getByTestId('commit-pull-btn')).not.toBeDisabled());
      fireEvent.click(screen.getByTestId('commit-pull-btn'));
      expect(onSelect).toHaveBeenCalledWith({
        tier: 1,
        thread_ids: [8],
        resonances: [{ id: 9, name: 'Tidecall' }],
        payers: { 8: 9 },
      });
    });

    it('starts on the first payer that can pay when the leader cannot, and sends it', async () => {
      vi.mocked(previewPull).mockResolvedValue(previewOf([pyre(1)]));
      const onSelect = vi.fn();
      render(<ThreadPullDialog {...defaultProps} onSelect={onSelect} />);
      fireEvent.click(within(screen.getByTestId('thread-checkbox-8')).getByRole('checkbox'));
      await waitFor(() =>
        expect(screen.getByTestId('payer-8-9')).toHaveAttribute('aria-checked', 'true')
      );
      await waitFor(() => expect(screen.getByTestId('commit-pull-btn')).not.toBeDisabled());
      fireEvent.click(screen.getByTestId('commit-pull-btn'));
      expect(onSelect).toHaveBeenCalledWith(
        expect.objectContaining({ thread_ids: [8], payers: { 8: 9 } })
      );
    });

    it('lets a single-resonance thread whose own resonance cannot pay name another', async () => {
      vi.mocked(previewPull).mockResolvedValue(
        previewOf([
          {
            thread_id: 7,
            options: [option(8, 'Stoneheart', 0, []), option(7, 'Flamevein', 20, [])],
          },
        ])
      );
      const onSelect = vi.fn();
      render(<ThreadPullDialog {...defaultProps} onSelect={onSelect} />);
      fireEvent.click(within(screen.getByTestId('thread-checkbox-7')).getByRole('checkbox'));
      expect(await screen.findByTestId('payer-options-7')).toBeInTheDocument();
      expect(screen.getByTestId('payer-7-8')).toBeDisabled();
      fireEvent.click(screen.getByTestId('payer-7-7'));
      await waitFor(() =>
        expect(previewPull).toHaveBeenLastCalledWith({
          character_sheet_id: 12,
          tier: 1,
          thread_ids: [7],
          payers: { 7: 7 },
        })
      );
      await waitFor(() => expect(screen.getByTestId('commit-pull-btn')).not.toBeDisabled());
      fireEvent.click(screen.getByTestId('commit-pull-btn'));
      expect(onSelect).toHaveBeenCalledWith({
        tier: 1,
        thread_ids: [7],
        resonances: [{ id: 7, name: 'Flamevein' }],
        payers: { 7: 7 },
      });
    });

    it('drops a payer named at one tier when another tier shows no choice', async () => {
      // At tier 3 the leader cannot pay, so the list starts on Tidecall; at tier 1 it can.
      vi.mocked(previewPull).mockImplementation((body) =>
        Promise.resolve(previewOf([pyre(body.tier === 3 ? 1 : 20)]))
      );
      const onSelect = vi.fn();
      render(<ThreadPullDialog {...defaultProps} onSelect={onSelect} />);
      fireEvent.click(screen.getByTestId('tier-btn-3'));
      fireEvent.click(within(screen.getByTestId('thread-checkbox-8')).getByRole('checkbox'));
      await waitFor(() =>
        expect(previewPull).toHaveBeenLastCalledWith({
          character_sheet_id: 12,
          tier: 3,
          thread_ids: [8],
          payers: { 8: 9 },
        })
      );
      await waitFor(() =>
        expect(screen.getByTestId('payer-8-9')).toHaveAttribute('aria-checked', 'true')
      );
      await waitFor(() =>
        expect(screen.getByTestId('preview-resonance-cost')).toHaveTextContent('3 Tidecall')
      );

      fireEvent.click(screen.getByTestId('tier-btn-1'));
      // The row, the cost line and the request agree: the leader pays, nobody is named.
      await waitFor(() =>
        expect(previewPull).toHaveBeenLastCalledWith({
          character_sheet_id: 12,
          tier: 1,
          thread_ids: [8],
        })
      );
      await waitFor(() =>
        expect(screen.getByTestId('payer-8-7')).toHaveAttribute('aria-checked', 'true')
      );
      await waitFor(() =>
        expect(screen.getByTestId('preview-resonance-cost')).toHaveTextContent('3 Flamevein')
      );
      await waitFor(() => expect(screen.getByTestId('commit-pull-btn')).not.toBeDisabled());
      fireEvent.click(screen.getByTestId('commit-pull-btn'));
      expect(onSelect).toHaveBeenCalledWith({
        tier: 1,
        thread_ids: [8],
        resonances: [{ id: 7, name: 'Flamevein' }],
        payers: {},
      });
    });

    it('stops naming a payer once its thread is unchecked', async () => {
      const onSelect = vi.fn();
      render(<ThreadPullDialog {...defaultProps} onSelect={onSelect} />);
      fireEvent.click(within(screen.getByTestId('thread-checkbox-8')).getByRole('checkbox'));
      fireEvent.click(within(screen.getByTestId('thread-checkbox-1')).getByRole('checkbox'));
      fireEvent.click(await screen.findByTestId('payer-8-9'));
      await waitFor(() =>
        expect(previewPull).toHaveBeenLastCalledWith(expect.objectContaining({ payers: { 8: 9 } }))
      );
      fireEvent.click(within(screen.getByTestId('thread-checkbox-8')).getByRole('checkbox'));
      await waitFor(() =>
        expect(previewPull).toHaveBeenLastCalledWith({
          character_sheet_id: 12,
          tier: 1,
          thread_ids: [1],
        })
      );
      await waitFor(() => expect(screen.getByTestId('commit-pull-btn')).not.toBeDisabled());
      fireEvent.click(screen.getByTestId('commit-pull-btn'));
      expect(onSelect).toHaveBeenCalledWith(
        expect.objectContaining({ thread_ids: [1], payers: {} })
      );
    });

    it('sums the cost by the resonance that pays: "3 Flamevein, 3 Tidecall"', async () => {
      vi.mocked(previewPull).mockResolvedValue(
        previewOf([{ thread_id: 1, options: [option(7, 'Flamevein', 20, [])] }, pyre(20)])
      );
      render(<ThreadPullDialog {...defaultProps} />);
      fireEvent.click(within(screen.getByTestId('thread-checkbox-1')).getByRole('checkbox'));
      fireEvent.click(within(screen.getByTestId('thread-checkbox-8')).getByRole('checkbox'));
      await waitFor(() =>
        expect(screen.getByTestId('preview-resonance-cost')).toHaveTextContent('6 Flamevein')
      );
      fireEvent.click(await screen.findByTestId('payer-8-9'));
      await waitFor(() =>
        expect(screen.getByTestId('preview-resonance-cost')).toHaveTextContent(
          '3 Flamevein, 3 Tidecall'
        )
      );
    });
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
