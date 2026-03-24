import { XTERM_TO_HEX } from '@/lib/xterm256';

import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';

const CURATED_PALETTE = [
  { label: 'Reds', indices: [1, 9, 124, 160, 196, 203, 210] },
  { label: 'Oranges', indices: [208, 214, 215, 172, 130] },
  { label: 'Yellows', indices: [3, 11, 220, 226, 228] },
  { label: 'Greens', indices: [2, 10, 28, 34, 40, 82, 114] },
  { label: 'Blues', indices: [4, 12, 20, 27, 33, 39, 75] },
  { label: 'Purples', indices: [5, 13, 53, 92, 128, 134, 170] },
  { label: 'Cyans', indices: [6, 14, 37, 44, 51, 87] },
  { label: 'Neutrals', indices: [7, 15, 8, 0, 240, 245, 250, 255] },
];

interface ColorPickerProps {
  onSelectColor: (xtermIndex: number) => void;
}

export function ColorPicker({ onSelectColor }: ColorPickerProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          title="Text Color"
          className="flex h-6 w-6 items-center justify-center rounded text-xs hover:bg-accent hover:text-accent-foreground"
        >
          <span className="text-sm">A</span>
          <span
            className="absolute mt-3 h-1 w-3 rounded-sm"
            style={{ background: 'linear-gradient(to right, #f00, #0f0, #00f)' }}
          />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-3" align="start" side="top">
        <div className="space-y-2">
          {CURATED_PALETTE.map((family) => (
            <div key={family.label}>
              <div className="mb-1 text-xs text-muted-foreground">{family.label}</div>
              <div className="flex flex-wrap gap-1">
                {family.indices.map((index) => (
                  <button
                    key={index}
                    type="button"
                    title={`Color ${index}`}
                    aria-label={`Select color ${index}`}
                    className="h-5 w-5 rounded border border-border transition-transform hover:scale-125 hover:border-foreground"
                    style={{ backgroundColor: XTERM_TO_HEX[index] }}
                    onClick={() => onSelectColor(index)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
