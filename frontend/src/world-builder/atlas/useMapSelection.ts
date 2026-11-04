import { useMemo } from 'react';

import type { LadderRow } from '@/almanach/types';
import type { RegionMapFootprint, RegionMapLandlessTitle, RegionMapPips } from '../types';
import { pipKey } from './regionMapCanvas';

const LANDLESS_STATION_WORDS: Record<string, string> = {
  titular: 'Titular',
  potential: 'Potential',
};

/** Titular or Potential; a seated rung that merely lacks land says nothing. */
function stationWordFor(
  landless: RegionMapLandlessTitle | null,
  row: { state: string } | null
): string | null {
  if (landless != null) return LANDLESS_STATION_WORDS[landless.station] ?? null;
  if (row != null && (row.state === 'Titular' || row.state === 'Potential')) return row.state;
  return null;
}

interface MapSelectionInput {
  data: RegionMapPips | undefined;
  ladderRows: LadderRow[];
  selectedAreaId: number | null;
  selectedTitleId: number | null;
  /** Historical Charter on: the chartered footprints' pips become the ghost. */
  charterOn: boolean;
}

/**
 * What the region map's selection means (#4983): a footprint (by area, or by the
 * title it belongs to), else a landless title the payload carries, else a ladder rung
 * the payload does not carry at all (a realm with no land on this map). The focus
 * title drives the panel, the pickers and the Historical Charter ghost.
 */
export function useMapSelection({
  data,
  ladderRows,
  selectedAreaId,
  selectedTitleId,
  charterOn,
}: MapSelectionInput) {
  const selected: RegionMapFootprint | null = useMemo(() => {
    const byArea = data?.footprints.find((f) => f.area_id === selectedAreaId) ?? null;
    if (byArea != null || selectedTitleId == null) return byArea;
    return data?.footprints.find((f) => f.title_id === selectedTitleId) ?? null;
  }, [data, selectedAreaId, selectedTitleId]);
  const selectedLandless: RegionMapLandlessTitle | null = useMemo(() => {
    if (selected != null || selectedTitleId == null) return null;
    return data?.landless_titles.find((t) => t.title_id === selectedTitleId) ?? null;
  }, [data, selected, selectedTitleId]);
  const selectedLadderRow: LadderRow | null = useMemo(() => {
    if (selected != null || selectedLandless != null || selectedTitleId == null) return null;
    return ladderRows.find((row) => row.title_id === selectedTitleId) ?? null;
  }, [ladderRows, selected, selectedLandless, selectedTitleId]);
  const focusTitleId =
    selected?.title_id ?? selectedLandless?.title_id ?? selectedLadderRow?.title_id ?? null;
  // A selection made by title (the door from a title page, a click on a footprint) names
  // a realm too; with no realm picked yet the page takes the title's.
  const focusRealmId = selected?.realm_id ?? selectedLandless?.realm_id ?? null;
  const stationWord = stationWordFor(selectedLandless, selectedLadderRow);
  // Historical Charter: every footprint whose title is in the selected title's charter.
  const charterFootprints = useMemo(() => {
    if (focusTitleId == null) return [];
    return data?.footprints.filter((f) => f.charters.includes(focusTitleId)) ?? [];
  }, [data, focusTitleId]);
  const ghostPips = useMemo(() => {
    const out = new Set<string>();
    if (!charterOn) return out;
    for (const f of charterFootprints) for (const [x, y] of f.pips) out.add(pipKey(x, y));
    return out;
  }, [charterFootprints, charterOn]);
  return {
    selected,
    selectedLandless,
    selectedLadderRow,
    focusTitleId,
    focusRealmId,
    stationWord,
    charterFootprints,
    ghostPips,
  };
}
