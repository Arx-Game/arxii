import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { Layout } from './Layout';

vi.mock('./Header', () => ({ Header: () => <div data-testid="site-header" /> }));
vi.mock('./Footer', () => ({ Footer: () => <div data-testid="site-footer" /> }));
vi.mock('./theme-background', () => ({ ThemeBackground: () => null }));
vi.mock('./DowntimeBanner', () => ({ DowntimeBanner: () => null }));
vi.mock('@/magic/components/alterations/PendingAlterationBanner', () => ({
  PendingAlterationBanner: () => null,
}));
vi.mock('@/ceremonies/SeanceOfferBanner', () => ({ SeanceOfferBanner: () => null }));
vi.mock('@/ceremonies/ConversionOfferBanner', () => ({ ConversionOfferBanner: () => null }));

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Layout>
        <div />
      </Layout>
    </MemoryRouter>
  );
}

describe('Layout chrome', () => {
  it.each(['/game', '/staff/world-builder/map/3'])('gives %s the whole tab', (path) => {
    renderAt(path);
    expect(screen.queryByTestId('site-header')).not.toBeInTheDocument();
    expect(screen.queryByTestId('site-footer')).not.toBeInTheDocument();
  });

  it('keeps the chrome around the Atlas itself', () => {
    renderAt('/staff/world-builder');
    expect(screen.getByTestId('site-header')).toBeInTheDocument();
    expect(screen.getByTestId('site-footer')).toBeInTheDocument();
  });
});
