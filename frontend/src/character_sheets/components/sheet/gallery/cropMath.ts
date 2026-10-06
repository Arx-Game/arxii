/**
 * The look cropper's geometry (#4151), kept pure so it can be tested without a DOM.
 *
 * Every crop is a 4:5 frame, the plate's shape, in the image's own pixels: `x`, `y` and
 * `width`, with the height always `width * 5 / 4`. The server re-checks and clamps what
 * it is sent; this is what makes the frame behave under the pointer.
 *
 * - Dragging inside the frame moves it, kept inside the image.
 * - A corner resizes from the opposite corner, which stays put.
 * - An edge resizes from the opposite edge, and the frame stays centred on the other
 *   axis, so dragging the right edge reads as "wider" even though the height has to
 *   grow with it to keep the shape.
 */

export const LOOK_RATIO = 4 / 5; // width / height
export const MIN_CROP_WIDTH = 60;

export interface CropRect {
  x: number;
  y: number;
  width: number;
}

export interface ImageSize {
  width: number;
  height: number;
}

export type Handle = 'nw' | 'n' | 'ne' | 'e' | 'se' | 's' | 'sw' | 'w';

export const HANDLES: Handle[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'];

export function cropHeight(width: number): number {
  return width / LOOK_RATIO;
}

/** The widest 4:5 frame that fits the image. */
export function maxCropWidth(image: ImageSize): number {
  return Math.min(image.width, image.height * LOOK_RATIO);
}

/** A new look starts as the biggest frame that fits, centred across, at the top. */
export function initialCrop(image: ImageSize): CropRect {
  const width = maxCropWidth(image);
  return { x: (image.width - width) / 2, y: 0, width };
}

/** Keep a frame of its current size inside the image. */
export function clampPosition(crop: CropRect, image: ImageSize): CropRect {
  const x = Math.min(Math.max(crop.x, 0), image.width - crop.width);
  const y = Math.min(Math.max(crop.y, 0), image.height - cropHeight(crop.width));
  return { x, y, width: crop.width };
}

/** Move the frame by a delta in image pixels. */
export function moveCrop(start: CropRect, dx: number, dy: number, image: ImageSize): CropRect {
  return clampPosition({ x: start.x + dx, y: start.y + dy, width: start.width }, image);
}

function bounded(width: number, room: number): number {
  return Math.max(Math.min(width, room), Math.min(MIN_CROP_WIDTH, room));
}

/**
 * Resize from a handle. `start` is the frame when the drag began; `pointer` is where
 * the pointer is now, in image pixels.
 */
export function resizeFromHandle(
  handle: Handle,
  start: CropRect,
  pointer: { x: number; y: number },
  image: ImageSize
): CropRect {
  const east = handle.includes('e');
  const west = handle.includes('w');
  const south = handle.includes('s');
  const north = handle.includes('n');
  const startHeight = cropHeight(start.width);
  const ax = west ? start.x + start.width : start.x;
  const ay = north ? start.y + startHeight : start.y;

  if ((east || west) && (north || south)) {
    return resizeCorner(east, south, ax, ay, pointer, image);
  }
  if (east || west) {
    return resizeHorizontal(east, ax, start, pointer, image);
  }
  return resizeVertical(south, ay, start, pointer, image);
}

function resizeCorner(
  east: boolean,
  south: boolean,
  ax: number,
  ay: number,
  pointer: { x: number; y: number },
  image: ImageSize
): CropRect {
  const room = Math.min(
    east ? image.width - ax : ax,
    (south ? image.height - ay : ay) * LOOK_RATIO
  );
  const wanted = Math.max(Math.abs(pointer.x - ax), Math.abs(pointer.y - ay) * LOOK_RATIO);
  const width = bounded(wanted, room);
  return {
    x: east ? ax : ax - width,
    y: south ? ay : ay - cropHeight(width),
    width,
  };
}

function resizeHorizontal(
  east: boolean,
  ax: number,
  start: CropRect,
  pointer: { x: number; y: number },
  image: ImageSize
): CropRect {
  const cy = start.y + cropHeight(start.width) / 2;
  const room = Math.min(
    east ? image.width - ax : ax,
    2 * Math.min(cy, image.height - cy) * LOOK_RATIO
  );
  const width = bounded(Math.abs(pointer.x - ax), room);
  return clampPosition({ x: east ? ax : ax - width, y: cy - cropHeight(width) / 2, width }, image);
}

function resizeVertical(
  south: boolean,
  ay: number,
  start: CropRect,
  pointer: { x: number; y: number },
  image: ImageSize
): CropRect {
  const cx = start.x + start.width / 2;
  const room = Math.min(
    (south ? image.height - ay : ay) * LOOK_RATIO,
    2 * Math.min(cx, image.width - cx)
  );
  const width = bounded(Math.abs(pointer.y - ay) * LOOK_RATIO, room);
  return clampPosition({ x: cx - width / 2, y: south ? ay : ay - cropHeight(width), width }, image);
}

/** Grow or shrink about the frame's centre (the + and - keys). */
export function scaleAround(crop: CropRect, factor: number, image: ImageSize): CropRect {
  const cx = crop.x + crop.width / 2;
  const cy = crop.y + cropHeight(crop.width) / 2;
  const width = Math.max(MIN_CROP_WIDTH, Math.min(maxCropWidth(image), crop.width * factor));
  return clampPosition({ x: cx - width / 2, y: cy - cropHeight(width) / 2, width }, image);
}

/** Whole pixels, for the server. */
export function roundCrop(crop: CropRect): CropRect {
  return { x: Math.round(crop.x), y: Math.round(crop.y), width: Math.round(crop.width) };
}

/**
 * CSS that places an image inside a frame so the frame shows exactly the crop.
 * `squareTop` takes the square at the top of the 4:5 crop, for the looks strip and the
 * round chips, as every portrait chip does.
 */
export function cropImageStyle(
  crop: CropRect,
  image: ImageSize,
  squareTop = false
): { width: string; left: string; top: string } {
  const frameHeight = squareTop ? crop.width : cropHeight(crop.width);
  return {
    width: `${(image.width / crop.width) * 100}%`,
    left: `${(-crop.x / crop.width) * 100}%`,
    top: `${(-crop.y / frameHeight) * 100}%`,
  };
}
