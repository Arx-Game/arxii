/**
 * One picture in the Gallery (#4151), with its words and tools shown on hover only.
 *
 * The title and caption appear over the foot of the picture when there are any, and
 * nothing appears when there are none. Tools appear only for whoever may change the
 * gallery. An NSFW picture is veiled for anyone who is not a friend until clicked.
 */
import type { DragEvent, ReactNode } from 'react';
import type { GalleryPicture } from '@/roster/gallery';
import { cn } from '@/lib/utils';

export interface TileTool {
  label: string;
  glyph: string;
  onClick: () => void;
  danger?: boolean;
}

interface PictureTileProps {
  picture: GalleryPicture;
  /** `look` shows the 4:5 crop; `tall` shows the whole picture filling a tall frame. */
  variant: 'look' | 'tall';
  veiled: boolean;
  tools: TileTool[];
  onOpen: () => void;
  /** Drag-to-reorder wiring, only for whoever may change the gallery. */
  drag?: {
    onDragStart: (event: DragEvent) => void;
    onDragEnd: () => void;
    onDragOver: (event: DragEvent) => void;
    onDrop: (event: DragEvent) => void;
    marker: 'before' | 'after' | null;
    dragging: boolean;
  };
  /** Shown top left for the owner: an NSFW flag. */
  flag?: ReactNode;
}

export function PictureTile({
  picture,
  variant,
  veiled,
  tools,
  onOpen,
  drag,
  flag,
}: PictureTileProps) {
  const src = variant === 'look' ? (picture.look_url ?? picture.url) : picture.url;
  const classes = [
    'gallery-pic',
    variant === 'look' ? 'is-look' : 'is-tall',
    picture.is_worn && variant === 'look' ? 'is-worn' : '',
    picture.is_hidden ? 'is-hidden' : '',
    veiled ? 'is-veiled' : '',
    drag?.dragging ? 'is-dragging' : '',
    drag?.marker === 'before' ? 'drop-before' : '',
    drag?.marker === 'after' ? 'drop-after' : '',
  ]
    .filter(Boolean)
    .join(' ');
  const hasWords = Boolean(picture.title || picture.caption);
  return (
    <div
      className={classes}
      data-picture={picture.id}
      draggable={Boolean(drag)}
      onDragStart={drag?.onDragStart}
      onDragEnd={drag?.onDragEnd}
      onDragOver={drag?.onDragOver}
      onDrop={drag?.onDrop}
    >
      <button
        type="button"
        className="gallery-pic-open"
        onClick={onOpen}
        aria-label={veiled ? 'Reveal NSFW picture' : `Open ${picture.title || 'picture'}`}
      >
        <img src={src} alt="" loading="lazy" draggable={false} />
      </button>
      {veiled && (
        <span className="gallery-veil">
          <span className="gallery-tag">NSFW</span>
          <span>Click to reveal</span>
        </span>
      )}
      {!veiled && hasWords && (
        <span className="gallery-cap">
          {picture.title && <b>{picture.title}</b>}
          {picture.caption && <i>{picture.caption}</i>}
        </span>
      )}
      {flag && !veiled && <span className="gallery-flag">{flag}</span>}
      {tools.length > 0 && (
        <span className="gallery-tools">
          {tools.map((tool) => (
            <button
              key={tool.label}
              type="button"
              className={cn('gallery-tool', tool.danger && 'is-danger')}
              aria-label={tool.label}
              title={tool.label}
              onClick={tool.onClick}
            >
              {tool.glyph}
            </button>
          ))}
        </span>
      )}
    </div>
  );
}
