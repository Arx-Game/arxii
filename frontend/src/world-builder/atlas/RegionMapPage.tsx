/**
 * RegionMapPage (#4242) — the Atlas's region-map view: a region of the world map
 * drawn as 10-mile pips on one canvas, with the lattice's own zoom and pan.
 *
 * Three modes. Select: a click on a footprint opens its panel (name, tier,
 * holder, the link to its Almanach page); a drag pans. Carve: pick a rung from
 * the realm's ladder (or plant one, the way the Almanach does) and give it pips
 * with one of three tools (#4905): Brush drags a square of pips (shift takes them
 * out), Fill floods a landmass from a click, Loop fills the land inside a drawn
 * line. Paint: brush pips to a terrain. Every write dispatches a registry action
 * through `useWorldBuilderAction`; the upload is the one multipart endpoint.
 * Alt-drag pans in any mode. Only the domain being carved draws an outline;
 * neighbours are shading. A view picker on the panel (#5030) says what is drawn:
 * Geography, Domain, Domain-Vassal or All, anchored on the selected domain; names
 * and seats are drawn on a screen-space layer so they never stack.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight, Maximize2 } from 'lucide-react';
import { toast } from 'sonner';

import { useAlmanachMutation, useLadder, useRealms, useRegionalEvents } from '@/almanach/queries';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';
import { useAccount } from '@/store/hooks';

import { useRegionMapPipsQuery, useRegionMapUpload, useWorldBuilderAction } from '../queries';
import type { RegionMapFootprint } from '../types';
import { regionMapFileUrl } from '../api';
import { useWorldBuilderActor } from '../useWorldBuilderActor';
import {
  DEFAULT_VIEW,
  MAP_ZOOM,
  fitView,
  readLatticeView,
  writeLatticeView,
  zoomAround,
  type LatticeView,
} from './latticeState';
import {
  EMPTY_HISTORY,
  afterHolders,
  beforeHolders,
  chunk,
  parseChanged,
  pushEntry,
  restoreRedo,
  restoreUndo,
  takeRedo,
  takeUndo,
  type CarveEntry,
  type CarveHistory,
  type PipChange,
  type PipHolder,
} from './carveHistory';
import {
  MAP_CELL_LINES_HIDE_BELOW,
  PIP_PX,
  drawNamesLayer,
  drawRegionMap,
  footprintAt,
  pipAt,
  pipKey,
  regionBounds,
  type RegionBounds,
  type ScreenMarker,
} from './regionMapCanvas';
import {
  BRUSH_WIDTHS,
  brushPips,
  linePips,
  floodHeld,
  floodLand,
  loopInterior,
  type BrushWidth,
  type Pip,
} from './regionMapFill';
import { regionMapTabUrl } from './constants';
import { clearMapFocus, peekMapFocus } from './mapFocus';
import {
  borderWidths,
  markerRadius,
  placeNames,
  rootsOf,
  seatMarkers,
  struckFootprints,
  visibleFootprints,
  type MapView,
  type SeatMarker,
} from './mapViews';
import { FoldToggle, RegionMapPanel } from './RegionMapPanel';
import { CarvePickers, SelectPickers } from './SelectPickers';
import { useMapSelection } from './useMapSelection';
import { useRegionMapLayout } from './useRegionMapLayout';

type MapMode = 'select' | 'carve' | 'paint';
const MODE_LABELS: Record<MapMode, string> = { select: 'Select', carve: 'Carve', paint: 'Paint' };
// #5189: Paint's two river entries, listed after the terrains. They are not terrains:
// a river is a line across the ground and leaves the ground as it is.
const PAINT_RIVER = '+river';
const PAINT_ERASE_RIVER = '-river';
type CarveTool = 'brush' | 'fill' | 'loop';
const TOOL_LABELS: Record<CarveTool, string> = { brush: 'Brush', fill: 'Fill', loop: 'Loop' };

/** How far outside a seat marker's edge a press still grabs it (#5157), in screen pixels. */
const SEAT_GRAB_PAD_PX = 4;

/** Maps a pip's centre to the viewport, at the current zoom and pan. */
function projector(bounds: RegionBounds, view: LatticeView) {
  return (x: number, y: number): [number, number] => [
    (x - bounds.x0 + 0.5) * PIP_PX * view.zoom + view.panX,
    (y - bounds.y0 + 0.5) * PIP_PX * view.zoom + view.panY,
  ];
}

/** The barony marker under a press at viewport (px, py), the nearest when several are close. */
function seatMarkerAt(
  markers: SeatMarker[],
  project: (x: number, y: number) => [number, number],
  px: number,
  py: number
): SeatMarker | null {
  let best: SeatMarker | null = null;
  let bestDistance = Infinity;
  for (const marker of markers) {
    if (marker.baronyId == null) continue;
    const [sx, sy] = project(marker.x, marker.y);
    const distance = Math.hypot(sx - px, sy - py);
    if (distance <= markerRadius(marker.rank) + SEAT_GRAB_PAD_PX && distance < bestDistance) {
      best = marker;
      bestDistance = distance;
    }
  }
  return best;
}

/**
 * Where a barony's seat may be dropped (#5157): the pips its county holds itself, which is
 * the county's footprint less every pip a child of the county stands on.
 */
