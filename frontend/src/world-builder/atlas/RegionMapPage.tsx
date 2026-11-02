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
 * neighbours are shading.
 */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { toast } from 'sonner';

import { useAlmanachMutation, useLadder, useRealms } from '@/almanach/queries';
import { Plate, PlateHead } from '@/components/folio';
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
  PIP_PX,
  TERRAIN_COLORS,
  drawRegionMap,
  footprintAt,
  pipAt,
  pipKey,
  regionBounds,
} from './regionMapCanvas';
import {
  BRUSH_WIDTHS,
  brushPips,
  floodHeld,
  floodLand,
  loopInterior,
  type BrushWidth,
  type Pip,
} from './regionMapFill';

type MapMode = 'select' | 'carve' | 'paint';
const MODE_LABELS: Record<MapMode, string> = { select: 'Select', carve: 'Carve', paint: 'Paint' };
type CarveTool = 'brush' | 'fill' | 'loop';
const TOOL_LABELS: Record<CarveTool, string> = { brush: 'Brush', fill: 'Fill', loop: 'Loop' };

const WHEEL_ZOOM_RATE = 0.0015;

function cursorClass(panning: boolean, mode: MapMode): string {
  if (panning) return 'cursor-grabbing';
  return mode === 'select' ? 'cursor-grab' : 'cursor-crosshair';
}
const DRAG_THRESHOLD_PX = 4;
/** The server's per-call cap (`MAX_FOOTPRINT_PIPS_PER_CALL`); a bigger fill goes in batches. */
const MAX_PIPS_PER_CALL = 20000;
/** View storage is keyed by node id; region maps live past every area id. */
const VIEW_NODE_OFFSET = 1_000_000;
const PLANT_TIERS = ['kingdom', 'duchy', 'county', 'march', 'barony'] as const;

export interface RegionMapPageProps {
  regionId: number;
  /** An area to open the panel on when the map opens (from an area page's On the map). */
  focusAreaId?: number | null;
}

