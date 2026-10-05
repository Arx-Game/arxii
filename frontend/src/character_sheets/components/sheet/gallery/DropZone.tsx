/** Drop pictures onto a character's Gallery, or click to choose them (#4151). */
import { type DragEvent, useState } from 'react';
import { cn } from '@/lib/utils';

const ACCEPT = 'image/png,image/jpeg,image/gif,image/webp';

interface DropZoneProps {
  busy: boolean;
  onFiles: (files: File[]) => void;
}

function imagesOnly(list: FileList | null): File[] {
  return Array.from(list ?? []).filter((file) => file.type.startsWith('image/'));
}

export function DropZone({ busy, onFiles }: DropZoneProps) {
  const [over, setOver] = useState(false);
  const isFileDrag = (event: DragEvent) => event.dataTransfer.types.includes('Files');

  return (
    <label
      className={cn('gallery-drop', over && 'is-over', busy && 'is-busy')}
      htmlFor="gallery-files"
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
        const files = imagesOnly(event.dataTransfer.files);
        if (files.length) onFiles(files);
      }}
    >
      <input
        id="gallery-files"
        type="file"
        accept={ACCEPT}
        multiple
        onChange={(event) => {
          const files = imagesOnly(event.target.files);
          if (files.length) onFiles(files);
          event.target.value = '';
        }}
      />
      <strong>{busy ? 'Adding…' : 'Drop pictures here, or click to choose'}</strong>
      <small>PNG, JPG, GIF or WebP. Several at once is fine.</small>
    </label>
  );
}