function seatDropTargets(
  footprints: RegionMapFootprint[],
  barony: RegionMapFootprint
): Set<string> {
  const county = footprints.find((f) => f.area_id === barony.parent_id);
  const targets = new Set<string>();
  if (!county) return targets;
  for (const [x, y] of county.pips) targets.add(pipKey(x, y));
  for (const child of footprints) {
    if (child.parent_id !== county.area_id) continue;
    for (const [x, y] of child.pips) targets.delete(pipKey(x, y));
  }
  return targets;
}

/** What the folded pickers still say: the domain being carved, or the selected one. */
function pickedName(candidates: ({ name: string; tier?: string } | null)[]): string {
  const picked = candidates.find((candidate) => candidate != null);
  if (!picked) return '';
  return picked.name || (picked.tier ? `unnamed ${picked.tier}` : '');
}

const WHEEL_ZOOM_RATE = 0.0015;

function cursorClass(panning: boolean, mode: MapMode): string {
  if (panning) return 'cursor-grabbing';
  return mode === 'select' ? 'cursor-grab' : 'cursor-crosshair';
}
const DRAG_THRESHOLD_PX = 4;
const NO_DOMAIN_MESSAGE = 'Pick a domain to carve.';
/** The server's per-call cap (`MAX_FOOTPRINT_PIPS_PER_CALL`); a bigger fill goes in batches. */
const MAX_PIPS_PER_CALL = 20000;
/** View storage is keyed by node id; region maps live past every area id. */
const VIEW_NODE_OFFSET = 1_000_000;
const PLANT_TIERS = ['kingdom', 'duchy', 'county', 'march', 'barony'] as const;

export interface RegionMapPageProps {
  regionId: number;
  /** An area to open the panel on when the map opens (from an area page's On the map). */
  focusAreaId?: number | null;
  /** True when the page already has the whole tab (#4993), so it offers no maximize. */
  standalone?: boolean;
}