export function RegionMapPage({ regionId, focusAreaId = null }: RegionMapPageProps) {
  const account = useAccount();
  const accountId = account?.id ?? 'anon';
  const nodeId = VIEW_NODE_OFFSET + regionId;
  const { data, isLoading, isError } = useRegionMapPipsQuery(regionId);
  const characterId = useWorldBuilderActor();
  const { mutateAsync: runAction } = useWorldBuilderAction(characterId ?? 0, null);
  const upload = useRegionMapUpload(regionId);

  const [mode, setMode] = useState<MapMode>('select');
  const [selectedAreaId, setSelectedAreaId] = useState<number | null>(focusAreaId);
  const [realmId, setRealmId] = useState<number | null>(null);
  const [carveTitleId, setCarveTitleId] = useState<number | null>(null);
  const [paintTerrain, setPaintTerrain] = useState<string>('plain');
  const [tool, setTool] = useState<CarveTool>('brush');
  const [brushWidth, setBrushWidth] = useState<BrushWidth>(1);
  const [history, setHistory] = useState<CarveHistory>(EMPTY_HISTORY);
  const [clearOpen, setClearOpen] = useState(false);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [pendingRemove, setPendingRemove] = useState(false);
  const [plantOpen, setPlantOpen] = useState(false);
  const [plantName, setPlantName] = useState('');
  const [plantTier, setPlantTier] = useState<(typeof PLANT_TIERS)[number]>('county');

  const { data: realmsPage } = useRealms();
  const realms = realmsPage?.results ?? [];
  const { data: ladder, refetch: refetchLadder } = useLadder(realmId, 'staff');
  const plantRung = useAlmanachMutation('almanach_plant_rung');

  useEffect(() => {
    setSelectedAreaId(focusAreaId);
  }, [focusAreaId, regionId]);

  // ---- the view: zoom + pan, remembered per region ----
  const [view, setView] = useState<LatticeView>(() => readLatticeView(accountId, nodeId));
  useEffect(() => {
    setView(readLatticeView(accountId, nodeId));
  }, [accountId, nodeId]);
  useEffect(() => {
    writeLatticeView(accountId, nodeId, view);
  }, [accountId, nodeId, view]);
  const viewportRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const viewport = viewportRef.current;
    if (!viewport) return undefined;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = viewport.getBoundingClientRect();
      const factor = Math.exp(-event.deltaY * WHEEL_ZOOM_RATE);
      setView((prev) =>
        zoomAround(prev, factor, event.clientX - rect.left, event.clientY - rect.top)
      );
    };
    viewport.addEventListener('wheel', onWheel, { passive: false });
    return () => viewport.removeEventListener('wheel', onWheel);
  }, []);

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
    const stored = readLatticeView(accountId, nodeId);
    if (stored.zoom !== DEFAULT_VIEW.zoom || stored.panX !== 0 || stored.panY !== 0) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    setView(fitView(canvasW, canvasH, viewport.clientWidth, viewport.clientHeight));
  }, [accountId, canvasH, canvasW, nodeId, regionId]);

  const fitToMap = () => {
    const viewport = viewportRef.current;
    if (!viewport || !canvasW) return;
    setView(fitView(canvasW, canvasH, viewport.clientWidth, viewport.clientHeight));
  };
  const zoomBy = (factor: number) => {
    const viewport = viewportRef.current;
    const cx = viewport ? viewport.clientWidth / 2 : 0;
    const cy = viewport ? viewport.clientHeight / 2 : 0;
    setView((prev) => zoomAround(prev, factor, cx, cy));
  };

  const selected: RegionMapFootprint | null = useMemo(
    () => data?.footprints.find((f) => f.area_id === selectedAreaId) ?? null,
    [data, selectedAreaId]
  );
  const ladderRows = ladder?.rows ?? [];
  const carveTarget = useMemo(
    () => ladder?.rows.find((row) => row.title_id === carveTitleId) ?? null,
    [ladder, carveTitleId]
  );
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
    drawRegionMap(ctx, data, { pending, pendingRemove, selectedAreaId, outlineAreaIds });
  }, [data, outlineAreaIds, pending, pendingRemove, selectedAreaId]);

  // ---- pointer handling: pan, select, or drag pips ----
  const [panning, setPanning] = useState(false);
  const handlePointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (event.button !== 0 || !data) return;
    const viewport = viewportRef.current;
    if (!viewport) return;
    const rect = viewport.getBoundingClientRect();
    const startX = event.clientX;
    const startY = event.clientY;
    const origin = view;
    const panMode = mode === 'select' || event.altKey;
    const remove = event.shiftKey;
    let moved = false;
    const dragged = new Set<string>();
    const path: Pip[] = [];
    const carveTool: CarveTool = mode === 'paint' ? 'brush' : tool;
    const addPip = (clientX: number, clientY: number) => {
      const pip = pipAt(data.region, view, rect, clientX, clientY);
      if (!pip) return;
      const pips = carveTool === 'brush' ? brushPips(pip, brushWidth).filter(insideRegion) : [pip];
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
          toast.error('Pick a domain to carve.');
          return;
        }
        // Every batch that landed is undoable, even when a later batch is refused or
        // the request fails, so the entry is pushed whatever way the loop ends.
        const changed: PipChange[] = [];
        busyRef.current = true;
        try {
          for (const part of chunk(pips, MAX_PIPS_PER_CALL)) {
            const result = await runAction({
              key: 'atlas_carve_footprint',
              kwargs: { title_id: carveTitleId, [remove ? 'remove' : 'add']: part },
            });
            if (result.success === false) break;
            changed.push(...parseChanged(result.data));
          }
        } finally {
          busyRef.current = false;
          setHistory((h) => pushEntry(h, { titleId: carveTitleId, changed }));
        }
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

  const plant = async () => {
    if (realmId == null || !plantName.trim()) return;
    try {
      const result = await plantRung.mutateAsync({
        realm_id: realmId,
        tier: plantTier,
        name: plantName.trim(),
        parent_title_id: carveTitleId ?? undefined,
      });
      const titleId = result?.data?.title_id;
      await refetchLadder();
      if (typeof titleId === 'number') setCarveTitleId(titleId);
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
            onClick={() => setMode(m)}
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
            </select>
            {brushWidthSelect}
          </>
        )}
        {mode === 'carve' && (
          <>
            <select
              className="h-8 rounded-md border bg-background px-2 text-sm"
              value={realmId ?? ''}
              onChange={(event) => {
                setRealmId(event.target.value ? Number(event.target.value) : null);
                setCarveTitleId(null);
              }}
              aria-label="realm"
              data-testid="carve-realm"
            >
              <option value="">Realm…</option>
              {realms.map((realm) => (
                <option key={realm.id} value={realm.id}>
                  {realm.name}
                </option>
              ))}
            </select>
            <select
              className="h-8 max-w-xs rounded-md border bg-background px-2 text-sm"
              value={carveTitleId ?? ''}
              onChange={(event) =>
                setCarveTitleId(event.target.value ? Number(event.target.value) : null)
              }
              aria-label="domain"
              data-testid="carve-domain"
              disabled={realmId == null}
            >
              <option value="">Domain…</option>
              {(ladder?.rows ?? []).map((row) => (
                <option key={row.title_id} value={row.title_id}>
                  {row.name || `unnamed ${row.tier}`} · {row.tier}
                  {row.house_name ? ` · ${row.house_name}` : ''}
                </option>
              ))}
            </select>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={realmId == null}
              onClick={() => setPlantOpen((open) => !open)}
            >
              Create domain
            </Button>
            <span className="mx-1 h-6 border-l" aria-hidden="true" />
            <span className="flex items-center gap-2" data-testid="carve-tools">
              {(['brush', 'fill', 'loop'] as const).map((t) => (
                <Button
                  key={t}
                  type="button"
                  size="sm"
                  variant={tool === t ? 'default' : 'outline'}
                  aria-pressed={tool === t}
                  onClick={() => setTool(t)}
                >
                  {TOOL_LABELS[t]}
                </Button>
              ))}
              {tool === 'brush' && brushWidthSelect}
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

      {plantOpen && mode === 'carve' && (
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
        </div>
        <aside
          className="w-72 shrink-0 overflow-y-auto border-l border-t"
          data-testid="region-map-panel"
        >
          <Plate className="h-full rounded-none p-4">
            {selected ? (
              <div>
                <PlateHead as="div">{selected.level_display}</PlateHead>
                <h3 className="theme-heading mt-1 text-lg font-semibold [font-variant:small-caps]">
                  {selected.name || 'Unnamed'}
                </h3>
                <p className="mt-1 font-body text-sm italic text-muted-foreground">
                  {selected.holder_name || 'Unclaimed'} · {selected.pips.length} pips
                </p>
                {selected.title_id != null && (
                  <Link
                    to={`/staff/almanach/titles/${selected.title_id}`}
                    className="mt-3 inline-block text-sm underline hover:text-primary"
                  >
                    Open in the Almanach
                  </Link>
                )}
                {mode === 'carve' && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="mt-3"
                    disabled={selected.title_id == null}
                    onClick={() => {
                      if (selected.realm_id != null) setRealmId(selected.realm_id);
                      setCarveTitleId(selected.title_id);
                    }}
                  >
                    Carve this one
                  </Button>
                )}
              </div>
            ) : (
              <div>
                <PlateHead as="div">Open ground</PlateHead>
                <p className="mt-1 font-body text-sm italic text-muted-foreground">
                  {data.footprints.length} domains on this map.
                </p>
              </div>
            )}
            <div className="mt-6 grid grid-cols-2 gap-x-3 gap-y-1" data-testid="region-map-legend">
              {data.terrains.map((terrain) => (
                <span key={terrain} className="flex items-center gap-2 text-xs">
                  <span
                    className="inline-block h-3 w-3 rounded-sm border border-black/20"
                    style={{ background: TERRAIN_COLORS[terrain] ?? '#c0c0c0' }}
                  />
                  {terrain}
                </span>
              ))}
            </div>
          </Plate>
        </aside>
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
    </section>
  );
}
