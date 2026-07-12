import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { EncounterOutcomeBanner } from '../EncounterOutcomeBanner';

describe('EncounterOutcomeBanner', () => {
  it('renders the outcome label', () => {
    render(<EncounterOutcomeBanner outcome="victory" />);

    expect(screen.getByRole('status')).toHaveTextContent('Victory');
  });

  // #2197: the "Return to Scene" link was removed — the banner now renders
  // inline on the scene page itself (CombatRail), so it would have been
  // self-referential.
  it('does not render a Return to Scene link', () => {
    render(<EncounterOutcomeBanner outcome="defeat" />);

    expect(screen.queryByRole('link', { name: /return to scene/i })).not.toBeInTheDocument();
  });
});
