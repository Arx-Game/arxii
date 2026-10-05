/**
 * The Gallery tab (#4151).
 *
 * One pool of pictures per character. Looks (pictures with a saved 4:5 crop) are a grid
 * on the left; every other picture is shown one at a time in a tall frame on the right,
 * with arrows and thumbnails under it. Clicking any picture opens it full size. Words
 * and tools appear on hover, tools only for whoever may change the gallery: its
 * player, or staff (whose uploads here become the character's own art).
 *
 * Reordering is drag and drop within either side. Dragging a picture onto the looks
 * makes it a look (the cropper opens); dragging a look onto the tall frame makes it a
 * plain picture again.
 */
import { type DragEvent, useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  type GalleryPicture,
  useChangePicture,
  useDeletePicture,
  useGalleryQuery,
  useMediaUsageQuery,
  useMoodOptionsQuery,
  useReorderGallery,
  useSetPictureHidden,
  useUploadPictures,
  useWearPicture,
} from '@/roster/gallery';
import { LookCropper, type CropSave } from './LookCropper';
import { PictureDeleteConfirm } from './PictureDeleteConfirm';
import { type DeleteChoice, formatBytes } from './labels';
import { PictureDetailsDialog } from './PictureDetailsDialog';
import { PictureLightbox } from './PictureLightbox';
import { PictureTile, type TileTool } from './PictureTile';
import { DropZone } from './DropZone';
import './gallery.css';
import { cn } from '@/lib/utils';

interface GalleryPanelProps {
  entryId: number;
  sheetId: number;
  characterName: string;
  /** The character's current player, or staff: may change the gallery. */
  canManage: boolean;
  /** Only the current player hides character art (it is their time on the character). */
  isOwner: boolean;
  /** Friends (and the owner and staff) see NSFW pictures plain. */
  viewerIsFriend: boolean;
  ink: string;
}

type Side = 'looks' | 'pictures';

