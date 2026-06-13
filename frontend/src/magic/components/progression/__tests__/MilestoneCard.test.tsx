/**
 * Tests for MilestoneCard, MysteryMilestoneSlot, and StageSection.
 *
 * Covers:
 * - known + eligible → renders title, summary, "Available" badge, CTA button
 * - known + locked → renders missing items list
 * - known + already_have → renders "Attained" badge
 * - uncovered → no eligibility info; shows "Learn more" CTA when route_name is set
 * - MysteryMilestoneSlot → renders placeholder; does NOT render any milestone title
 * - StageSection with has_undiscovered: true → exactly one mystery slot
 * - StageSection with has_undiscovered: false → no mystery slot
 * - StageSection with is_current: true → renders "Current" indicator
 */

import { render, screen, within } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import { MilestoneCard } from '../MilestoneCard';
import { MysteryMilestoneSlot } from '../MysteryMilestoneSlot';
import { StageSection } from '../StageSection';
import type { ProgressionMilestone, ProgressionStage } from '@/magic/magicProgressionTypes';

// ---------------------------------------------------------------------------
// Mock useNavigate so router calls don't crash.
// ---------------------------------------------------------------------------

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// ---------------------------------------------------------------------------
// Wrapper — MilestoneCard calls useNavigate, so needs a router context.
// ---------------------------------------------------------------------------

