/**
 * Drop pictures onto a character's Gallery, or click to choose them (#4151). In `single`
 * mode (the portrait picker, #4889) it takes one file and carries its own input id, so it
 * can sit on a page beside the Gallery's.
 */
import { type DragEvent, useState } from 'react';
import { cn } from '@/lib/utils';

const ACCEPT = 'image/png,image/jpeg,image/gif,image/webp';

interface DropZoneProps {
  busy: boolean;
  onFiles: (files: File[]) => void;
  /** Take one file at a time. */
  single?: boolean;
  /** The file input's id; the Gallery's own by default. */
  inputId?: string;
}

function imagesOnly(list: FileList | null): File[] {
  return Array.from(list ?? []).filter((file) => file.type.startsWith('image/'));
}

export function DropZone({
  busy,
  onFiles,
  single = false,
  inputId = 'gallery-files',
}: DropZoneProps) {
  const [over, setOver] = useState(false);
  const isFileDrag = (event: DragEvent) => event.dataTransfer.types.includes('Files');
  const taken = (files: File[]) => (single ? files.slice(0, 1) : files);
  const prompt = `Drop ${single ? 'a picture' : 'pictures'} here, or click to choose`;

  return (
    <label
      className={cn('gallery-drop', over && 'is-over', busy && 'is-busy')}
      htmlFor={inputId}
      onDragOver={(event) => {
        if (!isFileDrag(event)) return;
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        if (!isFileDrag(event)) return;
        event.preventDefault();
        setOver(false);
        const files = taken(imagesOnly(event.dataTransfer.files));
        if (files.length) onFiles(files);
      }}
    >
      <input
        id={inputId}
        type="file"
        accept={ACCEPT}
        multiple={!single}
        onChange={(event) => {
          const files = taken(imagesOnly(event.target.files));
          if (files.length) onFiles(files);
          event.target.value = '';
        }}
      />
      <strong>{busy ? 'Adding…' : prompt}</strong>
      <small>
        {single ? 'PNG, JPG, GIF or WebP.' : 'PNG, JPG, GIF or WebP. Several at once is fine.'}
      </small>
    </label>
  );
}
