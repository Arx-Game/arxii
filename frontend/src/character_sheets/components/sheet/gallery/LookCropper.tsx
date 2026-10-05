/**
 * The look cropper (#4151): frame a picture in the plate's 4:5 shape.
 *
 * Drag inside the frame to move it, a corner to resize from the opposite corner, an
 * edge to resize from the opposite edge (the frame stays centred the other way). Arrow
 * keys move it, Shift for further; + and - resize it; Enter saves; Esc cancels. The
 * previews show the same crop as the sheet, the looks strip and a round chip read it,
 * since every surface shows this one frame.
 *
 * The geometry lives in `cropMath`; this component only turns pointer and key events
 * into image pixels.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import type { GalleryPicture, MoodOption } from '@/roster/gallery';
import {
  type CropRect,
  type Handle,
  HANDLES,
  type ImageSize,
  cropHeight,
  initialCrop,
  moveCrop,
  resizeFromHandle,
  roundCrop,
  scaleAround,
} from './cropMath';
import { CropPreview } from './CropPreview';
import './gallery.css';
import { cn } from '@/lib/utils';

export interface CropSave {
  crop: CropRect;
  mood: number | null;
  wear: boolean;
}

interface LookCropperProps {
  picture: GalleryPicture | null;
  moods: MoodOption[];
  /** The plate ink, so the cropper is printed like the plate it frames for. */
  ink: string;
  isSaving: boolean;
  onSave: (save: CropSave) => void;
  onClose: () => void;
}

interface Drag {
  handle: Handle | null;
  startX: number;
  startY: number;
  start: CropRect;
}

const NUDGE = 8;
const NUDGE_FAR = 40;

