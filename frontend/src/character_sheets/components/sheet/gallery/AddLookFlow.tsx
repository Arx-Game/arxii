/**
 * Add a look (#4151), from the plate's strip: pick one of the character's pictures, or
 * upload a new one, then frame it in the cropper and say what mood it shows.
 *
 * Only pictures that can be looks are offered: not NSFW, not hidden, not already looks.
 */
import { useRef, useState } from 'react';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import {
  type GalleryPicture,
  useChangePicture,
  useGalleryQuery,
  useMoodOptionsQuery,
  useUploadPictures,
} from '@/roster/gallery';
import { LookCropper, type CropSave } from './LookCropper';
import './gallery.css';

interface AddLookFlowProps {
  open: boolean;
  entryId: number;
  sheetId: number;
  ink: string;
  onClose: () => void;
}

export function AddLookFlow({ open, entryId, sheetId, ink, onClose }: AddLookFlowProps) {
  const { data: pictures = [] } = useGalleryQuery(entryId, open);
  const { data: moods = [] } = useMoodOptionsQuery(open);
  const upload = useUploadPictures(entryId, sheetId);
  const change = useChangePicture(entryId, sheetId);
  const [cropping, setCropping] = useState<GalleryPicture | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const candidates = pictures.filter((p) => !p.is_look && !p.is_nsfw && !p.is_hidden);

  const finish = () => {
    setCropping(null);
    onClose();
  };
  const save = ({ crop, mood, wear }: CropSave) => {
    if (!cropping) return;
    change.mutate({ id: cropping.id, change: { crop, mood, wear } }, { onSuccess: finish });
  };

  return (
    <>
      <Dialog open={open && cropping === null} onOpenChange={(next) => !next && onClose()}>
        <DialogContent className="max-w-lg">
          <div className="refsheet gallery-dialog">
            <DialogTitle className="gallery-dialog-title">Add a look</DialogTitle>
            <div className="gallery-pick">
              {candidates.map((picture) => (
                <button
                  key={picture.id}
                  type="button"
                  aria-label={picture.title || 'Picture'}
                  onClick={() => setCropping(picture)}
                >
                  <img src={picture.url} alt="" />
                </button>
              ))}
              <button
                type="button"
                className="is-upload"
                disabled={upload.isPending}
                onClick={() => fileRef.current?.click()}
              >
                {upload.isPending ? 'Adding…' : 'Upload a picture'}
              </button>
            </div>
            <input
              ref={fileRef}
              id="add-look-file"
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              hidden
              onChange={(event) => {
                const file = event.target.files?.[0];
                event.target.value = '';
                if (!file) return;
                upload.mutate([file], {
                  onSuccess: (added) => {
                    if (added[0]) setCropping(added[0]);
                  },
                });
              }}
            />
            <div className="gallery-actions">
              <div />
              <div>
                <button type="button" className="gallery-btn" onClick={onClose}>
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </DialogContent>
      </Dialog>
      <LookCropper
        picture={cropping}
        moods={moods}
        ink={ink}
        isSaving={change.isPending}
        onSave={save}
        onClose={finish}
      />
    </>
  );
}
