import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { DEFAULT_FEED_CHIPS, type FeedChipState } from '../feedChips';
import { FeedChipStrip } from './FeedChipStrip';

const defaults = (): FeedChipState => ({
  chips: DEFAULT_FEED_CHIPS.map((c) => ({ ...c })),
  all: true,
});

function renderStrip(state: FeedChipState = defaults(), newCounts: Record<string, number> = {}) {
  const onChange = vi.fn();
  render(<FeedChipStrip state={state} onChange={onChange} newCounts={newCounts} />);
  return { onChange };
}

describe('FeedChipStrip (#3856)', () => {
  it('renders the chips, then +, then All at the end, as plain labels', () => {
    renderStrip();
    const strip = screen.getByRole('toolbar', { name: 'Feed filters' });
    const names = within(strip)
      .getAllByRole('button')
      .map((b) => b.textContent?.trim());
    expect(names).toEqual(['Roleplay', 'Whispers', 'Movement', 'Ambience', 'System', '+', 'All']);
    expect(within(strip).getByRole('button', { name: 'Roleplay' })).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    expect(within(strip).queryByText(/right.?click/i)).not.toBeInTheDocument();
  });

  it('pressing a chip toggles it; pressing All switches everything off', () => {
    const { onChange } = renderStrip();
    fireEvent.click(screen.getByRole('button', { name: 'System' }));
    expect(onChange).toHaveBeenLastCalledWith(
      expect.objectContaining({
        all: true,
        chips: expect.arrayContaining([expect.objectContaining({ id: 'sy', on: false })]),
      })
    );
    fireEvent.click(screen.getByRole('button', { name: 'All' }));
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ all: false }));
  });

  it('shows every chip dark while All is off', () => {
    renderStrip({ ...defaults(), all: false });
    expect(screen.getByRole('button', { name: 'Roleplay' })).toHaveAttribute(
      'aria-pressed',
      'false'
    );
    expect(screen.getByRole('button', { name: 'All' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('shows a new pill on a chip with unseen waking items', () => {
    renderStrip(defaults(), { rp: 2 });
    expect(screen.getByRole('button', { name: /Roleplay/ })).toHaveTextContent('new');
    expect(screen.getByRole('button', { name: /Whispers/ })).not.toHaveTextContent('new');
  });

  it('hides + once three custom chips exist', () => {
    const state = defaults();
    for (const n of [1, 2, 3]) {
      state.chips.push({
        id: `c${n}`,
        label: `Chip ${n}`,
        kinds: [],
        on: true,
        wake: false,
        custom: true,
      });
    }
    renderStrip(state);
    expect(screen.queryByRole('button', { name: '+' })).not.toBeInTheDocument();
  });

  it('right-clicking a chip opens its editor with the name, the kinds and where they live', async () => {
    renderStrip();
    fireEvent.contextMenu(screen.getByRole('button', { name: 'Whispers' }));
    const editor = await screen.findByRole('dialog');
    expect(within(editor).getByLabelText('Chip name')).toHaveValue('Whispers');
    expect(within(editor).getByLabelText(/^Whispers$/)).toBeChecked();
    const speech = within(editor).getByLabelText(/Speech/);
    expect(speech).not.toBeChecked();
    // Poses, Speech and GM emits all live in Roleplay today.
    expect(within(editor).getAllByText('(in Roleplay)')).toHaveLength(3);
    expect(within(editor).getByLabelText('Wake me when this arrives')).toBeChecked();
    expect(within(editor).getByRole('button', { name: 'Delete chip' })).toBeInTheDocument();
  });

  it('ticking a kind in the editor moves it to this chip', async () => {
    const { onChange } = renderStrip();
    fireEvent.contextMenu(screen.getByRole('button', { name: 'Whispers' }));
    const editor = await screen.findByRole('dialog');
    fireEvent.click(within(editor).getByLabelText(/Speech/));
    const next = onChange.mock.lastCall?.[0] as FeedChipState;
    expect(next.chips.find((c) => c.id === 'wh')?.kinds).toEqual(['whisper', 'say']);
    expect(next.chips.find((c) => c.id === 'rp')?.kinds).toEqual(['pose', 'emit']);
  });

  it('renaming commits on Enter and closes the editor; wake and delete write through', async () => {
    const user = userEvent.setup();
    const { onChange } = renderStrip();
    fireEvent.contextMenu(screen.getByRole('button', { name: 'Movement' }));
    const editor = await screen.findByRole('dialog');
    const name = within(editor).getByLabelText('Chip name');
    await user.clear(name);
    await user.type(name, 'Comings{Enter}');
    expect((onChange.mock.lastCall?.[0] as FeedChipState).chips[2].label).toBe('Comings');
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    fireEvent.contextMenu(screen.getByRole('button', { name: 'Movement' }));
    const again = await screen.findByRole('dialog');
    fireEvent.click(within(again).getByLabelText('Wake me when this arrives'));
    expect((onChange.mock.lastCall?.[0] as FeedChipState).chips[2].wake).toBe(true);
    fireEvent.click(within(again).getByRole('button', { name: 'Delete chip' }));
    expect((onChange.mock.lastCall?.[0] as FeedChipState).chips.map((c) => c.id)).toEqual([
      'rp',
      'wh',
      'am',
      'sy',
    ]);
  });

  it('+ adds a custom chip and opens its editor with the name selected', async () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <FeedChipStrip state={defaults()} onChange={onChange} newCounts={{}} />
    );
    fireEvent.click(screen.getByRole('button', { name: '+' }));
    const next = onChange.mock.lastCall?.[0] as FeedChipState;
    expect(next.chips.at(-1)).toMatchObject({ label: 'Chip 1', custom: true, kinds: [] });
    // The strip is controlled; the page re-renders it with the new state.
    rerender(<FeedChipStrip state={next} onChange={onChange} newCounts={{}} />);
    const editor = await screen.findByRole('dialog');
    const name = within(editor).getByLabelText('Chip name') as HTMLInputElement;
    expect(name).toHaveValue('Chip 1');
    expect(name.selectionStart).toBe(0);
    expect(name.selectionEnd).toBe('Chip 1'.length);
  });
});