export function GalleryPanel({
  entryId,
  sheetId,
  characterName,
  canManage,
  isOwner,
  viewerIsFriend,
  ink,
}: GalleryPanelProps) {
  const { data: pictures = [], isLoading } = useGalleryQuery(entryId);
  const { data: moods = [] } = useMoodOptionsQuery(canManage);
  const { data: usage } = useMediaUsageQuery(isOwner);
  const upload = useUploadPictures(entryId, sheetId);
  const change = useChangePicture(entryId, sheetId);
  const remove = useDeletePicture(entryId, sheetId);
  const reorder = useReorderGallery(entryId, sheetId);
  const hide = useSetPictureHidden(entryId, sheetId);
  const wearPicture = useWearPicture(entryId, sheetId);

  const looks = useMemo(() => pictures.filter((p) => p.is_look), [pictures]);
  const others = useMemo(() => pictures.filter((p) => !p.is_look), [pictures]);

  const [viewIndex, setViewIndex] = useState(0);
  const [revealed, setRevealed] = useState<Set<number>>(new Set());
  const [lightbox, setLightbox] = useState<{ side: Side; index: number } | null>(null);
  const [cropping, setCropping] = useState<GalleryPicture | null>(null);
  const [editing, setEditing] = useState<GalleryPicture | null>(null);
  const [deleting, setDeleting] = useState<GalleryPicture | null>(null);
  const [dragId, setDragId] = useState<number | null>(null);
  const [marker, setMarker] = useState<{ id: number; where: 'before' | 'after' } | null>(null);
  const [targetSide, setTargetSide] = useState<Side | null>(null);

  const shownIndex = Math.min(viewIndex, Math.max(others.length - 1, 0));
  const current = others[shownIndex];

  const isVeiled = (picture: GalleryPicture) =>
    picture.is_nsfw && !viewerIsFriend && !revealed.has(picture.id);
  const reveal = (picture: GalleryPicture) => setRevealed((prev) => new Set(prev).add(picture.id));
  const open = (side: Side, index: number) => {
    const list = side === 'looks' ? looks : others;
    const picture = list[index];
    if (picture && isVeiled(picture)) reveal(picture);
    else setLightbox({ side, index });
  };

  // ---------------------------------------------------------- changes

  const saveCrop = ({ crop, mood, wear }: CropSave) => {
    if (!cropping) return;
    change.mutate(
      { id: cropping.id, change: { crop, mood, wear } },
      { onSuccess: () => setCropping(null) }
    );
  };

  const unLook = (picture: GalleryPicture) => {
    const crop = picture.crop;
    change.mutate(
      { id: picture.id, change: { crop: null } },
      {
        onSuccess: () =>
          toast(`${picture.title || 'Picture'} is no longer a profile picture.`, {
            action: crop
              ? {
                  label: 'Undo',
                  onClick: () => change.mutate({ id: picture.id, change: { crop } }),
                }
              : undefined,
          }),
      }
    );
  };

  const wear = (picture: GalleryPicture) => wearPicture.mutate(picture.id);

  const confirmDelete = (picture: GalleryPicture, choice: DeleteChoice) => {
    if (choice === 'hide') {
      hide.mutate({ id: picture.id, hidden: true }, { onSuccess: () => setDeleting(null) });
      return;
    }
    remove.mutate(picture.id, { onSuccess: () => setDeleting(null) });
  };

  // ---------------------------------------------------------- drag to reorder

  const sideOf = (id: number): Side => (looks.some((p) => p.id === id) ? 'looks' : 'pictures');

  const dragFor = (picture: GalleryPicture) =>
    canManage
      ? {
          dragging: dragId === picture.id,
          marker: marker?.id === picture.id ? marker.where : null,
          onDragStart: (event: DragEvent) => {
            event.dataTransfer.effectAllowed = 'move';
            event.dataTransfer.setData('text/plain', String(picture.id));
            setDragId(picture.id);
          },
          onDragEnd: () => {
            setDragId(null);
            setMarker(null);
            setTargetSide(null);
          },
          onDragOver: (event: DragEvent) => {
            if (dragId === null || sideOf(dragId) !== sideOf(picture.id)) return;
            event.preventDefault();
            event.stopPropagation();
            const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
            const where = event.clientX > rect.left + rect.width / 2 ? 'after' : 'before';
            setMarker({ id: picture.id, where });
          },
          onDrop: (event: DragEvent) => {
            if (dragId === null || dragId === picture.id) return;
            if (sideOf(dragId) !== sideOf(picture.id)) return;
            event.preventDefault();
            event.stopPropagation();
            const ids = pictures.map((p) => p.id).filter((id) => id !== dragId);
            const at = ids.indexOf(picture.id) + (marker?.where === 'after' ? 1 : 0);
            ids.splice(at, 0, dragId);
            reorder.mutate(ids);
            setDragId(null);
            setMarker(null);
          },
        }
      : undefined;

  /** A picture dropped on the other side: onto the looks makes a look, off makes it plain. */
  const sideDrop = (side: Side) =>
    canManage
      ? {
          onDragOver: (event: DragEvent) => {
            if (dragId === null || sideOf(dragId) === side) return;
            const dragged = pictures.find((p) => p.id === dragId);
            if (side === 'looks' && (dragged?.is_nsfw || dragged?.is_hidden)) return;
            event.preventDefault();
            setTargetSide(side);
          },
          onDragLeave: (event: DragEvent) => {
            if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node)) {
              setTargetSide(null);
            }
          },
          onDrop: (event: DragEvent) => {
            const dragged = pictures.find((p) => p.id === dragId);
            setTargetSide(null);
            setDragId(null);
            if (!dragged || sideOf(dragged.id) === side) return;
            event.preventDefault();
            if (side === 'looks') setCropping(dragged);
            else unLook(dragged);
          },
        }
      : {};

  // ---------------------------------------------------------- tools

  const lookTools = (picture: GalleryPicture): TileTool[] => {
    if (!canManage) return [];
    const tools: TileTool[] = [];
    if (picture.is_hidden) {
      if (isOwner)
        tools.push({
          label: 'Show',
          glyph: '◐',
          onClick: () => hide.mutate({ id: picture.id, hidden: false }),
        });
    } else {
      tools.push({ label: 'Adjust crop', glyph: '▣', onClick: () => setCropping(picture) });
    }
    tools.push({ label: 'Details', glyph: '…', onClick: () => setEditing(picture) });
    tools.push({
      label: 'Remove from profile pictures',
      glyph: '×',
      danger: true,
      onClick: () => unLook(picture),
    });
    return tools;
  };

  const pictureTools = (picture: GalleryPicture): TileTool[] => {
    if (!canManage) return [];
    const tools: TileTool[] = [];
    if (picture.is_hidden) {
      if (isOwner)
        tools.push({
          label: 'Show',
          glyph: '◐',
          onClick: () => hide.mutate({ id: picture.id, hidden: false }),
        });
    } else if (!picture.is_nsfw) {
      tools.push({
        label: 'Make profile picture',
        glyph: '▣',
        onClick: () => setCropping(picture),
      });
    }
    tools.push({ label: 'Details', glyph: '…', onClick: () => setEditing(picture) });
    const canHide = isOwner && picture.is_character_art && !picture.is_hidden;
    if (picture.can_delete || canHide) {
      tools.push({
        label: picture.can_delete ? 'Delete' : 'Hide',
        glyph: '×',
        danger: true,
        onClick: () => setDeleting(picture),
      });
    }
    return tools;
  };

  const nsfwFlag = (picture: GalleryPicture) =>
    canManage && picture.is_nsfw ? <span className="gallery-tag">NSFW</span> : undefined;

  if (isLoading) return null;
  const lightboxList = lightbox?.side === 'looks' ? looks : others;

  return (
    <div className="gallery">
      <div className="gallery-head">
        <span className="refsheet-eyebrow">Gallery</span>
        <span className="gallery-count">
          {pictures.length === 1 ? '1 picture' : `${pictures.length} pictures`}
          {usage && ` · ${formatBytes(usage.used_bytes)} of ${formatBytes(usage.quota_bytes)}`}
        </span>
      </div>

      {canManage && <DropZone busy={upload.isPending} onFiles={(files) => upload.mutate(files)} />}

      <div className="gallery-layout">
        <div
          className={cn('gallery-looks', targetSide === 'looks' && 'is-target')}
          {...sideDrop('looks')}
        >
          {looks.length === 0 && <p className="gallery-empty">No profile pictures yet.</p>}
          {looks.map((picture, index) => (
            <PictureTile
              key={picture.id}
              picture={picture}
              variant="look"
              veiled={false}
              tools={lookTools(picture)}
              onOpen={() => open('looks', index)}
              drag={dragFor(picture)}
            />
          ))}
        </div>

        <div
          className={cn('gallery-viewer', targetSide === 'pictures' && 'is-target')}
          {...sideDrop('pictures')}
        >
          {current ? (
            <PictureTile
              key={current.id}
              picture={current}
              variant="tall"
              veiled={isVeiled(current)}
              tools={pictureTools(current)}
              onOpen={() => open('pictures', shownIndex)}
              flag={nsfwFlag(current)}
            />
          ) : (
            <p className="gallery-empty">No other pictures.</p>
          )}
          {others.length > 1 && (
            <div className="gallery-nav">
              <button
                type="button"
                className="gallery-arrow"
                aria-label="Previous picture"
                onClick={() => setViewIndex((shownIndex - 1 + others.length) % others.length)}
              >
                ←
              </button>
              <div className="gallery-strip">
                {others.map((picture, index) => (
                  <button
                    key={picture.id}
                    type="button"
                    className={cn(
                      'gallery-thumb',
                      index === shownIndex && 'is-on',
                      isVeiled(picture) && 'is-veiled'
                    )}
                    aria-label={`Show picture ${index + 1}`}
                    aria-current={index === shownIndex ? 'true' : undefined}
                    onClick={() => setViewIndex(index)}
                    draggable={canManage}
                    onDragStart={dragFor(picture)?.onDragStart}
                    onDragEnd={dragFor(picture)?.onDragEnd}
                    onDragOver={dragFor(picture)?.onDragOver}
                    onDrop={dragFor(picture)?.onDrop}
                  >
                    <img src={picture.url} alt="" loading="lazy" draggable={false} />
                  </button>
                ))}
              </div>
              <button
                type="button"
                className="gallery-arrow"
                aria-label="Next picture"
                onClick={() => setViewIndex((shownIndex + 1) % others.length)}
              >
                →
              </button>
            </div>
          )}
        </div>
      </div>

      <PictureLightbox
        pictures={lightboxList}
        index={lightbox?.index ?? null}
        isVeiled={isVeiled}
        onReveal={reveal}
        onIndex={(index) => setLightbox((prev) => (prev ? { ...prev, index } : prev))}
        onClose={() => setLightbox(null)}
      />
      <LookCropper
        picture={cropping}
        moods={moods}
        ink={ink}
        isSaving={change.isPending}
        onSave={saveCrop}
        onClose={() => setCropping(null)}
      />
      <PictureDetailsDialog
        picture={editing}
        moods={moods}
        isSaving={change.isPending}
        onSave={(details) =>
          editing &&
          change.mutate({ id: editing.id, change: details }, { onSuccess: () => setEditing(null) })
        }
        onMakeLook={(picture) => {
          setEditing(null);
          setCropping(picture);
        }}
        onWear={(picture) => {
          setEditing(null);
          wear(picture);
        }}
        onClose={() => setEditing(null)}
      />
      <PictureDeleteConfirm
        picture={deleting}
        characterName={characterName}
        isWorking={remove.isPending || hide.isPending}
        onConfirm={confirmDelete}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
