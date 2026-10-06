/** Small pure helpers the Gallery's components share (#4151). */
import type { CharacterSheetLook } from '@/character_sheets/api';
import type { GalleryPicture } from '@/roster/gallery';

/** "Furious", then "Furious 2" for the second look tagged the same way; untagged: none. */
export function lookLabels(looks: CharacterSheetLook[]): Map<number, string> {
  const seen = new Map<string, number>();
  const labels = new Map<number, string>();
  for (const look of looks) {
    if (!look.look) {
      labels.set(look.tenure_media_id, '');
      continue;
    }
    const count = (seen.get(look.look) ?? 0) + 1;
    seen.set(look.look, count);
    labels.set(look.tenure_media_id, count > 1 ? `${look.look} ${count}` : look.look);
  }
  return labels;
}

export type DeleteChoice = 'delete' | 'remove' | 'hide';

export function deleteChoiceFor(picture: GalleryPicture): DeleteChoice {
  if (!picture.can_delete) return 'hide';
  return picture.also_on.length > 0 ? 'remove' : 'delete';
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
