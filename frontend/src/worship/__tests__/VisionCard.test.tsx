/**
 * VisionCard (#4333 slice 3): a vision a closed pledge released lists what came with
 * it (the fact clue, the follow-up and the cost's condition) as footnotes.
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { VisionCard } from '../components/VisionCard';
import type { Vision } from '../types';

const base: Vision = {
  id: 1,
  recipient: 3,
  being_name: 'Ombrin',
  body: '[staff-authored delay text]\n\n[staff-authored answer text]',
  reveal_source: true,
  prayer: null,
  clue: 4,
  clue_slug: 'ombrin-codex-clue',
  clue_name: 'Ombrin codex clue',
  episode: null,
  episode_title: null,
  follow_up_clue_name: 'Ombrin mission clue',
  condition_names: ['Marked by Ombrin'],
  sent_at: new Date().toISOString(),
};

describe('VisionCard', () => {
  it('lists the fact clue, the follow-up and the condition an answer brought', () => {
    render(<VisionCard vision={base} />);
    const notes = screen.getByTestId('vision-footnotes');
    expect(notes).toHaveTextContent('A clue came with it: Ombrin codex clue.');
    expect(notes).toHaveTextContent('A follow-up came with it: Ombrin mission clue.');
    expect(notes).toHaveTextContent('Condition: Marked by Ombrin.');
    expect(screen.getByText('from Ombrin')).toBeInTheDocument();
  });

  it('shows no footnote for a vision with nothing attached', () => {
    render(
      <VisionCard
        vision={{
          ...base,
          clue: null,
          clue_slug: null,
          clue_name: null,
          follow_up_clue_name: null,
          condition_names: [],
        }}
      />
    );
    expect(screen.queryByTestId('vision-footnotes')).not.toBeInTheDocument();
  });
});