export function LookCropper({ picture, moods, ink, isSaving, onSave, onClose }: LookCropperProps) {
  const imgRef = useRef<HTMLImageElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [image, setImage] = useState<ImageSize | null>(null);
  const [crop, setCrop] = useState<CropRect | null>(null);
  const [shownWidth, setShownWidth] = useState(0);
  const [mood, setMood] = useState<number | null>(null);
  const [wear, setWear] = useState(true);
  const drag = useRef<Drag | null>(null);

  useEffect(() => {
    setImage(null);
    setCrop(null);
    setMood(picture?.mood_id ?? null);
    setWear(!picture?.is_look || Boolean(picture?.is_worn));
  }, [picture]);

  const onImageLoad = () => {
    const img = imgRef.current;
    if (!img || !picture) return;
    const size = { width: img.naturalWidth, height: img.naturalHeight };
    setImage(size);
    setShownWidth(img.clientWidth);
    // An existing look reopens where it was framed; a new one starts at the top.
    setCrop(
      picture.crop
        ? { x: picture.crop.x, y: picture.crop.y, width: picture.crop.width }
        : initialCrop(size)
    );
    boxRef.current?.focus();
  };

  useEffect(() => {
    const onResize = () => setShownWidth(imgRef.current?.clientWidth ?? 0);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const scale = image && shownWidth ? shownWidth / image.width : 0;

  const save = useCallback(() => {
    if (!crop || isSaving) return;
    onSave({ crop: roundCrop(crop), mood, wear });
  }, [crop, isSaving, mood, onSave, wear]);

  const onPointerDown = (event: React.PointerEvent) => {
    if (!crop || !scale) return;
    const target = event.target as HTMLElement;
    const handle = (target.closest('[data-handle]') as HTMLElement | null)?.dataset.handle as
      | Handle
      | undefined;
    if (!handle && !target.closest('[data-crop-box]')) return;
    event.preventDefault();
    drag.current = {
      handle: handle ?? null,
      startX: event.clientX,
      startY: event.clientY,
      start: crop,
    };
    stageRef.current?.setPointerCapture?.(event.pointerId);
    boxRef.current?.focus();
  };

  const onPointerMove = (event: React.PointerEvent) => {
    const current = drag.current;
    if (!current || !image || !scale) return;
    if (!current.handle) {
      const dx = (event.clientX - current.startX) / scale;
      const dy = (event.clientY - current.startY) / scale;
      setCrop(moveCrop(current.start, dx, dy, image));
      return;
    }
    const rect = stageRef.current?.getBoundingClientRect();
    if (!rect) return;
    const pointer = {
      x: (event.clientX - rect.left) / scale,
      y: (event.clientY - rect.top) / scale,
    };
    setCrop(resizeFromHandle(current.handle, current.start, pointer, image));
  };

  const endDrag = () => {
    drag.current = null;
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (!crop || !image || !scale) return;
    const tag = (event.target as HTMLElement).tagName;
    if (tag === 'SELECT' || tag === 'BUTTON' || tag === 'INPUT') return;
    if (event.key === 'Enter') {
      event.preventDefault();
      save();
      return;
    }
    if (event.key === '+' || event.key === '=') {
      event.preventDefault();
      setCrop(scaleAround(crop, 1.05, image));
      return;
    }
    if (event.key === '-' || event.key === '_') {
      event.preventDefault();
      setCrop(scaleAround(crop, 1 / 1.05, image));
      return;
    }
    const step = (event.shiftKey ? NUDGE_FAR : NUDGE) / scale;
    const moves: Record<string, [number, number]> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const move = moves[event.key];
    if (move) {
      event.preventDefault();
      setCrop(moveCrop(crop, move[0], move[1], image));
    }
  };

  const isNew = !picture?.is_look;

  return (
    <Dialog open={picture !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-5xl border-0 bg-transparent p-0 text-[#f1e6d6] shadow-none">
        <div className="refsheet gallery-cropper" data-ink={ink} onKeyDown={onKeyDown}>
          <DialogTitle className="sr-only">Frame this look</DialogTitle>
          <div className="gallery-cropper-stage-wrap">
            {picture && (
              <div
                ref={stageRef}
                className="gallery-cropper-stage"
                onPointerDown={onPointerDown}
                onPointerMove={onPointerMove}
                onPointerUp={endDrag}
                onPointerCancel={endDrag}
              >
                <img ref={imgRef} src={picture.url} alt="" draggable={false} onLoad={onImageLoad} />
                {crop && scale > 0 && (
                  <div
                    ref={boxRef}
                    data-crop-box
                    className="gallery-cropper-box"
                    tabIndex={0}
                    aria-label="Crop frame. Arrow keys move it, plus and minus resize it."
                    style={{
                      left: crop.x * scale,
                      top: crop.y * scale,
                      width: crop.width * scale,
                      height: cropHeight(crop.width) * scale,
                    }}
                  >
                    {HANDLES.map((handle) => (
                      <span
                        key={handle}
                        data-handle={handle}
                        className={cn('gallery-cropper-handle', `is-${handle}`)}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
          <div className="gallery-cropper-side">
            <span className="refsheet-eyebrow">Profile picture</span>
            {picture && crop && image && (
              <div className="gallery-cropper-previews" aria-hidden="true">
                <figure>
                  <CropPreview src={picture.url} crop={crop} image={image} className="is-plate" />
                  <figcaption>Sheet</figcaption>
                </figure>
                <figure>
                  <CropPreview
                    src={picture.url}
                    crop={crop}
                    image={image}
                    squareTop
                    className="is-look"
                  />
                  <figcaption>Look</figcaption>
                </figure>
                <figure>
                  <CropPreview
                    src={picture.url}
                    crop={crop}
                    image={image}
                    squareTop
                    className="is-chip"
                  />
                  <figcaption>Chip</figcaption>
                </figure>
              </div>
            )}
            <label className="gallery-field">
              <span>Mood it shows</span>
              <select
                id="look-mood"
                value={mood ?? ''}
                onChange={(event) =>
                  setMood(event.target.value ? Number(event.target.value) : null)
                }
              >
                <option value="">None</option>
                {moods.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.name}
                  </option>
                ))}
              </select>
            </label>
            {!picture?.is_worn && (
              <label className="gallery-check">
                <input
                  id="look-wear"
                  type="checkbox"
                  checked={wear}
                  onChange={(event) => setWear(event.target.checked)}
                />
                <span>Show it on the sheet now</span>
              </label>
            )}
            <div className="gallery-cropper-actions">
              <button type="button" className="gallery-btn" onClick={onClose}>
                Cancel
              </button>
              <button
                type="button"
                className="gallery-btn is-primary"
                onClick={save}
                disabled={!crop || isSaving}
              >
                {isNew ? 'Save profile picture' : 'Save crop'}
              </button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
