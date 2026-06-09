/**
 * Tests for the OutcomeRoulette component.
 *
 * Phase 5, Task 5.2 — consequence-outcome display (#850).
 */

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { OutcomeRoulette } from '../OutcomeRoulette';
import type { OutcomeDisplayRow, ConsequenceOutcomeModifier } from '../api';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const OUTCOME_DISPLAY: OutcomeDisplayRow[] = [
  { label: 'Scratch', tier_name: 'Trivial', weight: 40, is_selected: false },
  { label: 'Bruised', tier_name: 'Minor', weight: 35, is_selected: true },
  { label: 'Broken arm', tier_name: 'Severe', weight: 25, is_selected: false },
];

const MODIFIERS: ConsequenceOutcomeModifier[] = [
  { source_kind: 'condition', source_label: 'Exhausted', value: -3 },
  { source_kind: 'equipment', source_label: 'Light armour', value: 1 },
];

// ---------------------------------------------------------------------------
// Tests — outcome pool rendering
// ---------------------------------------------------------------------------

describe('OutcomeRoulette — outcome pool', () => {
  it('renders all outcome rows', () => {
    render(<OutcomeRoulette outcomeDisplay={OUTCOME_DISPLAY} modifiers={[]} modifierTotal={0} />);

    expect(screen.getByTestId('outcome-row-Trivial')).toBeInTheDocument();
    expect(screen.getByTestId('outcome-row-Minor')).toBeInTheDocument();
    expect(screen.getByTestId('outcome-row-Severe')).toBeInTheDocument();
  });

  it('marks the selected outcome with aria-selected=true', () => {
    render(<OutcomeRoulette outcomeDisplay={OUTCOME_DISPLAY} modifiers={[]} modifierTotal={0} />);

    const selectedRow = screen.getByTestId('outcome-row-Minor');
    expect(selectedRow).toHaveAttribute('aria-selected', 'true');
  });

  it('marks non-selected outcomes with aria-selected=false', () => {
    render(<OutcomeRoulette outcomeDisplay={OUTCOME_DISPLAY} modifiers={[]} modifierTotal={0} />);

    expect(screen.getByTestId('outcome-row-Trivial')).toHaveAttribute('aria-selected', 'false');
    expect(screen.getByTestId('outcome-row-Severe')).toHaveAttribute('aria-selected', 'false');
  });

  it('shows the selected-marker checkmark only on the winner', () => {
    render(<OutcomeRoulette outcomeDisplay={OUTCOME_DISPLAY} modifiers={[]} modifierTotal={0} />);

    expect(screen.getByTestId('outcome-selected-marker-Minor')).toBeInTheDocument();
    expect(screen.queryByTestId('outcome-selected-marker-Trivial')).not.toBeInTheDocument();
    expect(screen.queryByTestId('outcome-selected-marker-Severe')).not.toBeInTheDocument();
  });

  it('shows tier names on each row', () => {
    render(<OutcomeRoulette outcomeDisplay={OUTCOME_DISPLAY} modifiers={[]} modifierTotal={0} />);

    expect(screen.getByTestId('outcome-tier-Trivial')).toHaveTextContent('Trivial');
    expect(screen.getByTestId('outcome-tier-Minor')).toHaveTextContent('Minor');
    expect(screen.getByTestId('outcome-tier-Severe')).toHaveTextContent('Severe');
  });

  it('shows all outcome labels', () => {
    render(<OutcomeRoulette outcomeDisplay={OUTCOME_DISPLAY} modifiers={[]} modifierTotal={0} />);

    // Scratch only appears once; Bruised appears in both the callout and the pool row.
    expect(screen.getByText('Scratch')).toBeInTheDocument();
    expect(screen.getAllByText('Bruised')).toHaveLength(2);
    expect(screen.getByText('Broken arm')).toBeInTheDocument();
  });

  it('shows the selected-outcome callout', () => {
    render(<OutcomeRoulette outcomeDisplay={OUTCOME_DISPLAY} modifiers={[]} modifierTotal={0} />);

    const callout = screen.getByTestId('outcome-selected-callout');
    expect(callout).toBeInTheDocument();
    expect(callout).toHaveTextContent('Bruised');
    expect(callout).toHaveTextContent('Minor');
  });
});

// ---------------------------------------------------------------------------
// Tests — modifier breakdown
// ---------------------------------------------------------------------------

describe('OutcomeRoulette — modifier breakdown', () => {
  it('renders each modifier row with label', () => {
    render(
      <OutcomeRoulette outcomeDisplay={OUTCOME_DISPLAY} modifiers={MODIFIERS} modifierTotal={-2} />
    );

    expect(screen.getByTestId('modifier-row-Exhausted')).toBeInTheDocument();
    expect(screen.getByTestId('modifier-row-Light armour')).toBeInTheDocument();
  });

  it('shows the signed value for each modifier', () => {
    render(
      <OutcomeRoulette outcomeDisplay={OUTCOME_DISPLAY} modifiers={MODIFIERS} modifierTotal={-2} />
    );

    expect(screen.getByTestId('modifier-value-Exhausted')).toHaveTextContent('-3');
    expect(screen.getByTestId('modifier-value-Light armour')).toHaveTextContent('+1');
  });

  it('shows the modifier total with sign', () => {
    render(
      <OutcomeRoulette outcomeDisplay={OUTCOME_DISPLAY} modifiers={MODIFIERS} modifierTotal={-2} />
    );

    expect(screen.getByTestId('modifier-total')).toHaveTextContent('-2');
  });

  it('shows positive total with + prefix', () => {
    const positiveModifiers: ConsequenceOutcomeModifier[] = [
      { source_kind: 'effort', source_label: 'Effort bonus', value: 5 },
    ];

    render(
      <OutcomeRoulette
        outcomeDisplay={OUTCOME_DISPLAY}
        modifiers={positiveModifiers}
        modifierTotal={5}
      />
    );

    expect(screen.getByTestId('modifier-total')).toHaveTextContent('+5');
  });

  it('hides modifier breakdown when no modifiers', () => {
    render(<OutcomeRoulette outcomeDisplay={OUTCOME_DISPLAY} modifiers={[]} modifierTotal={0} />);

    expect(screen.queryByTestId('modifier-breakdown')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — summary
// ---------------------------------------------------------------------------

describe('OutcomeRoulette — summary', () => {
  it('shows the summary text when provided', () => {
    render(
      <OutcomeRoulette
        outcomeDisplay={OUTCOME_DISPLAY}
        modifiers={[]}
        modifierTotal={0}
        summary="You take a bruise to the ribs."
      />
    );

    expect(screen.getByTestId('outcome-summary')).toHaveTextContent(
      'You take a bruise to the ribs.'
    );
  });

  it('hides summary when not provided', () => {
    render(<OutcomeRoulette outcomeDisplay={OUTCOME_DISPLAY} modifiers={[]} modifierTotal={0} />);

    expect(screen.queryByTestId('outcome-summary')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Tests — empty states
// ---------------------------------------------------------------------------

describe('OutcomeRoulette — empty states', () => {
  it('renders without crashing when outcomeDisplay is empty', () => {
    render(<OutcomeRoulette outcomeDisplay={[]} modifiers={[]} modifierTotal={0} />);

    // No callout, no pool rows, no modifiers
    expect(screen.queryByTestId('outcome-selected-callout')).not.toBeInTheDocument();
    expect(screen.queryByTestId('outcome-pool')).not.toBeInTheDocument();
  });
});
