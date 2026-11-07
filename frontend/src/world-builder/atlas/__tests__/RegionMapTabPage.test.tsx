import { screen } from '@testing-library/react';
import { Route, Routes } from 'react-router-dom';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { RegionMapTabPage } from '../RegionMapTabPage';

const regionMapPage = vi.fn((_props: Record<string, unknown>) => (
  <div data-testid="region-map-stub" />
));
vi.mock('../RegionMapPage', () => ({
  RegionMapPage: (props: Record<string, unknown>) => regionMapPage(props),
}));

function renderAt(path: string) {
  return renderWithProviders(
    <Routes>
      <Route path="/staff/world-builder/map/:regionId" element={<RegionMapTabPage />} />
    </Routes>,
    { initialEntries: [path] }
  );
}

describe('RegionMapTabPage', () => {
  beforeEach(() => regionMapPage.mockClear());

  it('opens the region in the URL, standalone, with nothing focused', () => {
    renderAt('/staff/world-builder/map/3');
    expect(regionMapPage).toHaveBeenCalledWith({
      regionId: 3,
      focusAreaId: null,
      standalone: true,
    });
  });

  it('opens on the footprint the Atlas had selected', () => {
    renderAt('/staff/world-builder/map/3?focus=10');
    expect(regionMapPage).toHaveBeenCalledWith({
      regionId: 3,
      focusAreaId: 10,
      standalone: true,
    });
  });

  it('refuses a region id that is not a number, without fetching', () => {
    renderAt('/staff/world-builder/map/catenys');
    expect(regionMapPage).not.toHaveBeenCalled();
    expect(screen.getByTestId('region-map-error')).toHaveTextContent(
      'The map could not be loaded.'
    );
  });
});
