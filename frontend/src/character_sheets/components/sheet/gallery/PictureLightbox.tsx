/**
 * A picture at full size (#4151), with its title and caption, and arrows through the
 * set it was opened from. A veiled picture stays veiled here until clicked.
 */
import { useEffect } from 'react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import type { GalleryPicture } from '@/roster/gallery';
import { cn } from '@/lib/utils';

interface PictureLightboxProps {
  pictures: GalleryPicture[];
  index: number | null;
  isVeiled: (picture: GalleryPicture) => boolean;
  onReveal: (picture: GalleryPicture) => void;
  onIndex: (index: number) => void;
  onClose: () => void;
}

export function PictureLightbox({
  pictures,
  index,
  isVeiled,
  onReveal,
  onIndex,
  onClose,
}: PictureLightboxProps) {
  const picture = index !== null ? pictures[index] : undefined;
  const many = pictures.length > 1;
  const step = (delta: number) => {
    if (index === null) return;
    onIndex((index + delta + pictures.length) % pictures.length);
  };

  useEffect(() => {
    if (index === null || !many) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'ArrowLeft') onIndex((index - 1 + pictures.length) % pictures.length);
      if (event.key === 'ArrowRight') onIndex((index + 1) % pictures.length);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [index, many, onIndex, pictures.length]);

  const veiled = picture ? isVeiled(picture) : false;
  return (
    <Dialog open={picture !== undefined} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-6xl border-0 bg-transparent p-0 shadow-none">
        <DialogTitle className="sr-only">{picture?.title || 'Picture'}</DialogTitle>
        {picture && (
          <div className="gallery-lightbox">
            <div className="gallery-lightbox-row">
              {many && (
                <button
                  type="button"
                  className="gallery-arrow"
                  aria-label="Previous picture"
                  onClick={() => step(-1)}
                >
                  ←
                </button>
              )}
              <button
                type="button"
                className={cn('gallery-lightbox-img', veiled && 'is-veiled')}
                onClick={() => veiled && onReveal(picture)}
                aria-label={veiled ? 'Reveal NSFW picture' : picture.title || 'Picture'}
                style={{ border: 0, padding: 0, background: 'none' }}
              >
                <img src={picture.url} alt={picture.title || ''} />
                {veiled && (
                  <span className="gallery-veil">
                    <span className="gallery-tag">NSFW</span>
                    <span>Click to reveal</span>
                  </span>
                )}
              </button>
              {many && (
                <button
                  type="button"
                  className="gallery-arrow"
                  aria-label="Next picture"
                  onClick={() => step(1)}
                >
                  →
                </button>
              )}
            </div>
            {!veiled && (picture.title || picture.caption) && (
              <div className="gallery-lightbox-cap">
                {picture.title && <b>{picture.title}</b>}
                {picture.caption && <i>{picture.caption}</i>}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
