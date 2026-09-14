import { useRef, useState } from 'react';
import * as PopoverPrimitive from '@radix-ui/react-popover';
import { PopoverContent } from '@/components/ui/popover';
import { cn } from '@/lib/utils';
import { FEED_KINDS } from '../feedKinds';
import {
  KIND_LABELS,
  MAX_CHIP_LABEL,
  MAX_CUSTOM_CHIPS,
  addCustomChip,
  chipFor,
  deleteChip,
  renameChip,
  setChipWake,
  setKindOwner,
  toggleAll,
  toggleChip,
  type FeedChip,
  type FeedChipState,
} from '../feedChips';

interface FeedChipStripProps {
  state: FeedChipState;
  onChange: (next: FeedChipState) => void;
  /** Unseen waking items per chip id (`chipUnread`); a chip with a count shows a "new" pill. */
  newCounts?: Record<string, number>;
}

const chipClass =
  'inline-flex min-h-8 items-center gap-1.5 rounded-full border px-2.5 text-xs transition-colors ' +
  'aria-pressed:border-primary/60 aria-pressed:bg-primary/10 aria-pressed:text-foreground ' +
  'text-muted-foreground hover:border-primary/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';

/**
 * The filter chips above the feed (#3856): one plain label per chip, `+` while
 * a custom chip can still be added, All at the right end. A press toggles the
 * chip (or, with All off, brings back only that chip); a right-click opens the
 * chip's editor. Nothing on the strip explains itself, by ruling.
 */
export function FeedChipStrip({ state, onChange, newCounts = {} }: FeedChipStripProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [selectName, setSelectName] = useState(false);
  const customCount = state.chips.filter((chip) => chip.custom).length;

  const openEditor = (id: string, withNameSelected = false) => {
    setSelectName(withNameSelected);
    setEditingId(id);
  };

  const handleAdd = () => {
    const next = addCustomChip(state);
    if (!next.newChipId) return;
    onChange({ chips: next.chips, all: next.all });
    openEditor(next.newChipId, true);
  };

  return (
    <div
      role="toolbar"
      aria-label="Feed filters"
      className="flex min-h-10 flex-wrap items-center gap-1.5 border-b px-3 py-1.5"
    >
      {state.chips.map((chip) => (
        <PopoverPrimitive.Root
          key={chip.id}
          open={editingId === chip.id}
          onOpenChange={(open) => {
            // A left click on the chip is a toggle, never an open; only the
            // context menu opens, and the popover's own dismissals close.
            if (!open) setEditingId(null);
          }}
        >
          <PopoverPrimitive.Anchor asChild>
            <button
              type="button"
              className={chipClass}
              aria-pressed={state.all && chip.on}
              onClick={() => onChange(toggleChip(state, chip.id))}
              onContextMenu={(event) => {
                event.preventDefault();
                openEditor(chip.id);
              }}
            >
              {chip.label}
              {(newCounts[chip.id] ?? 0) > 0 && (
                <span className="rounded-full bg-primary px-1.5 text-[10px] uppercase tracking-wide text-primary-foreground">
                  new
                </span>
              )}
            </button>
          </PopoverPrimitive.Anchor>
          {editingId === chip.id && (
            <FeedChipEditor
              chip={chip}
              state={state}
              selectName={selectName}
              onChange={onChange}
              onClose={() => setEditingId(null)}
            />
          )}
        </PopoverPrimitive.Root>
      ))}
      {customCount < MAX_CUSTOM_CHIPS && (
        <button
          type="button"
          className={cn(chipClass, 'px-2 font-semibold')}
          onClick={handleAdd}
          aria-label="+"
        >
          +
        </button>
      )}
      <button
        type="button"
        className={cn(chipClass, 'ml-auto font-semibold')}
        aria-pressed={state.all}
        onClick={() => onChange(toggleAll(state))}
      >
        All
      </button>
    </div>
  );
}

interface FeedChipEditorProps {
  chip: FeedChip;
  state: FeedChipState;
  selectName: boolean;
  onChange: (next: FeedChipState) => void;
  onClose: () => void;
}

/**
 * The chip's editor, in a popover under the chip: its name, the kinds it
 * carries (with where a kind lives now, when another chip has it), whether
 * it wakes the player, and Delete. Every change writes through at once.
 */
function FeedChipEditor({ chip, state, selectName, onChange, onClose }: FeedChipEditorProps) {
  const [name, setName] = useState(chip.label);
  const nameRef = useRef<HTMLInputElement>(null);

  const commitName = () => {
    if (name.trim() && name.trim() !== chip.label) onChange(renameChip(state, chip.id, name));
  };

  return (
    // The popover focuses its first control, the name, on open; a chip just
    // added gets its placeholder name selected so typing replaces it.
    <PopoverContent align="start" className="w-64 space-y-1.5 p-3 text-xs">
      <input
        ref={nameRef}
        aria-label="Chip name"
        className="mb-1 w-full border-0 border-b bg-transparent pb-0.5 font-medium text-foreground outline-none focus-visible:border-primary"
        value={name}
        maxLength={MAX_CHIP_LABEL}
        onChange={(event) => setName(event.target.value)}
        onFocus={() => {
          if (selectName) nameRef.current?.select();
        }}
        onBlur={commitName}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            event.preventDefault();
            commitName();
            onClose();
          }
        }}
      />
      {FEED_KINDS.map((kind) => {
        const owner = chipFor(kind, state.chips);
        const mine = owner?.id === chip.id;
        return (
          <label key={kind} className="flex items-center gap-2 py-0.5">
            <input
              type="checkbox"
              className="accent-primary"
              checked={mine}
              onChange={(event) =>
                onChange(setKindOwner(state, chip.id, kind, event.target.checked))
              }
            />
            <span>{KIND_LABELS[kind]}</span>
            {owner && !mine && <span className="text-muted-foreground">(in {owner.label})</span>}
          </label>
        );
      })}
      <label className="mt-1 flex items-center gap-2 border-t pt-2 font-semibold">
        <input
          type="checkbox"
          className="accent-primary"
          checked={chip.wake}
          onChange={(event) => onChange(setChipWake(state, chip.id, event.target.checked))}
        />
        Wake me when this arrives
      </label>
      <button
        type="button"
        className="mt-1 text-destructive underline-offset-2 hover:underline"
        onClick={() => {
          onChange(deleteChip(state, chip.id));
          onClose();
        }}
      >
        Delete chip
      </button>
    </PopoverContent>
  );
}
