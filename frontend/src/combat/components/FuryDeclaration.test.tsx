import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { FuryDeclaration } from './FuryDeclaration';

const tiers = [
  {
    id: 1,
    name: 'Seething',
    depth: 1,
    control_surrendered: 6,
    is_berserk: false,
    full_intensity: 9,
  },
  {
    id: 2,
    name: 'Unbound',
    depth: 2,
    control_surrendered: 12,
    is_berserk: true,
    full_intensity: 18,
  },
];
const anchors = [
  {
    id: 7,
    name: 'Rival',
    provocation_cap: 1,
    tier_full_intensities: [
      { tier_id: 1, full_intensity: 9 },
      { tier_id: 2, full_intensity: 19 },
    ],
  },
  {
    id: 8,
    name: 'Ilse',
    provocation_cap: 3,
    tier_full_intensities: [
      { tier_id: 1, full_intensity: 10 },
      { tier_id: 2, full_intensity: 21 },
    ],
  },
];

function renderDeclaration(tierId: number | null, anchorId: number | null) {
  return render(
    <FuryDeclaration
      tiers={tiers}
      anchors={anchors}
      tierId={tierId}
      anchorId={anchorId}
      onTierChange={() => {}}
      onAnchorChange={() => {}}
    />
  );
}

describe('FuryDeclaration', () => {
  it('is headed "Surrender control" with tier and anchor selects', () => {
    renderDeclaration(null, null);
    expect(screen.getByText('Surrender control')).toBeInTheDocument();
    expect(screen.getByTestId('fury-tier-select')).toBeInTheDocument();
    expect(screen.getByTestId('fury-anchor-select')).toBeInTheDocument();
    expect(screen.queryByTestId('fury-preview')).not.toBeInTheDocument();
  });

  it('lists each tier as the control it surrenders, marking the Berserk tier', async () => {
    renderDeclaration(null, null);
    await userEvent.click(screen.getByTestId('fury-tier-select'));
    expect(await screen.findByText('Seething: surrender 6 control')).toBeInTheDocument();
    expect(screen.getByText('Unbound: surrender 12 control (Berserk)')).toBeInTheDocument();
  });

  it("previews the trade with the chosen anchor's full-share intensity", () => {
    renderDeclaration(1, 8);
    expect(screen.getByTestId('fury-preview')).toHaveTextContent(
      '6 control → up to +10 intensity, by your roll'
    );
  });

  it('shows an over-cap warning when the chosen tier exceeds the anchor cap', () => {
    renderDeclaration(2, 7);
    expect(screen.getByTestId('fury-over-cap-warning')).toBeInTheDocument();
  });

  it('shows no over-cap warning when within cap', () => {
    renderDeclaration(2, 8);
    expect(screen.queryByTestId('fury-over-cap-warning')).not.toBeInTheDocument();
  });
});
