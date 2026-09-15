/**
 * GlimpseFlow Component Tests (#2427, offers slot #3675)
 *
 * Pure presentational component — plain render, no providers needed.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { GlimpseFlow } from '../GlimpseFlow';
import type { GlimpseFlowProps, GlimpseTagOption } from '../glimpseTypes';

const TONE_WONDER: GlimpseTagOption = {
  id: 1,
  axis: 'TONE',
  name: 'Wonder',
  slug: 'wonder',
  description: 'Awe at the impossible.',
  example: 'The light bent around her hand like water.',
  sort_order: 1,
  offers: [],
};

const TONE_DREAD: GlimpseTagOption = {
  id: 2,
  axis: 'TONE',
  name: 'Dread',
  slug: 'dread',
  description: 'Fear at the impossible.',
  example: 'The shadows breathed.',
  sort_order: 2,
  offers: [],
};

const CONSEQUENCE_A: GlimpseTagOption = {
  id: 3,
  axis: 'CONSEQUENCE',
  name: 'A Debt Incurred',
  slug: 'debt-incurred',
  description: 'Something was owed after.',
  example: 'The price came due at midnight.',
  sort_order: 1,
  offers: [],
};

const CONSEQUENCE_B: GlimpseTagOption = {
  id: 4,
  axis: 'CONSEQUENCE',
  name: 'A Door Opened',
  slug: 'door-opened',
  description: 'Something new became possible.',
  example: 'A door that was not there before, now was.',
  sort_order: 2,
  offers: [],
};

const WITNESS_ALONE: GlimpseTagOption = {
  id: 5,
  axis: 'WITNESS',
  name: 'Alone',
  slug: 'alone',
  description: 'No one else saw.',
  example: 'She told no one.',
  sort_order: 1,
  offers: [],
};

const SENSORY_TASTE: GlimpseTagOption = {
  id: 6,
  axis: 'SENSORY',
  name: 'A Taste of Copper',
  slug: 'taste-of-copper',
  description: 'A sensory detail of the glimpse.',
  example: 'Copper on the tongue, like a coin.',
  sort_order: 1,
  offers: [],
};

const TRIGGER_TRAUMA: GlimpseTagOption = {
  id: 10,
  axis: 'TRIGGER',
  name: 'Trauma',
  slug: 'trauma',
  description: 'A shattering event cracked you open.',
  example: 'The wound never fully closed.',
  sort_order: 1,
  offers: [],
};

const TRIGGER_PATRON: GlimpseTagOption = {
  id: 11,
  axis: 'TRIGGER',
  name: 'Patron Chose You',
  slug: 'patron-chose-you',
  description: 'A god, demon, or force selected you.',
  example: 'Something ancient turned its gaze upon you.',
  sort_order: 2,
  offers: [],
};

const ALL_TAGS: GlimpseTagOption[] = [
  TONE_WONDER,
  TONE_DREAD,
  CONSEQUENCE_A,
  CONSEQUENCE_B,
  WITNESS_ALONE,
  SENSORY_TASTE,
];

function makeProps(overrides: Partial<GlimpseFlowProps> = {}): GlimpseFlowProps {
  return {
    tags: ALL_TAGS,
    selectedTagIds: [],
    prose: '',
    onChangeAxis: vi.fn(),
    onChangeProse: vi.fn(),
    onSkip: vi.fn(),
    showDeferralControls: true,
    ...overrides,
  };
}

describe('GlimpseFlow', () => {
  it('replaces the selection when a second Tone card is clicked (single-select)', async () => {
    const user = userEvent.setup();
    const onChangeAxis = vi.fn();
    render(<GlimpseFlow {...makeProps({ selectedTagIds: [1], onChangeAxis })} />);

    await user.click(screen.getByText('Dread'));

    expect(onChangeAxis).toHaveBeenCalledWith('TONE', [2]);
  });

  it('clears the Tone selection when the already-selected card is clicked again', async () => {
    const user = userEvent.setup();
    const onChangeAxis = vi.fn();
    render(<GlimpseFlow {...makeProps({ selectedTagIds: [1], onChangeAxis })} />);

    await user.click(screen.getByText('Wonder'));

    expect(onChangeAxis).toHaveBeenCalledWith('TONE', []);
  });

  it('toggles membership for a multi-select axis (Consequence)', async () => {
    const user = userEvent.setup();
    const onChangeAxis = vi.fn();
    render(<GlimpseFlow {...makeProps({ selectedTagIds: [3], onChangeAxis })} />);

    // The accordion is single-open (Tone is the default) — open Consequence first.
    await user.click(screen.getByText('Consequence: what did it leave behind?'));
    await user.click(screen.getByText('A Door Opened'));
    expect(onChangeAxis).toHaveBeenLastCalledWith('CONSEQUENCE', [3, 4]);

    onChangeAxis.mockClear();
    await user.click(screen.getByText('A Debt Incurred'));
    expect(onChangeAxis).toHaveBeenLastCalledWith('CONSEQUENCE', []);
  });

  it('does not render a link/suggestion section (#3675: offers are chapter-scoped now)', () => {
    render(<GlimpseFlow {...makeProps({ selectedTagIds: [1, 3] })} />);

    expect(screen.queryByText('Suggested Distinctions')).not.toBeInTheDocument();
    expect(screen.queryByText('Link a distinction to your glimpse')).not.toBeInTheDocument();
  });

  it('renders the staff-authored story hint under the story textarea', () => {
    render(<GlimpseFlow {...makeProps({ storyHint: 'The detail goes here.' })} />);

    expect(screen.getByText('The detail goes here.')).toBeInTheDocument();
  });

  it('renders no story hint when storyHint is omitted', () => {
    render(<GlimpseFlow {...makeProps()} />);

    expect(screen.queryByText('The detail goes here.')).not.toBeInTheDocument();
  });

  it('calls onSkip from both deferral buttons', async () => {
    const user = userEvent.setup();
    const onSkip = vi.fn();
    render(<GlimpseFlow {...makeProps({ onSkip })} />);

    await user.click(screen.getByText('Skip for now'));
    await user.click(screen.getByText('Save tags: write the story later'));

    expect(onSkip).toHaveBeenCalledTimes(2);
  });

  it('does not render deferral controls when showDeferralControls is false', () => {
    render(<GlimpseFlow {...makeProps({ showDeferralControls: false })} />);

    expect(screen.queryByText('Skip for now')).not.toBeInTheDocument();
  });

  it('renders SENSORY tags as toggle chips in the story step, not an accordion item', () => {
    render(<GlimpseFlow {...makeProps()} />);

    expect(screen.queryByText('Sensory & Discovery')).not.toBeInTheDocument();
    expect(screen.getByText('A Taste of Copper')).toBeInTheDocument();
  });

  it('calls onChangeProse when the story textarea changes', async () => {
    const user = userEvent.setup();
    const onChangeProse = vi.fn();
    render(<GlimpseFlow {...makeProps({ onChangeProse })} />);

    await user.type(screen.getByLabelText('Your Story'), 'a');

    expect(onChangeProse).toHaveBeenCalled();
  });

  it('renders gracefully with an empty catalog — no axis steps and no SENSORY chips', () => {
    render(<GlimpseFlow {...makeProps({ tags: [] })} />);

    expect(screen.queryByText('Tone — how did it feel?')).not.toBeInTheDocument();
    expect(screen.queryByText('Consequence: what did it leave behind?')).not.toBeInTheDocument();
    expect(screen.queryByText('Witness & Secrecy: who saw?')).not.toBeInTheDocument();
    // The always-present heading and story step still render.
    expect(screen.getByText('The Glimpse')).toBeInTheDocument();
  });

  it('renders the default heading above the axis accordion when no heading prop is passed', () => {
    render(<GlimpseFlow {...makeProps()} />);

    expect(screen.getByText('The Glimpse')).toBeInTheDocument();
  });

  it('renders a staff-authored heading when the heading prop is passed', () => {
    render(<GlimpseFlow {...makeProps({ heading: 'Your First Sight of the Unseen' })} />);

    expect(screen.getByText('Your First Sight of the Unseen')).toBeInTheDocument();
    expect(screen.queryByText('The Glimpse')).not.toBeInTheDocument();
  });

  it('selects a tag card via Enter from the keyboard', async () => {
    const user = userEvent.setup();
    const onChangeAxis = vi.fn();
    render(<GlimpseFlow {...makeProps({ onChangeAxis })} />);

    (screen.getByText('Wonder').closest('[role="button"]') as HTMLElement | null)?.focus();
    await user.keyboard('{Enter}');

    expect(onChangeAxis).toHaveBeenCalledWith('TONE', [1]);
  });

  it('selects a tag card via Space from the keyboard, without scrolling the page', async () => {
    const user = userEvent.setup();
    const onChangeAxis = vi.fn();
    render(<GlimpseFlow {...makeProps({ onChangeAxis })} />);

    const card = screen.getByText('Wonder').closest('[role="button"]') as HTMLElement;
    card.focus();
    await user.keyboard('[Space]');

    expect(onChangeAxis).toHaveBeenCalledWith('TONE', [1]);
  });

  it('renders the Trigger step as a single-select accordion item', () => {
    render(<GlimpseFlow {...makeProps({ tags: [...ALL_TAGS, TRIGGER_TRAUMA, TRIGGER_PATRON] })} />);

    expect(screen.getByText('Trigger: what was happening?')).toBeInTheDocument();
    expect(screen.getByText('Trauma')).toBeInTheDocument();
  });

  it('replaces the selection when a second Trigger card is clicked (single-select)', async () => {
    const user = userEvent.setup();
    const onChangeAxis = vi.fn();
    render(
      <GlimpseFlow
        {...makeProps({
          tags: [...ALL_TAGS, TRIGGER_TRAUMA, TRIGGER_PATRON],
          selectedTagIds: [10],
          onChangeAxis,
        })}
      />
    );

    await user.click(screen.getByText('Patron Chose You'));

    expect(onChangeAxis).toHaveBeenCalledWith('TRIGGER', [11]);
  });

  it('hides the Trigger step when no TRIGGER tags exist in the catalog', () => {
    render(<GlimpseFlow {...makeProps()} />);

    expect(screen.queryByText('Trigger: what was happening?')).not.toBeInTheDocument();
  });
});
