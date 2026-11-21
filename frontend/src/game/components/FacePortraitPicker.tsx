/**
 * FacePortraitPicker - choose a face's portrait from the player's own pictures, or upload
 * a new one (#4889). It draws the Gallery's head line with its storage total, its drop zone
 * (one file here) and a grid of the player's pictures. A pick is stored as its own copy, so
 * it adds the picture's size to the storage total, and the tile says so.
 */
import { useEffect, useState } from 'react';
import { toast } from 'sonner';

import { DropZone } from '@/character_sheets/components/sheet/gallery/DropZone';
import { formatBytes } from '@/character_sheets/components/sheet/gallery/labels';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import { useMediaUsageQuery } from '@/roster/gallery';
import { cn } from '@/lib/utils';

import '@/character_sheets/components/sheet/gallery/gallery.css';
import { usePortraitChoicesQuery, type PortraitChoice } from '../faceQueries';

interface FacePortraitPickerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with the chosen picture; the caller stores the copy and closes the picker. */
  onPick: (mediaId: number) => void;
  /** Called with a new file; the caller stores it and closes the picker. */
  onUpload: (file: File) => void;
  busy: boolean;
}

export function FacePortraitPicker({
  open,
  onOpenChange,
  onPick,
  onUpload,
  busy,
}: FacePortraitPickerProps) {
  const { data: pictures = [], isError } = usePortraitChoicesQuery(open);
  const { data: usage } = useMediaUsageQuery(open);
  const [chosen, setChosen] = useState<PortraitChoice | null>(null);

  useEffect(() => {
    if (isError) toast.error('Failed to load your pictures.');
  }, [isError]);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) setChosen(null);
        onOpenChange(next);
      }}
    >
      <DialogContent {...NO_DESCRIPTION} className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Choose a portrait</DialogTitle>
        </DialogHeader>
        <div className="gallery">
          <div className="gallery-head">
            <span className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Your pictures
            </span>
            <span className="gallery-count">
              {pictures.length === 1 ? '1 picture' : `${pictures.length} pictures`}
              {usage && ` · ${formatBytes(usage.used_bytes)} of ${formatBytes(usage.quota_bytes)}`}
            </span>
          </div>
          <DropZone
            single
            inputId="face-portrait-file"
            busy={busy}
            onFiles={(files) => onUpload(files[0])}
          />
          <div className="grid max-h-64 grid-cols-3 gap-2 overflow-y-auto">
            {pictures.map((picture) => (
              <button
                key={picture.id}
                type="button"
                aria-pressed={chosen?.id === picture.id}
                onClick={() => setChosen(picture)}
                className={cn(
                  'flex flex-col gap-1 border p-1 text-left text-xs hover:bg-accent',
                  chosen?.id === picture.id && 'ring-2 ring-primary'
                )}
              >
                <img src={picture.url} alt={picture.title} className="aspect-square object-cover" />
                <span className="truncate">{picture.title || 'Untitled'}</span>
                {picture.file_size_bytes !== null && (
                  <span className="text-muted-foreground">
                    {formatBytes(picture.file_size_bytes)}
                  </span>
                )}
              </button>
            ))}
          </div>
          {chosen && chosen.file_size_bytes !== null && (
            <p className="text-sm text-muted-foreground">
              Adds {formatBytes(chosen.file_size_bytes)}
            </p>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={() => chosen && onPick(chosen.id)} disabled={!chosen || busy}>
            Use this picture
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
