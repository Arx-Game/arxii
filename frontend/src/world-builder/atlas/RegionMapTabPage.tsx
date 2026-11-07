/**
 * A region map in its own browser tab (#4993): `RegionMapPage` with the whole viewport, for
 * the drawing work the Atlas's panel is too small for. `Layout` drops the site chrome on
 * this route. `?focus=` opens on the footprint the Atlas had selected.
 */
import { useParams, useSearchParams } from 'react-router-dom';

import { RegionMapPage } from './RegionMapPage';

function positiveInt(raw: string | null | undefined): number | null {
  const value = Number(raw);
  return Number.isInteger(value) && value > 0 ? value : null;
}

export function RegionMapTabPage() {
  const { regionId: rawRegionId } = useParams();
  const [searchParams] = useSearchParams();
  const regionId = positiveInt(rawRegionId);
  if (regionId == null) {
    return (
      <div className="p-8 text-sm text-destructive" data-testid="region-map-error">
        The map could not be loaded.
      </div>
    );
  }
  return (
    <div className="min-h-0 flex-1">
      <RegionMapPage
        regionId={regionId}
        focusAreaId={positiveInt(searchParams.get('focus'))}
        standalone
      />
    </div>
  );
}
