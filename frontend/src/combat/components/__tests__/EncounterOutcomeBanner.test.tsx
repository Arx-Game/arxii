import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { EncounterOutcomeBanner } from '../EncounterOutcomeBanner';

describe('EncounterOutcomeBanner', () => {
  it('renders the outcome label', () => {
    render(
      <MemoryRouter>
        <EncounterOutcomeBanner outcome="victory" sceneId={12} />
      </MemoryRouter>
    );

    expect(screen.getByRole('status')).toHaveTextContent('Victory');
  });

  it('renders a Return to Scene link to the given sceneId', () => {
    render(
      <MemoryRouter>
        <EncounterOutcomeBanner outcome="defeat" sceneId={12} />
      </MemoryRouter>
    );

    const link = screen.getByRole('link', { name: /return to scene/i });
    expect(link).toHaveAttribute('href', '/scenes/12');
  });
});