export function RegionMapPage({
  regionId,
  focusAreaId = null,
  standalone = false,
}: RegionMapPageProps) {
  const account = useAccount();
  const accountId = account?.id ?? 'anon';
  const nodeId = VIEW_NODE_OFFSET + regionId;
  const { data, isLoading, isError } = useRegionMapPipsQuery(regionId);
  const characterId = useWorldBuilderActor();
  const { mutateAsync: runAction } = useWorldBuilderAction(characterId ?? 0, null);
  const upload = useRegionMapUpload(regionId);
  const {
    panelOpen,
    togglePanel,
    pickersOpen,
    togglePickers,
    view: homeView,
    setView: setHomeView,
    tiers,
    toggleTier,
  } = useRegionMapLayout(accountId);

  const [mode, setMode] = useState<MapMode>('select');
  // #5030: Carve mode starts on Domain-Vassal for the domain being carved, as a default only;
  // a view picked while carving holds until changed or the mode is left, and never touches
  // the remembered view the other modes use.
  const [carveView, setCarveView] = useState<MapView>('domain-vassal');
  const mapView: MapView = mode === 'carve' ? carveView : homeView;
  const setMapView = (next: MapView) => {
    if (mode === 'carve') setCarveView(next);
    else setHomeView(next);
  };
  const switchMode = (next: MapMode) => {
    if (next === 'carve' && mode !== 'carve') setCarveView('domain-vassal');
    setMode(next);
  };
  const [selectedAreaId, setSelectedAreaId] = useState<number | null>(focusAreaId);
  // #4983: a title selected by name, which may hold no land; and its Historical Charter.
  const [selectedTitleId, setSelectedTitleId] = useState<number | null>(() => peekMapFocus());
  useEffect(() => clearMapFocus(), []);
  const [charterOn, setCharterOn] = useState(false);
  const [realmId, setRealmId] = useState<number | null>(null);
  const [carveTitleId, setCarveTitleId] = useState<number | null>(null);
  // #4988: Adjust lets a carve take pips from a sibling rung instead of skipping them.
  const [adjust, setAdjust] = useState(false);
  const [paintTerrain, setPaintTerrain] = useState<string>('plain');
  const [tool, setTool] = useState<CarveTool>('brush');
  const [brushWidth, setBrushWidth] = useState<BrushWidth>(1);
  const [history, setHistory] = useState<CarveHistory>(EMPTY_HISTORY);
  const [clearOpen, setClearOpen] = useState(false);
  const [resetRiversOpen, setResetRiversOpen] = useState(false);
  const paintsRiver = paintTerrain === PAINT_RIVER || paintTerrain === PAINT_ERASE_RIVER;
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [pendingRemove, setPendingRemove] = useState(false);
  const [plantOpen, setPlantOpen] = useState(false);
  const [plantName, setPlantName] = useState('');
  const [plantTier, setPlantTier] = useState<(typeof PLANT_TIERS)[number]>('county');

  const { data: realmsPage } = useRealms();
  const realms = realmsPage?.results ?? [];
  const { data: ladder, refetch: refetchLadder } = useLadder(realmId, 'staff');
  const plantRung = useAlmanachMutation('almanach_plant_rung');
  // #5080: the open regional events over the realm, shaded on every footprint beneath
  const { data: eventsPage } = useRegionalEvents(realmId);
  const events = useMemo(() => eventsPage?.results ?? [], [eventsPage]);
  const struck = useMemo(
    () =>
      struckFootprints(
        data?.footprints ?? [],
        events.map((e) => e.area_id)
      ),
    [data, events]
  );

  useEffect(() => {
    setSelectedAreaId(focusAreaId);
  }, [focusAreaId, regionId]);

  // ---- the view: zoom + pan, remembered per region ----
  const [view, setView] = useState<LatticeView>(() => readLatticeView(accountId, nodeId, MAP_ZOOM));
  useEffect(() => {
    setView(readLatticeView(accountId, nodeId, MAP_ZOOM));
  }, [accountId, nodeId]);
  useEffect(() => {
    writeLatticeView(accountId, nodeId, view);
  }, [accountId, nodeId, view]);
  const viewportRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const namesRef = useRef<HTMLCanvasElement>(null);

  // The viewport only exists once the map has loaded, so the listener waits for it. Attached
  // by hand because React's onWheel is passive, and preventDefault is what stops Ctrl+scroll
  // and a trackpad pinch from zooming the browser page (#4993).
  const mapLoaded = data != null;
  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return undefined;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      // Plain scroll moves the map; Ctrl+scroll zooms it (#4993).
      if (!event.ctrlKey && !event.metaKey) {
        setView((prev) => ({
          ...prev,
          panX: prev.panX - event.deltaX,
          panY: prev.panY - event.deltaY,
        }));
        return;
      }
      const rect = viewport.getBoundingClientRect();
      const factor = Math.exp(-event.deltaY * WHEEL_ZOOM_RATE);
      setView((prev) =>
        zoomAround(prev, factor, event.clientX - rect.left, event.clientY - rect.top, MAP_ZOOM)
      );
    };
    viewport.addEventListener('wheel', onWheel, { passive: false });
    return () => viewport.removeEventListener('wheel', onWheel);
  }, [mapLoaded]);

  const bounds = data ? regionBounds(data.region) : null;
  const canvasW = bounds ? bounds.width * PIP_PX : 0;
  const canvasH = bounds ? bounds.height * PIP_PX : 0;
  const insideRegion = ([x, y]: Pip) =>
    bounds != null &&
    x >= bounds.x0 &&
    y >= bounds.y0 &&
    x < bounds.x0 + bounds.width &&
    y < bounds.y0 + bounds.height;

  // A region never looked at before opens fitted to the viewport; a remembered view stays.
  const fittedRef = useRef<number | null>(null);
  useEffect(() => {
    if (!canvasW || fittedRef.current === regionId) return;
    fittedRef.current = regionId;
    const stored = readLatticeView(accountId, nodeId, MAP_ZOOM);
    if (stored.zoom !== DEFAULT_VIEW.zoom || stored.panX !== 0 || stored.panY !== 0) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    setView(fitView(canvasW, canvasH, viewport.clientWidth, viewport.clientHeight, MAP_ZOOM));
  }, [accountId, canvasH, canvasW, nodeId, regionId]);

  const fitToMap = () => {
    const viewport = viewportRef.current;
    if (!viewport || !canvasW) return;
    setView(fitView(canvasW, canvasH, viewport.clientWidth, viewport.clientHeight, MAP_ZOOM));
  };
  const zoomBy = (factor: number) => {
    const viewport = viewportRef.current;
    const cx = viewport ? viewport.clientWidth / 2 : 0;
    const cy = viewport ? viewport.clientHeight / 2 : 0;
    setView((prev) => zoomAround(prev, factor, cx, cy, MAP_ZOOM));
  };

  const ladderRows = useMemo(() => ladder?.rows ?? [], [ladder]);
  const {
    selected,
    selectedLandless,
    selectedLadderRow,
    focusTitleId,
    focusRealmId,
    stationWord,
    charterFootprints,
    ghostPips,
  } = useMapSelection({ data, ladderRows, selectedAreaId, selectedTitleId, charterOn });
  useEffect(() => {
    if (realmId == null && focusRealmId != null) setRealmId(focusRealmId);
  }, [focusRealmId, realmId]);
  // #5116: the domain the selected one lies in, for the panel's way up.
  const selectedAbove = useMemo(
    () =>
      selected?.parent_id == null
        ? null
        : (data?.footprints.find((f) => f.area_id === selected.parent_id) ?? null),
    [data, selected]
  );
  const carveTarget = useMemo(
    () => ladder?.rows.find((row) => row.title_id === carveTitleId) ?? null,
    [ladder, carveTitleId]
  );
  // #5030: the view's anchor is the domain being carved, else the selected one, else the
  // picked realm's roots; the view decides which footprints are drawn at all.
  const anchorFootprint = useMemo(() => {
    if (mode === 'carve') return data?.footprints.find((f) => f.title_id === carveTitleId) ?? null;
    return selected;
  }, [carveTitleId, data, mode, selected]);
  const anchors = useMemo(() => {
    if (anchorFootprint) return [anchorFootprint];
    return rootsOf(data?.footprints ?? [], realmId);
  }, [anchorFootprint, data, realmId]);
  // What the view is drawn around: that domain's name, else the realm's. While carving
  // the anchor is the domain being carved, not the selection the panel shows beneath, so
  // the caption never says "selected" (#5118: it read "no domain selected" over one).
  const anchorCaption = anchorFootprint
    ? anchorFootprint.name || `unnamed ${anchorFootprint.level_display.toLowerCase()}`
    : (realms.find((r) => r.id === realmId)?.name ?? 'all realms');
  // The domain being carved is always drawn, whatever the view: Geography while carving
  // shows the terrain and only that one outline (#5030).
  const visible = useMemo(() => {
    const shown = visibleFootprints(mapView, data?.footprints ?? [], anchors);
    if (mode === 'carve' && anchorFootprint && !shown.includes(anchorFootprint)) {
      return [...shown, anchorFootprint];
    }
    return shown;
  }, [anchorFootprint, anchors, data, mapView, mode]);
  const cellLines = view.zoom >= MAP_CELL_LINES_HIDE_BELOW;

  // The lines between the tier below the anchor (#5056): the view's borders.
  const borders = useMemo(
    () => borderWidths(mapView, data?.footprints ?? [], anchors, tiers),
    [anchors, data, mapView, tiers]
  );
  // The seat markers the view draws (#5157): the handles of the seat drag too.
  const markers = useMemo(
    () => seatMarkers(mapView, data?.footprints ?? [], anchors, tiers),
    [anchors, data, mapView, tiers]
  );
  // A seat drag in progress: the barony, and the pips it may be dropped on, tinted.
  const [seatDrag, setSeatDrag] = useState<{ baronyId: number; targets: Set<string> } | null>(null);
  const [seatGhost, setSeatGhost] = useState<ScreenMarker | null>(null);

  // The one footprint that draws an edge: the domain being carved, or the selected one.
  const outlineAreaIds = useMemo(() => {
    if (mode === 'carve') {
      const target = data?.footprints.find((f) => f.title_id === carveTitleId);
      return new Set(target ? [target.area_id] : []);
    }
    if (mode === 'select' && selectedAreaId != null) return new Set([selectedAreaId]);
    return new Set<number>();
  }, [carveTitleId, data, mode, selectedAreaId]);

  // ---- drawing ----
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    drawRegionMap(
      ctx,
      { ...data, footprints: visible },
      {
        pending: seatDrag ? seatDrag.targets : pending,
        pendingRemove: seatDrag ? false : pendingRemove,
        selectedAreaId,
        outlineAreaIds,
        borderWidths: borders,
        ghostPips: mapView === 'geography' ? undefined : ghostPips,
        cellLines,
        struckAreaIds: struck,
      }
    );
  }, [
    borders,
    cellLines,
    data,
    ghostPips,
    mapView,
    outlineAreaIds,
    pending,
    pendingRemove,
    seatDrag,
    selectedAreaId,
    struck,
    visible,
  ]);

  // ---- the names layer: seats and names in screen space, redrawn on view, zoom, pan or
  // a change of viewport size (folding the panel or the pickers, resizing the window) ----
  const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return undefined;
    const measure = () =>
      setViewportSize((prev) =>
        prev.width === viewport.clientWidth && prev.height === viewport.clientHeight
          ? prev
          : { width: viewport.clientWidth, height: viewport.clientHeight }
      );
    measure();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, [mapLoaded]);
  useEffect(() => {
    const canvas = namesRef.current;
    if (!canvas || !data || !bounds) return;
    const size = viewportSize;
    canvas.width = size.width;
    canvas.height = size.height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const project = projector(bounds, view);
    ctx.font = '12px "Cormorant Garamond", Georgia, serif';
    const labels = placeNames(
      mapView,
      data.footprints,
      anchors,
      project,
      (text) => ctx.measureText(text).width,
      tiers
    );
    const dots = markers.map((marker) => {
      const [x, y] = project(marker.x, marker.y);
      return { x, y, r: markerRadius(marker.rank) };
    });
    drawNamesLayer(ctx, size, dots, labels, seatGhost);
  }, [anchors, bounds, data, mapView, markers, seatGhost, tiers, view, viewportSize]);

  // ---- pointer handling: pan, select, or drag pips ----
  const [panning, setPanning] = useState(false);
  // a seat press waiting for its pointerup; cleared on cancel and on unmount (#4988)
  const seatDragCleanup = useRef<(() => void) | null>(null);
  useEffect(() => () => seatDragCleanup.current?.(), []);
  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !data) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    const rect = viewport.getBoundingClientRect();
    const startX = event.clientX;
    const startY = event.clientY;
    const origin = view;
    const panMode = mode === 'select' || event.altKey;
    if (!panMode && mode === 'carve' && !event.shiftKey) {
      // #4988: a press on a barony's seat marker starts a seat drag, not a carve. The
      // handle is the marker as drawn plus a few pixels (#5157), never one exact pip.
      const project = projector(regionBounds(data.region), view);
      const grabbed = seatMarkerAt(markers, project, startX - rect.left, startY - rect.top);
      const seatOf = grabbed ? data.footprints.find((f) => f.area_id === grabbed.baronyId) : null;
      if (grabbed && seatOf) {
        seatDragCleanup.current?.();
        const targets = seatDropTargets(data.footprints, seatOf);
        const radius = markerRadius(grabbed.rank);
        const stop = () => {
          window.removeEventListener('pointermove', onSeatMove);
          window.removeEventListener('pointerup', onSeatUp);
          window.removeEventListener('pointercancel', stop);
          seatDragCleanup.current = null;
          setSeatDrag(null);
          setSeatGhost(null);
        };
        const onSeatMove = (moveEvent: PointerEvent) => {
          setSeatGhost({
            x: moveEvent.clientX - rect.left,
            y: moveEvent.clientY - rect.top,
            r: radius,
          });
        };
        const onSeatUp = (upEvent: PointerEvent) => {
          stop();
          const drop = pipAt(data.region, view, rect, upEvent.clientX, upEvent.clientY);
          // a drop anywhere but the county's own ground does nothing
          if (!drop || !targets.has(pipKey(drop[0], drop[1]))) return;
          void moveSeat(seatOf, drop);
        };
        window.addEventListener('pointermove', onSeatMove);
        window.addEventListener('pointerup', onSeatUp);
        window.addEventListener('pointercancel', stop);
        seatDragCleanup.current = stop;
        setSeatDrag({ baronyId: seatOf.area_id, targets });
        return;
      }
    }
    if (!panMode && mode === 'carve' && carveTitleId == null) {
      // A carve with nothing picked is a mistake, not a gesture: say so before any
      // drag or preview starts (#4935).
      toast.error(NO_DOMAIN_MESSAGE);
      return;
    }
    // #5189: a river stroke is one pip wide and joined between pointer samples; Shift
    // or the Erase river entry erases
    const riverStroke = mode === 'paint' && paintsRiver;
    const remove = event.shiftKey || (riverStroke && paintTerrain === PAINT_ERASE_RIVER);
    let moved = false;
    const dragged = new Set<string>();
    const path: Pip[] = [];
    const carveTool: CarveTool = mode === 'paint' ? 'brush' : tool;
    const stroke = (pip: Pip): Pip[] => {
      if (riverStroke) return linePips(path.at(-1) ?? pip, pip);
      return carveTool === 'brush' ? brushPips(pip, brushWidth).filter(insideRegion) : [pip];
    };
    const addPip = (clientX: number, clientY: number) => {
      const pip = pipAt(data.region, view, rect, clientX, clientY);
      if (!pip) return;
      const pips = stroke(pip);
      for (const [x, y] of pips) dragged.add(pipKey(x, y));
      path.push(pip);
      setPending(new Set(dragged));
      setPendingRemove(remove);
    };
    if (!panMode) addPip(startX, startY);
    const onMove = (moveEvent: PointerEvent) => {
      const dx = moveEvent.clientX - startX;
      const dy = moveEvent.clientY - startY;
      if (!moved && Math.hypot(dx, dy) < DRAG_THRESHOLD_PX) return;
      moved = true;
      if (panMode) {
        setPanning(true);
        setView({ zoom: origin.zoom, panX: origin.panX + dx, panY: origin.panY + dy });
      } else {
        addPip(moveEvent.clientX, moveEvent.clientY);
      }
    };
    const onUp = (upEvent: PointerEvent) => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      setPanning(false);
      if (panMode) {
        if (!moved) {
          const pip = pipAt(data.region, view, rect, upEvent.clientX, upEvent.clientY);
          const hit = pip ? footprintAt(data.footprints, pip[0], pip[1]) : null;
          setSelectedAreaId(hit?.area_id ?? null);
          setSelectedTitleId(hit?.title_id ?? null);
        }
        return;
      }
      setPending(new Set());
      if (carveTool === 'fill') {
        if (moved || path.length === 0 || carveTitleId == null) return;
        const pips = remove
          ? floodHeld(data, path[0], carveTitleId)
          : floodLand(data, path[0], carveTitleId, ladderRows);
        if (pips.length > 0) void commit(pips, remove);
        return;
      }
      const pips =
        carveTool === 'loop'
          ? loopInterior(data, path)
          : [...dragged].map((key) => key.split(',').map(Number) as Pip);
      if (pips.length === 0) return;
      void commit(pips, remove);
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const commitCarve = async (pips: Pip[], remove: boolean, titleId: number) => {
    // Every batch that landed is undoable, even when a later batch is refused or
    // the request fails, so the entry is pushed whatever way the loop ends.
    const changed: PipChange[] = [];
    busyRef.current = true;
    try {
      for (const part of chunk(pips, MAX_PIPS_PER_CALL)) {
        const result = await runAction({
          key: 'atlas_carve_footprint',
          kwargs: {
            title_id: titleId,
            [remove ? 'remove' : 'add']: part,
            ...(adjust ? { take_from_siblings: true } : {}),
          },
        });
        if (result.success === false) break;
        changed.push(...parseChanged(result.data));
      }
    } finally {
      busyRef.current = false;
      setHistory((h) => pushEntry(h, { titleId: titleId, changed }));
    }
  };

  const commit = async (pips: [number, number][], remove: boolean) => {
    if (characterId == null) {
      toast.error(
        'Select a character to build as; builder actions dispatch through your played character.'
      );
      return;
    }
    try {
      if (mode === 'carve') {
        if (carveTitleId == null) {
          toast.error(NO_DOMAIN_MESSAGE);
          return;
        }
        await commitCarve(pips, remove, carveTitleId);
      } else if (mode === 'paint' && paintsRiver) {
        await runAction({
          key: 'atlas_paint_river',
          kwargs: { region_id: regionId, pips, river: !remove },
        });
      } else if (mode === 'paint') {
        await runAction({
          key: 'atlas_paint_terrain',
          kwargs: { region_id: regionId, pips, terrain: paintTerrain },
        });
      }
    } catch {
      // the mutation already toasted
    }
  };

  // #5189: every river on the region goes back to what its map file gives
  const resetRivers = async () => {
    if (characterId == null) return;
    try {
      await runAction({ key: 'atlas_reset_rivers', kwargs: { region_id: regionId } });
    } catch {
      // the mutation already toasted
    }
  };

  // #4988: the seat drag; its `changed` is one undo entry like a carve's
  const moveSeat = async (barony: RegionMapFootprint, drop: Pip) => {
    if (characterId == null || busyRef.current) return;
    busyRef.current = true;
    try {
      const result = await runAction({
        key: 'atlas_move_seat',
        kwargs: { area_id: barony.area_id, pip: drop },
      });
      if (result.success !== false) {
        const changed = parseChanged(result.data);
        // a barony from the Areas tree may carry no Title; undo only reads `changed`
        const titleId = barony.title_id ?? carveTitleId ?? 0;
        setHistory((h) => pushEntry(h, { titleId, changed }));
      }
    } catch {
      // the mutation already toasted
    } finally {
      busyRef.current = false;
    }
  };

  // ---- undo, redo, clear (#4905): restores write prior holders back, never an inverse carve
  const restore = async (holders: PipHolder[]): Promise<boolean> => {
    try {
      for (const part of chunk(holders, MAX_PIPS_PER_CALL)) {
        const result = await runAction({ key: 'atlas_restore_footprint', kwargs: { pips: part } });
        if (result.success === false) return false;
      }
      return true;
    } catch {
      return false; // the mutation already toasted
    }
  };
  // One write at a time for the history: a held Ctrl+Z would otherwise send overlapping
  // restores that can land out of order, and an undo pressed while a fill is still
  // committing would undo the gesture before it and lose the redo when the fill lands.
  const busyRef = useRef(false);
  const undo = async () => {
    if (busyRef.current) return;
    const taken = takeUndo(history);
    if (!taken.entry) return;
    const entry: CarveEntry = taken.entry;
    busyRef.current = true;
    setHistory(taken.history);
    try {
      if (!(await restore(beforeHolders(entry)))) setHistory((h) => restoreUndo(h, entry));
    } finally {
      busyRef.current = false;
    }
  };
  const redo = async () => {
    if (busyRef.current) return;
    const taken = takeRedo(history);
    if (!taken.entry) return;
    const entry: CarveEntry = taken.entry;
    busyRef.current = true;
    setHistory(taken.history);
    try {
      if (!(await restore(afterHolders(entry)))) setHistory((h) => restoreRedo(h, entry));
    } finally {
      busyRef.current = false;
    }
  };
  const clearTarget = async () => {
    setClearOpen(false);
    if (carveTitleId == null || busyRef.current) return;
    busyRef.current = true;
    try {
      const result = await runAction({
        key: 'atlas_clear_footprint',
        kwargs: { title_id: carveTitleId },
      });
      if (result.success === false) return;
      setHistory((h) =>
        pushEntry(h, { titleId: carveTitleId, changed: parseChanged(result.data) })
      );
    } catch {
      // the mutation already toasted
    } finally {
      busyRef.current = false;
    }
  };
  const keysRef = useRef({ undo, redo });
  keysRef.current = { undo, redo };
  useEffect(() => {
    if (mode !== 'carve') return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      const target = event.target as HTMLElement | null;
      if (target && /^(input|select|textarea)$/i.test(target.tagName)) return;
      const key = event.key.toLowerCase();
      if (key === 'z' && event.shiftKey) void keysRef.current.redo();
      else if (key === 'z') void keysRef.current.undo();
      else if (key === 'y') void keysRef.current.redo();
      else return;
      event.preventDefault();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mode]);

  // The side panel follows the domain being carved, not the last Select-mode click
  // (#5011): picking a carve domain, or planting one, selects it too.
  const pickCarveDomain = (id: number | null) => {
    setCarveTitleId(id);
    setSelectedTitleId(id);
    setSelectedAreaId(data?.footprints.find((f) => f.title_id === id)?.area_id ?? null);
  };

  // A carve target and a selection belong to the realm they were picked in: changing
  // the realm, in either mode, drops both, or Carve would keep aiming at a rung of the
  // realm just left with its picker reading blank (#5058).
  const changeRealm = (id: number | null) => {
    if (id === realmId) return;
    setRealmId(id);
    setCarveTitleId(null);
    setSelectedTitleId(null);
    setSelectedAreaId(null);
  };

  const plant = async () => {
    if (realmId == null || !plantName.trim()) return;
    try {
      const result = await plantRung.mutateAsync({
        realm_id: realmId,
        tier: plantTier,
        name: plantName.trim(),
        parent_title_id: carveTarget?.title_id,
      });
      const titleId = result?.data?.title_id;
      await refetchLadder();
      if (typeof titleId === 'number') pickCarveDomain(titleId);
      setPlantName('');
      setPlantOpen(false);
      setMode('carve');
    } catch {
      // toasted by the mutation
    }
  };

  const onFilePicked = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (file) upload.mutate(file);
  };

  if (isLoading) {
    return (
      <div className="p-8 text-sm text-muted-foreground" data-testid="region-map-loading">
        Loading the map…
      </div>
    );
  }
  if (isError || !data || !bounds) {
    return (
      <div className="p-8 text-sm text-destructive" data-testid="region-map-error">
        The map could not be loaded.
      </div>
    );
  }
  const { region } = data;
  const miles = region.width_cells * 100;
  const pickedDomainName = pickedName(
    mode === 'carve' ? [carveTarget] : [selected, selectedLandless, selectedLadderRow]
  );
  const brushWidthSelect = (
    <select
      className="h-8 rounded-md border bg-background px-2 text-sm"
      value={brushWidth}
      onChange={(event) => setBrushWidth(Number(event.target.value) as BrushWidth)}
      aria-label="brush width"
      data-testid="brush-width"
    >
      {BRUSH_WIDTHS.map((width) => (
        <option key={width} value={width}>
          {width}
        </option>
      ))}
    </select>
  );

  return (
    <section className="flex h-full min-h-0 flex-col" data-testid="region-map-page">
      <header className="flex flex-wrap items-baseline gap-3 px-6 pt-5">
        <h2 className="theme-heading text-2xl font-semibold [font-variant:small-caps]">
          {region.name}
        </h2>
        <span className="font-body text-sm italic text-muted-foreground">
          {region.width_cells} × {region.height_cells} cells · {miles} miles across
          {region.latest_upload ? ` · ${region.latest_upload.file_name}` : ''}
        </span>
        <div className="ml-auto flex items-center gap-2">
          {!standalone && (
            <Button type="button" variant="ghost" size="sm" asChild>
              <a
                href={regionMapTabUrl(region.id, selectedAreaId)}
                target="_blank"
                rel="noopener"
                aria-label="Open the map in its own tab"
                title="Open the map in its own tab"
                data-testid="region-map-maximize"
              >
                <Maximize2 className="h-4 w-4" aria-hidden="true" />
              </a>
            </Button>
          )}
          <label className="cursor-pointer">
            <input
              type="file"
              accept=".map,text/plain"
              className="hidden"
              onChange={onFilePicked}
              data-testid="region-map-file"
              disabled={upload.isPending}
            />
            <Button type="button" variant="outline" size="sm" asChild>
              <span>{upload.isPending ? 'Rasterizing…' : 'Upload .map'}</span>
            </Button>
          </label>
          {region.latest_upload && (
            <Button type="button" variant="ghost" size="sm" asChild>
              <a href={regionMapFileUrl(region.id)} download={region.latest_upload.file_name}>
                Download
              </a>
            </Button>
          )}
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2 px-6 py-3" data-testid="region-map-modes">
        {(['select', 'carve', 'paint'] as const).map((m) => (
          <Button
            key={m}
            type="button"
            size="sm"
            variant={mode === m ? 'default' : 'outline'}
            aria-pressed={mode === m}
            onClick={() => switchMode(m)}
          >
            {MODE_LABELS[m]}
          </Button>
        ))}
        {mode === 'paint' && (
          <>
            <select
              className="h-8 rounded-md border bg-background px-2 text-sm"
              value={paintTerrain}
              onChange={(event) => setPaintTerrain(event.target.value)}
              aria-label="terrain"
              data-testid="paint-terrain"
            >
              {data.terrains.map((terrain) => (
                <option key={terrain} value={terrain}>
                  {terrain}
                </option>
              ))}
              <option value={PAINT_RIVER}>River</option>
              <option value={PAINT_ERASE_RIVER}>Erase river</option>
            </select>
            {!paintsRiver && brushWidthSelect}
            {paintsRiver && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setResetRiversOpen(true)}
                data-testid="reset-rivers"
              >
                Reset rivers
              </Button>
            )}
          </>
        )}
        {mode !== 'paint' && (
          <>
            <FoldToggle
              open={pickersOpen}
              what="realm and domain"
              openIcon={ChevronLeft}
              foldedIcon={ChevronRight}
              onToggle={togglePickers}
              testId="pickers-toggle"
            />
            {!pickersOpen && pickedDomainName && (
              <span className="font-body text-sm" data-testid="picked-domain">
                {pickedDomainName}
              </span>
            )}
          </>
        )}
        {mode === 'select' && pickersOpen && (
          <SelectPickers
            realms={realms}
            realmId={realmId}
            onRealm={changeRealm}
            ladderRows={ladderRows}
            focusTitleId={focusTitleId}
            onTitle={(id) => {
              setSelectedTitleId(id);
              setSelectedAreaId(data.footprints.find((f) => f.title_id === id)?.area_id ?? null);
            }}
          />
        )}
        {mode === 'carve' && (
          <>
            {pickersOpen && (
              <CarvePickers
                realms={realms}
                realmId={realmId}
                onRealm={changeRealm}
                ladderRows={ladderRows}
                carveTitleId={carveTitleId}
                onDomain={pickCarveDomain}
                onCreate={() => setPlantOpen((open) => !open)}
              />
            )}
            <span className="mx-1 h-6 border-l" aria-hidden="true" />
            <span className="flex items-center gap-2" data-testid="carve-tools">
              {(['brush', 'fill', 'loop'] as const).map((t) => (
                <Button
                  key={t}
                  type="button"
                  size="sm"
                  variant={tool === t ? 'default' : 'outline'}
                  aria-pressed={tool === t}
                  disabled={carveTitleId == null}
                  onClick={() => setTool(t)}
                >
                  {TOOL_LABELS[t]}
                </Button>
              ))}
              {tool === 'brush' && brushWidthSelect}
              <Button
                type="button"
                size="sm"
                variant={adjust ? 'default' : 'outline'}
                aria-pressed={adjust}
                data-testid="carve-adjust"
                disabled={carveTitleId == null}
                onClick={() => setAdjust((on) => !on)}
              >
                Adjust
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={history.undo.length === 0}
                onClick={() => void undo()}
              >
                Undo
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={history.redo.length === 0}
                onClick={() => void redo()}
              >
                Redo
              </Button>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                disabled={carveTitleId == null}
                onClick={() => setClearOpen(true)}
              >
                Clear
              </Button>
            </span>
          </>
        )}
        <div className="ml-auto flex items-center gap-1">
          <Button type="button" size="sm" variant="ghost" onClick={() => zoomBy(1 / 1.25)}>
            −
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={() => zoomBy(1.25)}>
            +
          </Button>
          <Button type="button" size="sm" variant="ghost" onClick={fitToMap}>
            Fit
          </Button>
        </div>
      </div>

      {plantOpen && mode === 'carve' && pickersOpen && (
        <form
          className="flex flex-wrap items-center gap-2 px-6 pb-3"
          data-testid="plant-form"
          onSubmit={(event) => {
            event.preventDefault();
            void plant();
          }}
        >
          <select
            className="h-8 rounded-md border bg-background px-2 text-sm"
            value={plantTier}
            onChange={(event) => setPlantTier(event.target.value as (typeof PLANT_TIERS)[number])}
            aria-label="tier"
          >
            {PLANT_TIERS.map((tier) => (
              <option key={tier} value={tier}>
                {tier}
              </option>
            ))}
          </select>
          <Input
            value={plantName}
            onChange={(event) => setPlantName(event.target.value)}
            placeholder="Name"
            className="h-8 w-56"
            aria-label="domain name"
          />
          <span className="font-body text-xs italic text-muted-foreground">
            {carveTarget ? `under ${carveTarget.name || carveTarget.tier}` : 'at the top'}
          </span>
          <Button type="submit" size="sm" disabled={!plantName.trim() || plantRung.isPending}>
            Plant
          </Button>
        </form>
      )}

      <div className="flex min-h-0 flex-1">
        <div
          ref={viewportRef}
          className={cn(
            'relative min-h-[480px] flex-1 overflow-hidden border-t bg-[#6d8db3]',
            cursorClass(panning, mode)
          )}
          data-testid="region-map-viewport"
          data-zoom={view.zoom.toFixed(2)}
          data-map-view={mapView}
          data-struck={struck.size}
          data-visible={visible.length}
          data-bordered={borders.size}
          data-ghost-pips={ghostPips.size}
          data-map-tiers={[...tiers].join(',')}
          data-seat-markers={markers.length}
          data-capital-markers={markers.filter((marker) => marker.rank > 0).length}
          data-seat-drag={seatDrag?.baronyId ?? ''}
          data-drop-targets={seatDrag?.targets.size ?? 0}
          onPointerDown={handlePointerDown}
        >
          <canvas
            ref={canvasRef}
            width={canvasW}
            height={canvasH}
            className="absolute left-0 top-0"
            style={{
              transform: `translate(${view.panX}px, ${view.panY}px) scale(${view.zoom})`,
              transformOrigin: '0 0',
              imageRendering: 'pixelated',
            }}
            data-testid="region-map-canvas"
          />
          <canvas
            ref={namesRef}
            className="pointer-events-none absolute left-0 top-0"
            data-testid="region-map-names"
          />
        </div>
        <RegionMapPanel
          open={panelOpen}
          onToggle={togglePanel}
          view={mapView}
          onView={setMapView}
          tiers={tiers}
          onToggleTier={toggleTier}
          anchorCaption={anchorCaption}
          selection={{ selected, selectedLandless, selectedLadderRow, stationWord, focusTitleId }}
          charterOn={charterOn}
          onToggleCharter={() => setCharterOn((on) => !on)}
          charterFootprints={charterFootprints}
          footprintCount={data.footprints.length}
          terrains={data.terrains}
          events={events.map((e) => ({ id: e.id, kind: e.kind, area: e.area }))}
          above={mode === 'select' ? selectedAbove : null}
          onUp={(footprint) => {
            setSelectedAreaId(footprint.area_id);
            setSelectedTitleId(footprint.title_id);
          }}
          onCarveThis={
            mode === 'carve'
              ? (footprint) => {
                  if (footprint.realm_id != null) setRealmId(footprint.realm_id);
                  setCarveTitleId(footprint.title_id);
                }
              : undefined
          }
        />
      </div>
      <AlertDialog open={clearOpen} onOpenChange={setClearOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              Clear {carveTarget?.name || carveTarget?.tier || 'this domain'} from the map
            </AlertDialogTitle>
            <AlertDialogDescription>
              Every pip it holds itself, on every region. Its child domains keep their ground. Undo
              puts it back.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void clearTarget()}>Clear</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
      <AlertDialog open={resetRiversOpen} onOpenChange={setResetRiversOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Reset rivers</AlertDialogTitle>
            <AlertDialogDescription>
              Every river on this map is replaced, the ones drawn by hand included, with the map
              file's longest rivers and the river beside each inland kingdom capital. This cannot be
              undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => void resetRivers()}>Reset rivers</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
