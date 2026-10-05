/**
 * What a picture says about itself (#4151): its title, caption, the mood it shows, and
 * whether it is NSFW. The game never suggests any of the words.
 */
import { useEffect, useState } from 'react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import type { GalleryPicture, MoodOption, PictureChange } from '@/roster/gallery';

interface PictureDetailsDialogProps {
  picture: GalleryPicture | null;
  moods: MoodOption[];
  isSaving: boolean;
  onSave: (change: PictureChange) => void;
  /** Open the cropper on this picture (it is not a look yet). */
  onMakeLook: (picture: GalleryPicture) => void;
  /** Wear this look. */
  onWear: (picture: GalleryPicture) => void;
  onClose: () => void;
}

export function PictureDetailsDialog({
  picture,
  moods,
  isSaving,
  onSave,
  onMakeLook,
  onWear,
  onClose,
}: PictureDetailsDialogProps) {
  const [title, setTitle] = useState('');
  const [caption, setCaption] = useState('');
  const [mood, setMood] = useState<number | null>(null);
  const [nsfw, setNsfw] = useState(false);

  useEffect(() => {
    setTitle(picture?.title ?? '');
    setCaption(picture?.caption ?? '');
    setMood(picture?.mood_id ?? null);
    setNsfw(picture?.is_nsfw ?? false);
  }, [picture]);

  if (!picture) {
    return <Dialog open={false} />;
  }
  const change: PictureChange = { title, caption, mood, is_nsfw: nsfw };

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-lg">
        <form
          className="refsheet gallery-dialog"
          onSubmit={(event) => {
            event.preventDefault();
            onSave(change);
          }}
        >
          <DialogTitle className="gallery-dialog-title">Picture details</DialogTitle>
          <label className="gallery-field">
            <span>Title</span>
            <input
              id="picture-title"
              type="text"
              maxLength={200}
              autoComplete="off"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
            />
          </label>
          <label className="gallery-field">
            <span>Caption</span>
            <textarea
              id="picture-caption"
              maxLength={2000}
              value={caption}
              onChange={(event) => setCaption(event.target.value)}
            />
          </label>
          <label className="gallery-field">
            <span>Mood it shows</span>
            <select
              id="picture-mood"
              value={mood ?? ''}
              onChange={(event) => setMood(event.target.value ? Number(event.target.value) : null)}
            >
              <option value="">None</option>
              {moods.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </select>
          </label>
          <label className="gallery-check">
            <input
              id="picture-nsfw"
              type="checkbox"
              checked={nsfw}
              onChange={(event) => setNsfw(event.target.checked)}
            />
            <span>
              NSFW
              <small>
                Blurred for anyone who isn&apos;t your friend, until they click. Can&apos;t be a
                profile picture.
              </small>
            </span>
          </label>
          {nsfw && picture.is_look && (
            <p className="gallery-warn">
              Saving this as NSFW takes it out of your profile pictures.
            </p>
          )}
          <div className="gallery-actions">
            <div>
              {!nsfw && !picture.is_look && !picture.is_hidden && (
                <button
                  type="button"
                  className="gallery-btn is-quiet"
                  onClick={() => onMakeLook(picture)}
                >
                  Make profile picture
                </button>
              )}
              {!nsfw && picture.is_look && !picture.is_worn && !picture.is_hidden && (
                <button
                  type="button"
                  className="gallery-btn is-quiet"
                  onClick={() => onWear(picture)}
                >
                  Show on the sheet
                </button>
              )}
            </div>
            <div>
              <button type="button" className="gallery-btn" onClick={onClose}>
                Cancel
              </button>
              <button type="submit" className="gallery-btn is-primary" disabled={isSaving}>
                Save
              </button>
            </div>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
