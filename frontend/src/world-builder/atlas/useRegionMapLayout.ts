/**
 * Which parts of the region map page are folded away (#4993), the side panel and the realm
 * and domain pickers, which view the map shows (#5030) and which tiers it draws (#5157). One browser remembers one
 * setting per account, shared by the Atlas's map view and the map's own tab. A convenience,
 * so unreadable storage just means open, and All.
 */
import { useCallback, useEffect, useMemo, useState } from 'react';

import {
  DEFAULT_MAP_TIERS,
  DEFAULT_MAP_VIEW,
  isMapTier,
  isMapView,
  MAP_TIERS,
  type MapTier,
  type MapView,
} from './mapViews';
import { readJSON, writeJSON } from './useAtlasState';

interface MapLayout {
  panelOpen: boolean;
  pickersOpen: boolean;
  view: MapView;
  tiers: MapTier[];
}

const OPEN: MapLayout = {
  panelOpen: true,
  pickersOpen: true,
  view: DEFAULT_MAP_VIEW,
  tiers: [...DEFAULT_MAP_TIERS],
};

function layoutKey(accountId: number | string): string {
  return `world-builder-atlas:${accountId}:map-layout`;
}

function readLayout(accountId: number | string): MapLayout {
  const stored = readJSON<Partial<MapLayout>>(layoutKey(accountId), OPEN);
  const layout = { ...OPEN, ...stored };
  if (!isMapView(layout.view)) layout.view = DEFAULT_MAP_VIEW;
  layout.tiers = Array.isArray(layout.tiers)
    ? MAP_TIERS.filter((tier) => layout.tiers.includes(tier) && isMapTier(tier))
    : [...DEFAULT_MAP_TIERS];
  return layout;
}

export function useRegionMapLayout(accountId: number | string) {
  const [layout, setLayout] = useState<MapLayout>(() => readLayout(accountId));
  // The account arrives after the first render in a freshly opened tab.
  useEffect(() => setLayout(readLayout(accountId)), [accountId]);

  const toggle = useCallback(
    (part: 'panelOpen' | 'pickersOpen') => {
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

  const toggleTier = useCallback(
    (tier: MapTier) => {
      setLayout((current) => {
        const on = current.tiers.includes(tier);
        const tiers = MAP_TIERS.filter((t) => (t === tier ? !on : current.tiers.includes(t)));
        const next = { ...current, tiers };
        writeJSON(layoutKey(accountId), next);
        return next;
      });
    },
    [accountId]
  );
  const tiers = useMemo(() => new Set(layout.tiers), [layout.tiers]);

  return {
    panelOpen: layout.panelOpen,
    pickersOpen: layout.pickersOpen,
    view: layout.view,
    setView,
    tiers,
    toggleTier,
    togglePanel: () => toggle('panelOpen'),
    togglePickers: () => toggle('pickersOpen'),
  };
}
