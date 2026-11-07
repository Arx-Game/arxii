/**
 * Which parts of the region map page are folded away (#4993): the side panel and the realm
 * and domain pickers. One browser remembers one setting per account, shared by the Atlas's
 * map view and the map's own tab. A convenience, so unreadable storage just means open.
 */
import { useCallback, useEffect, useState } from 'react';

import { readJSON, writeJSON } from './useAtlasState';

interface MapLayout {
  panelOpen: boolean;
  pickersOpen: boolean;
}

const OPEN: MapLayout = { panelOpen: true, pickersOpen: true };

function layoutKey(accountId: number | string): string {
  return `world-builder-atlas:${accountId}:map-layout`;
}

function readLayout(accountId: number | string): MapLayout {
  return { ...OPEN, ...readJSON<Partial<MapLayout>>(layoutKey(accountId), OPEN) };
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

  return {
    panelOpen: layout.panelOpen,
    pickersOpen: layout.pickersOpen,
    togglePanel: () => toggle('panelOpen'),
    togglePickers: () => toggle('pickersOpen'),
  };
}
