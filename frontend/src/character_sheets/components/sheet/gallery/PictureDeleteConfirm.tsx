/**
 * The Gallery's one Delete (#4151), confirmed in the words of what it will actually do.
 *
 * - The player's own file, on no other character: Delete, and the space it frees.
 * - The player's own file, also on another of their characters: it only comes off
 *   this one, and the other characters are named.
 * - Character art the player may not delete: Hide, for their own time on the character.
 */
import { AlertDialog, AlertDialogContent, AlertDialogTitle } from '@/components/ui/alert-dialog';
import type { GalleryPicture } from '@/roster/gallery';
import { type DeleteChoice, deleteChoiceFor, formatBytes } from './labels';
import { cn } from '@/lib/utils';

interface PictureDeleteConfirmProps {
  picture: GalleryPicture | null;
  characterName: string;
  isWorking: boolean;
  onConfirm: (picture: GalleryPicture, choice: DeleteChoice) => void;
  onClose: () => void;
}

export function PictureDeleteConfirm({
  picture,
  characterName,
  isWorking,
  onConfirm,
  onClose,
}: PictureDeleteConfirmProps) {
  if (!picture) return <AlertDialog open={false} />;
  const choice = deleteChoiceFor(picture);
  const name = picture.title || 'this picture';
  const copy = {
    delete: {
      title: `Delete ${name}?`,
      body: picture.file_size_bytes
        ? `This frees ${formatBytes(picture.file_size_bytes)}.`
        : 'It is deleted from your files.',
      action: 'Delete',
    },
    remove: {
      title: `Remove ${name} from ${characterName}?`,
      body: `It stays on ${picture.also_on.join(', ')}.`,
      action: `Remove from ${characterName}`,
    },
    hide: {
      title: `Hide ${name}?`,
      body: `It stays on ${characterName} for whoever plays next.`,
      action: 'Hide',
    },
  }[choice];

  return (
    <AlertDialog open onOpenChange={(open) => !open && onClose()}>
      <AlertDialogContent className="max-w-md">
        <div className="refsheet gallery-dialog">
          <AlertDialogTitle className="gallery-dialog-title">{copy.title}</AlertDialogTitle>
          <p>{copy.body}</p>
          <div className="gallery-actions">
            <div />
            <div>
              <button type="button" className="gallery-btn" onClick={onClose}>
                Cancel
              </button>
              <button
                type="button"
                className={cn('gallery-btn', choice === 'hide' ? 'is-primary' : 'is-danger')}
                disabled={isWorking}
                onClick={() => onConfirm(picture, choice)}
              >
                {copy.action}
              </button>
            </div>
          </div>
        </div>
      </AlertDialogContent>
    </AlertDialog>
  );
}
