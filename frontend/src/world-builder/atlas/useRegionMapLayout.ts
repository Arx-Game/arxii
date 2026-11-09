/**
 * Which parts of the region map page are folded away (#4993), the side panel and the realm
 * and domain pickers, and which view the map shows (#5030). One browser remembers one
 * setting per account, shared by the Atlas's map view and the map's own tab. A convenience,
 * so unreadable storage just means open, and All.
 */
import { useCallback, useEffect, useState } from 'react';

import { DEFAULT_MAP_VIEW, isMapView, type MapView } from './mapViews';
import { readJSON, writeJSON } from './useAtlasState';

interface MapLayout {
  panelOpen: boolean;
  pickersOpen: boolean;
  view: MapView;
}

const OPEN: MapLayout = { panelOpen: true, pickersOpen: true, view: DEFAULT_MAP_VIEW };

function layoutKey(accountId: number | string): string {
  return `world-builder-atlas:${accountId}:map-layout`;
}

function readLayout(accountId: number | string): MapLayout {
  const stored = readJSON<Partial<MapLayout>>(layoutKey(accountId), OPEN);
  const layout = { ...OPEN, ...stored };
  if (!isMapView(layout.view)) layout.view = DEFAULT_MAP_VIEW;
  return layout;
}

export function useRegionMapLayout(accountId: number | string) {
  const [layout, setLayout] = useState<MapLayout>(() => readLayout(accountId));
  // The account arrives after the first render in a freshly opened tab.
  useEffect(() => setLayout(readLayout(accountId)), [accountId]);

  const toggle = useCallback(
    (part: keyof MapLayout) => {
      setLayout((current) => {
        const next = { ...current, [part]: !current[part] };
        writeJSON(layoutKey(accountId), next);
        return next;
      });
    },
    [accountId]
  );

  const setView = useCallback(
    (view: MapView) => {
      setLayout((current) => {
        const next = { ...current, view };
        writeJSON(layoutKey(accountId), next);
        return next;
      });
    },
    [accountId]
  );

  return {
    panelOpen: layout.panelOpen,
    pickersOpen: layout.pickersOpen,
    view: layout.view,
    setView,
    togglePanel: () => toggle('panelOpen'),
    togglePickers: () => toggle('pickersOpen'),
  };
}
