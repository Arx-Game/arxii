import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { FuryDeclaration } from './FuryDeclaration';

const tiers = [
  {
    id: 1,
    name: 'Simmering',
    depth: 1,
    control_penalty: 1,
    intensity_bonus: 2,
    berserk_severity: 0,
  },
  {
    id: 2,
    name: 'Unleashed',
    depth: 2,
    control_penalty: 4,
    intensity_bonus: 5,
    berserk_severity: 3,
  },
];
const anchors = [
  { id: 7, name: 'Rival', provocation_cap: 1 },
  { id: 8, name: 'Mentor', provocation_cap: 3 },
];

describe('FuryDeclaration', () => {
  it('renders tier and anchor selects', () => {
    render(
      <FuryDeclaration
        tiers={tiers}
        anchors={anchors}
        tierId={null}
        anchorId={null}
        onTierChange={() => {}}
        onAnchorChange={() => {}}
      />
    );
    expect(screen.getByTestId('fury-tier-select')).toBeInTheDocument();
    expect(screen.getByTestId('fury-anchor-select')).toBeInTheDocument();
  });

  it('shows an over-cap warning when the chosen tier exceeds the anchor cap', () => {
    render(
      <FuryDeclaration
        tiers={tiers}
        anchors={anchors}
        tierId={2} // depth 2
        anchorId={7} // cap 1
        onTierChange={() => {}}
        onAnchorChange={() => {}}
      />
    );
    expect(screen.getByTestId('fury-over-cap-warning')).toBeInTheDocument();
  });

  it('shows no over-cap warning when within cap', () => {
    render(
      <FuryDeclaration
        tiers={tiers}
        anchors={anchors}
        tierId={2} // depth 2
        anchorId={8} // cap 3
        onTierChange={() => {}}
        onAnchorChange={() => {}}
      />
    );
    expect(screen.queryByTestId('fury-over-cap-warning')).not.toBeInTheDocument();
  });
});
