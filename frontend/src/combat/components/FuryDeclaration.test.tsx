import { describe, it, expect, vi } from 'vitest';
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
const resonances = [
  {
    id: 7,
    name: 'Rage',
    strength_name: 'Faint',
    provocation_cap: 1,
    tier_full_intensities: [
      { tier_id: 1, full_intensity: 9 },
      { tier_id: 2, full_intensity: 19 },
    ],
  },
  {
    id: 8,
    name: 'Wrath',
    strength_name: 'Blazing',
    provocation_cap: 3,
    tier_full_intensities: [
      { tier_id: 1, full_intensity: 10 },
      { tier_id: 2, full_intensity: 21 },
    ],
  },
];

function renderDeclaration(
  tierId: number | null,
  resonanceId: number | null,
  handlers: { onTierChange?: (id: number | null) => void } = {}
) {
  return render(
    <FuryDeclaration
      tiers={tiers}
      resonances={resonances}
      tierId={tierId}
      resonanceId={resonanceId}
      onTierChange={handlers.onTierChange ?? (() => {})}
      onResonanceChange={() => {}}
    />
  );
}

describe('FuryDeclaration', () => {
  it('is headed "Give in" with only the resonance picker until one is chosen', () => {
    renderDeclaration(null, null);
    expect(screen.getByText('Give in')).toBeInTheDocument();
    expect(screen.getByTestId('fury-resonance-select')).toBeInTheDocument();
    expect(screen.queryByTestId('fury-tier-hold')).not.toBeInTheDocument();
    expect(screen.queryByTestId('fury-preview')).not.toBeInTheDocument();
  });

  it('lists each kindled resonance with its strength word', async () => {
    renderDeclaration(null, null);
    await userEvent.click(screen.getByTestId('fury-resonance-select'));
    expect(await screen.findByText('Rage (kindled, faint)')).toBeInTheDocument();
    expect(screen.getByText('Wrath (kindled, blazing)')).toBeInTheDocument();
  });

  it('is headed with the chosen resonance and offers Hold steady plus the tiers it reaches', () => {
    renderDeclaration(null, 8);
    expect(screen.getByText('Give in to your Wrath')).toBeInTheDocument();
    expect(screen.getByTestId('fury-tier-hold')).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('fury-tier-1')).toHaveTextContent('Seething');
    expect(screen.getByTestId('fury-tier-2')).toHaveTextContent('Unbound');
    expect(screen.getByTestId('fury-depth-line')).toHaveTextContent(
      'Your Wrath is blazing: you can go as far as Unbound.'
    );
  });

  it('offers only the tiers a faint resonance reaches, so the Berserk tier is absent', () => {
    renderDeclaration(null, 7);
    expect(screen.getByTestId('fury-tier-1')).toBeInTheDocument();
    expect(screen.queryByTestId('fury-tier-2')).not.toBeInTheDocument();
    expect(screen.getByTestId('fury-depth-line')).toHaveTextContent(
      'Your Rage is faint: you can go as far as Seething.'
    );
  });

  it("previews the trade with the chosen resonance's full-share intensity", () => {
    renderDeclaration(1, 8);
    expect(screen.getByTestId('fury-preview')).toHaveTextContent(
      'Give up 6 control · Gain up to 10 intensity, by your roll'
    );
  });

  it('chooses a step and goes back to Hold steady', async () => {
    const onTierChange = vi.fn();
    renderDeclaration(null, 8, { onTierChange });
    await userEvent.click(screen.getByTestId('fury-tier-2'));
    expect(onTierChange).toHaveBeenLastCalledWith(2);
    await userEvent.click(screen.getByTestId('fury-tier-hold'));
    expect(onTierChange).toHaveBeenLastCalledWith(null);
  });
});
