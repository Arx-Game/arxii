/**
 * The region map's side panel (#4242): the view picker (#5030), what is selected, its
 * Historical Charter (#4983) and the terrain legend. It folds to a thin rail (#4993); the
 * selection and the view live on the page, so folding loses nothing.
 */
import { ArrowUp, PanelRightClose, PanelRightOpen, type LucideIcon } from 'lucide-react';

import type { LadderRow } from '@/almanach/types';
import { Plate, PlateHead } from '@/components/folio';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

import type { RegionMapFootprint, RegionMapLandlessTitle } from '../types';
import { MAP_VIEW_LABELS, MAP_VIEWS, type MapView } from './mapViews';
import { STRIKE_COLOR, TERRAIN_COLORS } from './regionMapCanvas';

interface FoldToggleProps {
  open: boolean;
  /** What the toggle folds, named in its "Hide ..." and "Show ..." label. */
  what: string;
  openIcon: LucideIcon;
  foldedIcon: LucideIcon;
  onToggle: () => void;
  testId: string;
  className?: string;
}

export function FoldToggle({
  open,
  what,
  openIcon: OpenIcon,
  foldedIcon: FoldedIcon,
  onToggle,
  testId,
  className,
}: FoldToggleProps) {
  const label = `${open ? 'Hide' : 'Show'} ${what}`;
  const Icon = open ? OpenIcon : FoldedIcon;
  return (
    <Button
      type="button"
      size="sm"
      variant="ghost"
      className={className}
      aria-expanded={open}
      aria-label={label}
      title={label}
      data-testid={testId}
      onClick={onToggle}
    >
      <Icon className="h-4 w-4" aria-hidden="true" />
    </Button>
  );
}

interface MapSelectionSummary {
  selected: RegionMapFootprint | null;
  selectedLandless: RegionMapLandlessTitle | null;
  selectedLadderRow: LadderRow | null;
  stationWord: string | null;
  focusTitleId: number | null;
}

interface RegionMapPanelProps {
  open: boolean;
  onToggle: () => void;
  /** What the map shows (#5030), and the domain the Domain views are anchored on. */
  view: MapView;
  onView: (view: MapView) => void;
  anchorCaption: string;
  selection: MapSelectionSummary;
  charterOn: boolean;
  onToggleCharter: () => void;
  charterFootprints: RegionMapFootprint[];
  footprintCount: number;
  terrains: string[];
  /** The open regional events on this map (#5080), named in the legend. */
  events?: { id: number; kind: string; area: string }[];
  /** Offered only while carving: make the selected footprint the domain being carved. */
  onCarveThis?: (footprint: RegionMapFootprint) => void;
  /** The domain the selected one lies in (#5116), when it is on this map: the
   * way up, one rung at a time. Null at the top, and while carving. */
  above?: RegionMapFootprint | null;
  onUp?: (footprint: RegionMapFootprint) => void;
}

function SelectionDetails({
  selection,
  charterOn,
  onToggleCharter,
  charterFootprints,
  onCarveThis,
  above,
  onUp,
}: Pick<
  RegionMapPanelProps,
  | 'selection'
  | 'charterOn'
  | 'onToggleCharter'
  | 'charterFootprints'
  | 'onCarveThis'
  | 'above'
  | 'onUp'
>) {
  const { selected, selectedLandless, selectedLadderRow, stationWord, focusTitleId } = selection;
  const landless = selectedLandless ?? selectedLadderRow;
  return (
    <div>
      <PlateHead as="div">{selected ? selected.level_display : (landless?.tier ?? '')}</PlateHead>
      <div className="mt-1 flex items-center gap-1">
        <h3 className="theme-heading text-lg font-semibold [font-variant:small-caps]">
          {(selected ? selected.name : landless?.name) || 'Unnamed'}
        </h3>
        {above && onUp && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            aria-label={`Up to ${above.name || `unnamed ${above.level_display.toLowerCase()}`}`}
            title={above.name || `unnamed ${above.level_display.toLowerCase()}`}
            data-testid="selection-up"
            onClick={() => onUp(above)}
          >
            <ArrowUp className="h-4 w-4" aria-hidden="true" />
          </Button>
        )}
      </div>
      {stationWord && (
        <p className="mt-1 text-xs uppercase tracking-wide text-muted-foreground">{stationWord}</p>
      )}
      <p className="mt-1 font-body text-sm italic text-muted-foreground">
        {selected
          ? `${selected.holder_name || 'Unclaimed'} · ${selected.pips.length} pips`
          : 'holds nothing'}
      </p>
      {focusTitleId != null && (
        <>
          <a
            href={`/staff/almanach/titles/${focusTitleId}`}
            target="_blank"
            rel="noopener"
            className="mt-3 inline-block text-sm underline hover:text-primary"
          >
            Open in the Almanach
          </a>
          <div className="mt-3">
            <Button
              type="button"
              size="sm"
              variant={charterOn ? 'default' : 'outline'}
              aria-pressed={charterOn}
              onClick={onToggleCharter}
            >
              Historical Charter
            </Button>
            {charterOn && (
              <ul className="mt-2 space-y-0.5 text-sm">
                {charterFootprints.map((f) => (
                  <li key={f.area_id}>{f.name || 'Unnamed'}</li>
                ))}
                {charterFootprints.length === 0 && (
                  <li className="text-muted-foreground">nothing chartered</li>
                )}
              </ul>
            )}
          </div>
        </>
      )}
      {onCarveThis && selected && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="mt-3"
          disabled={selected.title_id == null}
          onClick={() => onCarveThis(selected)}
        >
          Carve this one
        </Button>
      )}
    </div>
  );
}

