/**
 * Format an equipment slot label as ``Region (Layer)``.
 *
 * Uses the same display strings the backend ``BodyRegion`` /
 * ``EquipmentLayer`` TextChoices declare (see ``world/items/constants.py``)
 * so the wire-format enum values remain in sync with the UI labels.
 *
 * Falls back to the raw enum value if a future enum addition lands
 * without a corresponding label here yet — keeps the UI rendering rather
 * than crashing on unknown keys.
 *
 * Lives in its own module so the wardrobe components stay export-only
 * (Vite/React fast-refresh requires component files to export only
 * components — exporting helpers from the same file warns).
 */

import type { BodyRegion, EquipmentLayer } from './types';

const REGION_LABELS: Record<BodyRegion, string> = {
  head: 'Head',
  face: 'Face',
  neck: 'Neck',
  shoulders: 'Shoulders',
  torso: 'Torso',
  back: 'Back',
  waist: 'Waist',
  left_arm: 'Left Arm',
  right_arm: 'Right Arm',
  left_hand: 'Left Hand',
  right_hand: 'Right Hand',
  left_leg: 'Left Leg',
  right_leg: 'Right Leg',
  feet: 'Feet',
  left_finger: 'Left Finger',
  right_finger: 'Right Finger',
  left_ear: 'Left Ear',
  right_ear: 'Right Ear',
};

const LAYER_LABELS: Record<EquipmentLayer, string> = {
  skin: 'Skin',
  under: 'Under',
  base: 'Base',
  over: 'Over',
  outer: 'Outer',
  accessory: 'Accessory',
};

export function humanizeRegionLayer(region: BodyRegion, layer: EquipmentLayer): string {
  const regionLabel = REGION_LABELS[region] ?? region;
  const layerLabel = LAYER_LABELS[layer] ?? layer;
  return `${regionLabel} (${layerLabel})`;
}
