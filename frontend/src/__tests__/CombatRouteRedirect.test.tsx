/**
 * CombatRouteRedirect (#2197) — the old /scenes/:id/combat route now bounces
 * straight to /scenes/:id, preserving the :id param, since combat renders
 * in-scene via CombatRail instead of a dedicated page.
 */

import { render, screen } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation, useParams } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { CombatRouteRedirect } from '../App';

function DestinationStub() {
  const location = useLocation();
  const { id } = useParams();
  return (
    <div data-testid="destination" data-pathname={location.pathname} data-id={id}>
      scene page
    </div>
  );
}

describe('CombatRouteRedirect', () => {
  it('resolves /scenes/:id/combat to the scene page, preserving the id param', () => {
    render(
      <MemoryRouter initialEntries={['/scenes/42/combat']}>
        <Routes>
          <Route path="/scenes/:id" element={<DestinationStub />} />
          <Route path="/scenes/:id/combat" element={<CombatRouteRedirect />} />
        </Routes>
      </MemoryRouter>
    );

    const destination = screen.getByTestId('destination');
    expect(destination).toHaveAttribute('data-pathname', '/scenes/42');
    expect(destination).toHaveAttribute('data-id', '42');
  });
});