export function RegionMapPanel({
  open,
  onToggle,
  view,
  onView,
  anchorCaption,
  selection,
  charterOn,
  onToggleCharter,
  charterFootprints,
  footprintCount,
  terrains,
  events = [],
  onCarveThis,
  above,
  onUp,
}: RegionMapPanelProps) {
  const hasSelection =
    selection.selected || selection.selectedLandless || selection.selectedLadderRow;
  return (
    <aside
      className={cn('relative shrink-0 overflow-y-auto border-l border-t', open ? 'w-72' : 'w-10')}
      data-testid="region-map-panel"
    >
      <FoldToggle
        open={open}
        what="the side panel"
        openIcon={PanelRightClose}
        foldedIcon={PanelRightOpen}
        onToggle={onToggle}
        testId="panel-toggle"
        className="absolute right-1 top-1 z-10 h-8 w-8 p-0"
      />
      {open && (
        <Plate className="h-full rounded-none p-4">
          <div
            role="group"
            aria-label="view"
            className="mb-1 mr-8 flex flex-wrap gap-1"
            data-testid="map-view-picker"
          >
            {MAP_VIEWS.map((option) => (
              <Button
                key={option}
                type="button"
                size="sm"
                variant={view === option ? 'default' : 'outline'}
                aria-pressed={view === option}
                onClick={() => onView(option)}
              >
                {MAP_VIEW_LABELS[option]}
              </Button>
            ))}
          </div>
          <p
            className="mb-4 font-body text-xs italic text-muted-foreground"
            data-testid="map-view-anchor"
          >
            {anchorCaption}
          </p>
          {hasSelection ? (
            <SelectionDetails
              selection={selection}
              charterOn={charterOn}
              onToggleCharter={onToggleCharter}
              charterFootprints={charterFootprints}
              onCarveThis={onCarveThis}
              above={above}
              onUp={onUp}
            />
          ) : (
            <div>
              <PlateHead as="div">Open ground</PlateHead>
              <p className="mt-1 font-body text-sm italic text-muted-foreground">
                {footprintCount} domains on this map.
              </p>
            </div>
          )}
          <div className="mt-6 grid grid-cols-2 gap-x-3 gap-y-1" data-testid="region-map-legend">
            {terrains.map((terrain) => (
              <span key={terrain} className="flex items-center gap-2 text-xs">
                <span
                  className="inline-block h-3 w-3 rounded-sm border border-black/20"
                  style={{ background: TERRAIN_COLORS[terrain] ?? '#c0c0c0' }}
                />
                {terrain}
              </span>
            ))}
            {events.map((event) => (
              <span key={event.id} className="flex items-center gap-2 text-xs">
                <span
                  className="inline-block h-3 w-3 rounded-sm border border-black/20"
                  style={{ background: STRIKE_COLOR }}
                />
                {event.kind} over {event.area}
              </span>
            ))}
          </div>
        </Plate>
      )}
    </aside>
  );
}
