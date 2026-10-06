import { describe, expect, it } from 'vitest';
import {
  clampPosition,
  cropHeight,
  initialCrop,
  maxCropWidth,
  MIN_CROP_WIDTH,
  moveCrop,
  resizeFromHandle,
  scaleAround,
} from '../cropMath';

const TALL = { width: 600, height: 1000 };
const WIDE = { width: 1000, height: 600 };

describe('cropMath', () => {
  it('starts a new look as the biggest 4:5 frame, centred across and at the top', () => {
    expect(initialCrop(WIDE)).toEqual({ x: 260, y: 0, width: 480 });
    expect(initialCrop(TALL)).toEqual({ x: 0, y: 0, width: 600 });
  });

  it('keeps the 4:5 shape', () => {
    expect(cropHeight(400)).toBe(500);
    expect(maxCropWidth(WIDE)).toBe(480);
  });

  it('moves the frame but never off the image', () => {
    const start = { x: 100, y: 100, width: 200 };
    expect(moveCrop(start, 50, 20, TALL)).toEqual({ x: 150, y: 120, width: 200 });
    expect(moveCrop(start, -500, 5000, TALL)).toEqual({ x: 0, y: 750, width: 200 });
  });

  it('resizes from a corner, keeping the opposite corner still', () => {
    const start = { x: 100, y: 100, width: 200 }; // bottom-right corner at (300, 350)
    const out = resizeFromHandle('nw', start, { x: 0, y: 0 }, TALL);
    expect(out.x + out.width).toBeCloseTo(300);
    expect(out.y + cropHeight(out.width)).toBeCloseTo(350);
    expect(out.width).toBeGreaterThan(200);
  });

  it('resizes from the right edge, keeping the left edge and the vertical centre', () => {
    const start = { x: 100, y: 300, width: 200 }; // centre y = 425
    const out = resizeFromHandle('e', start, { x: 400, y: 0 }, TALL);
    expect(out.x).toBe(100);
    expect(out.width).toBe(300);
    expect(out.y + cropHeight(out.width) / 2).toBeCloseTo(425);
  });

  it('resizes from the bottom edge, keeping the top edge and the horizontal centre', () => {
    const start = { x: 200, y: 100, width: 200 }; // centre x = 300
    const out = resizeFromHandle('s', start, { x: 0, y: 600 }, TALL);
    expect(out.y).toBe(100);
    expect(out.width).toBe(400);
    expect(out.x + out.width / 2).toBe(300);
  });

  it('never grows past the image', () => {
    const out = resizeFromHandle('se', { x: 0, y: 0, width: 100 }, { x: 5000, y: 5000 }, TALL);
    expect(out.width).toBeLessThanOrEqual(600);
    expect(out.y + cropHeight(out.width)).toBeLessThanOrEqual(1000);
  });

  it('never shrinks below the minimum', () => {
    const out = resizeFromHandle('e', { x: 100, y: 100, width: 200 }, { x: 101, y: 0 }, TALL);
    expect(out.width).toBe(MIN_CROP_WIDTH);
  });

  it('scales about the centre and stays inside', () => {
    const out = scaleAround({ x: 0, y: 0, width: 600 }, 2, TALL);
    expect(out.width).toBe(600);
    expect(clampPosition(out, TALL)).toEqual(out);
  });
});
