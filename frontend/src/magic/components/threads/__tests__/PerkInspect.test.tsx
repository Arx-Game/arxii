import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { PerkInspect } from '../PerkInspect';
import type { PayerOption, Thread } from '../../../types';

const thread = {
  id: 1,
  name: 'Pyromancy',
  level: 30,
  target_kind: 'GIFT',
  resonance: 1,
  resonance_name: 'Fury',
  resonances: [
    { resonance_id: 1, resonance_name: 'Fury', amount: 30, leads: true },
    { resonance_id: 2, resonance_name: 'Domination', amount: 10, leads: false },
  ],
} as Thread;

const effect = {
  kind: 'FLAT_BONUS',
  authored_value: 2,
  level_multiplier: 3,
  scaled_value: 6,
  vital_target: null,
  source_thread_id: 1,
  source_thread_level: 20,
  source_tier: 2,
  narrative_snippet: 'The fire bends toward whoever you mean to break.',
  inactive: false,
  inactive_reason: null,
};

const option = (id: number, name: string, levelRead: number, effects = [effect]): PayerOption => ({
  resonance_id: id,
  resonance_name: name,
  cost: 3,
  balance: 14,
  affordable: true,
  effects,
  level_read: levelRead,
});

describe('PerkInspect', () => {
  it('shows the amount, how it was worked out, its source and the level read', () => {
    render(
      <PerkInspect
        thread={thread}
        option={option(2, 'Domination', 20)}
        open
        onOpenChange={vi.fn()}
      />
    );
    const panel = screen.getByTestId('perk-inspect-0');
    expect(panel).toHaveTextContent('Bonus to this cast');
    expect(panel).toHaveTextContent('Amount+6');
    expect(panel).toHaveTextContent('Worked out2 x 3');
    expect(panel).toHaveTextContent('Domination pull perk for Gift threads, tier 2');
    expect(panel).toHaveTextContent(
      'Thread level used20 (thread is 30; Domination is not its leading resonance)'
    );
    expect(panel).toHaveTextContent('The fire bends toward whoever you mean to break.');
  });

  it('reads the full thread level for the leading resonance', () => {
    render(
      <PerkInspect thread={thread} option={option(1, 'Fury', 30)} open onOpenChange={vi.fn()} />
    );
    expect(screen.getByTestId('perk-inspect-0')).toHaveTextContent('Thread level used30');
    expect(screen.getByTestId('perk-inspect-0')).not.toHaveTextContent('leading resonance');
  });

  it('says a held resonance the thread never took in has no perks and why', () => {
    render(
      <PerkInspect
        thread={thread}
        option={option(3, 'Wonder', 30, [])}
        open
        onOpenChange={vi.fn()}
      />
    );
    expect(screen.getByTestId('perk-inspect-none')).toHaveTextContent('No perks on this thread');
  });

  it('keeps a perk that is not active, with its reason', () => {
    const inactive = { ...effect, inactive: true, inactive_reason: 'Not in a sanctum.' };
    render(
      <PerkInspect
        thread={thread}
        option={option(1, 'Fury', 30, [inactive])}
        open
        onOpenChange={vi.fn()}
      />
    );
    expect(screen.getByTestId('perk-inspect-0')).toHaveTextContent('Not in a sanctum.');
  });
});
