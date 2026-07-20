/**
 * GlimpseFlow Component Tests (#2427)
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
  suggested_distinctions: [{ id: 10, name: 'Keen Senses' }],
};

const TONE_DREAD: GlimpseTagOption = {
  id: 2,
  axis: 'TONE',
  name: 'Dread',
  slug: 'dread',
  description: 'Fear at the impossible.',
  example: 'The shadows breathed.',
  sort_order: 2,
  suggested_distinctions: [],
};

const CONSEQUENCE_A: GlimpseTagOption = {
  id: 3,
  axis: 'CONSEQUENCE',
  name: 'A Debt Incurred',
  slug: 'debt-incurred',
  description: 'Something was owed after.',
  example: 'The price came due at midnight.',
  sort_order: 1,
  suggested_distinctions: [
    { id: 10, name: 'Keen Senses' },
    { id: 11, name: 'Marked' },
  ],
};

const CONSEQUENCE_B: GlimpseTagOption = {
  id: 4,
  axis: 'CONSEQUENCE',
  name: 'A Door Opened',
  slug: 'door-opened',
  description: 'Something new became possible.',
  example: 'A door that was not there before, now was.',
  sort_order: 2,
  suggested_distinctions: [],
};

const WITNESS_ALONE: GlimpseTagOption = {
  id: 5,
  axis: 'WITNESS',
  name: 'Alone',
  slug: 'alone',
  description: 'No one else saw.',
  example: 'She told no one.',
  sort_order: 1,
  suggested_distinctions: [],
};

const SENSORY_TASTE: GlimpseTagOption = {
  id: 6,
  axis: 'SENSORY',
  name: 'A Taste of Copper',
  slug: 'taste-of-copper',
  description: 'A sensory detail of the glimpse.',
  example: 'Copper on the tongue, like a coin.',
  sort_order: 1,
  suggested_distinctions: [],
};

const TRIGGER_TRAUMA: GlimpseTagOption = {
  id: 10,
  axis: 'TRIGGER',
  name: 'Trauma',
  slug: 'trauma',
  description: 'A shattering event cracked you open.',
  example: 'The wound never fully closed.',
  sort_order: 1,
  suggested_distinctions: [],
};

const TRIGGER_PATRON: GlimpseTagOption = {
  id: 11,
  axis: 'TRIGGER',
  name: 'Patron Chose You',
  slug: 'patron-chose-you',
  description: 'A god, demon, or force selected you.',
  example: 'Something ancient turned its gaze upon you.',
  sort_order: 2,
  suggested_distinctions: [],
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
    linkedDistinctionIds: [],
    onChangeAxis: vi.fn(),
    onChangeProse: vi.fn(),
    onToggleDistinctionLink: vi.fn(),
    onSkip: vi.fn(),
    showDeferralControls: true,
    linkableDistinctions: [],
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
    await user.click(screen.getByText('Consequence'));
    await user.click(screen.getByText('A Door Opened'));
    expect(onChangeAxis).toHaveBeenLastCalledWith('CONSEQUENCE', [3, 4]);

    onChangeAxis.mockClear();
    await user.click(screen.getByText('A Debt Incurred'));
    expect(onChangeAxis).toHaveBeenLastCalledWith('CONSEQUENCE', []);
  });

  it('dedupes a distinction suggested by two selected tags to a single suggestion', () => {
    // TONE_WONDER (id 1) and CONSEQUENCE_A (id 3) both suggest distinction 10.
    render(<GlimpseFlow {...makeProps({ selectedTagIds: [1, 3] })} />);

    expect(screen.getAllByText('Keen Senses')).toHaveLength(1);
    // The non-overlapping suggestion from CONSEQUENCE_A still appears.
    expect(screen.getByText('Marked')).toBeInTheDocument();
  });

  it('does not render the suggestion panel when nothing is selected', () => {
    render(<GlimpseFlow {...makeProps({ selectedTagIds: [] })} />);

    expect(screen.queryByText('Suggested Distinctions')).not.toBeInTheDocument();
  });

  it('renders the manual-link control with zero suggestions', () => {
    render(
      <GlimpseFlow
        {...makeProps({
          selectedTagIds: [],
          linkableDistinctions: [{ id: 99, name: 'Silver Tongue' }],
        })}
      />
    );

    expect(screen.getByText('Link a distinction to your glimpse')).toBeInTheDocument();
    expect(screen.getByText('Silver Tongue')).toBeInTheDocument();
  });

  it('calls onToggleDistinctionLink when a linkable distinction is clicked', async () => {
    const user = userEvent.setup();
    const onToggleDistinctionLink = vi.fn();
    render(
      <GlimpseFlow
        {...makeProps({
          linkableDistinctions: [{ id: 99, name: 'Silver Tongue' }],
          onToggleDistinctionLink,
        })}
      />
    );

    await user.click(screen.getByText('Silver Tongue'));

    expect(onToggleDistinctionLink).toHaveBeenCalledWith(99);
  });

  it('calls onSkip from both deferral buttons', async () => {
    const user = userEvent.setup();
    const onSkip = vi.fn();
    render(<GlimpseFlow {...makeProps({ onSkip })} />);

    await user.click(screen.getByText('Skip for now'));
    await user.click(screen.getByText('Save tags — write the story later'));

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

    expect(screen.queryByText('Tone')).not.toBeInTheDocument();
    expect(screen.queryByText('Consequence')).not.toBeInTheDocument();
    expect(screen.queryByText('Witness & Secrecy')).not.toBeInTheDocument();
    // The always-present heading and story step still render.
    expect(screen.getByText('The Glimpse')).toBeInTheDocument();
    expect(screen.getByText('Link a distinction to your glimpse')).toBeInTheDocument();
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

    expect(screen.getByText('Trigger')).toBeInTheDocument();
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

    expect(screen.queryByText('Trigger')).not.toBeInTheDocument();
  });
});