function Wrapper({ children }: { children: ReactNode }) {
  return <MemoryRouter>{children}</MemoryRouter>;
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeMilestone(overrides: Partial<ProgressionMilestone> = {}): ProgressionMilestone {
  return {
    kind: 'path_unlock',
    tier: 'known',
    title: 'First Flame',
    summary: 'Unlock the path of fire.',
    eligibility: 'eligible',
    missing: [],
    xp_cost: 10,
    route_name: '/magic/paths/fire',
    codex_entry_id: null,
    ...overrides,
  };
}

function makeStage(overrides: Partial<ProgressionStage> = {}): ProgressionStage {
  return {
    stage: 1,
    stage_label: 'Initiate',
    is_current: false,
    has_undiscovered: false,
    milestones: [],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// MilestoneCard tests
// ---------------------------------------------------------------------------

describe('MilestoneCard', () => {
  it('known + eligible: renders title, summary, Available badge, and CTA', () => {
    const milestone = makeMilestone({ eligibility: 'eligible' });
    render(<MilestoneCard milestone={milestone} />, { wrapper: Wrapper });

    const card = screen.getByTestId('milestone-card');
    expect(card).toBeInTheDocument();
    expect(within(card).getByText('First Flame')).toBeInTheDocument();
    expect(within(card).getByText('Unlock the path of fire.')).toBeInTheDocument();
    expect(within(card).getByText(/available/i)).toBeInTheDocument();
    expect(within(card).getByRole('button')).toBeInTheDocument();
  });

  it('known + eligible: shows xp_cost', () => {
    const milestone = makeMilestone({ eligibility: 'eligible', xp_cost: 25 });
    render(<MilestoneCard milestone={milestone} />, { wrapper: Wrapper });

    expect(screen.getByText(/25.*XP/i)).toBeInTheDocument();
  });

  it('known + locked: renders missing items', () => {
    const milestone = makeMilestone({
      eligibility: 'locked',
      missing: ['Complete the ritual', 'Reach stage 2'],
    });
    render(<MilestoneCard milestone={milestone} />, { wrapper: Wrapper });

    const card = screen.getByTestId('milestone-card');
    expect(within(card).getByText(/locked/i)).toBeInTheDocument();
    expect(within(card).getByText('Complete the ritual')).toBeInTheDocument();
    expect(within(card).getByText('Reach stage 2')).toBeInTheDocument();
  });

  it('known + already_have: renders Attained badge', () => {
    const milestone = makeMilestone({ eligibility: 'already_have', route_name: null });
    render(<MilestoneCard milestone={milestone} />, { wrapper: Wrapper });

    expect(screen.getByText(/attained/i)).toBeInTheDocument();
  });

  it('uncovered: no eligibility badge, shows muted treatment, "Learn more" CTA when route set', () => {
    const milestone = makeMilestone({
      tier: 'uncovered',
      eligibility: null,
      missing: [],
      route_name: '/magic/codex/42',
    });
    render(<MilestoneCard milestone={milestone} />, { wrapper: Wrapper });

    const card = screen.getByTestId('milestone-card');
    expect(within(card).queryByText(/available/i)).not.toBeInTheDocument();
    expect(within(card).queryByText(/locked/i)).not.toBeInTheDocument();
    expect(within(card).queryByText(/attained/i)).not.toBeInTheDocument();
    expect(within(card).getByRole('button', { name: /learn more/i })).toBeInTheDocument();
  });

  it('known + no route_name: no CTA button', () => {
    const milestone = makeMilestone({ route_name: null });
    render(<MilestoneCard milestone={milestone} />, { wrapper: Wrapper });

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// MysteryMilestoneSlot tests
// ---------------------------------------------------------------------------

describe('MysteryMilestoneSlot', () => {
  it('renders the placeholder with data-testid', () => {
    render(<MysteryMilestoneSlot />, { wrapper: Wrapper });

    expect(screen.getByTestId('mystery-slot')).toBeInTheDocument();
  });

  it('does NOT render any milestone title text', () => {
    render(<MysteryMilestoneSlot />, { wrapper: Wrapper });

    // Must not show titles that would reveal specifics
    expect(screen.queryByText('First Flame')).not.toBeInTheDocument();
    expect(screen.queryByText(/unlock/i)).not.toBeInTheDocument();
  });

  it('renders a generic placeholder message', () => {
    render(<MysteryMilestoneSlot />, { wrapper: Wrapper });

    // Should have some non-empty muted placeholder text
    const slot = screen.getByTestId('mystery-slot');
    expect(slot.textContent?.trim().length).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// StageSection tests
// ---------------------------------------------------------------------------

describe('StageSection', () => {
  it('renders stage_label as section aria-label', () => {
    const stage = makeStage({ stage_label: 'Kindled', milestones: [] });
    render(<StageSection stage={stage} />, { wrapper: Wrapper });

    expect(screen.getByRole('region', { name: 'Kindled' })).toBeInTheDocument();
  });

  it('has_undiscovered true → exactly one mystery slot', () => {
    const stage = makeStage({ has_undiscovered: true, milestones: [makeMilestone()] });
    render(<StageSection stage={stage} />, { wrapper: Wrapper });

    expect(screen.getAllByTestId('mystery-slot')).toHaveLength(1);
  });

  it('has_undiscovered false → no mystery slot', () => {
    const stage = makeStage({ has_undiscovered: false, milestones: [makeMilestone()] });
    render(<StageSection stage={stage} />, { wrapper: Wrapper });

    expect(screen.queryByTestId('mystery-slot')).not.toBeInTheDocument();
  });

  it('is_current true → renders "Current" indicator', () => {
    const stage = makeStage({ is_current: true, stage_label: 'Adept' });
    render(<StageSection stage={stage} />, { wrapper: Wrapper });

    expect(screen.getByText(/current/i)).toBeInTheDocument();
  });

  it('renders all milestones as MilestoneCards', () => {
    const milestones = [
      makeMilestone({ title: 'Alpha', kind: 'a' }),
      makeMilestone({ title: 'Beta', kind: 'b' }),
    ];
    const stage = makeStage({ milestones });
    render(<StageSection stage={stage} />, { wrapper: Wrapper });

    expect(screen.getAllByTestId('milestone-card')).toHaveLength(2);
    expect(screen.getByText('Alpha')).toBeInTheDocument();
    expect(screen.getByText('Beta')).toBeInTheDocument();
  });
});
