/**
 * ArtDialog (#3535) — hang art on a room or area from the builder, or take
 * it down. One dialog serves both documents: the caller supplies the hang/
 * take-down dispatches (`staff_edit_room`/`edit_area` with `art_id`), this
 * only picks the `Media`.
 *
 * The library and upload reuse the roster media machinery wholesale
 * (`fetchPlayerMedia`/`uploadPlayerMedia` — the same Cloudinary-backed store
 * the character galleries use); an upload hangs immediately, since "upload
 * then separately click it" is a pointless second step for a picker.
 */
import { useRef } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';
import { fetchPlayerMedia, uploadPlayerMedia } from '@/roster/api';
import type { PlayerMedia } from '@/roster/types';

const ART_LIBRARY_KEY = ['world-builder', 'art-library'] as const;

export interface ArtDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** What the art hangs on — dialog copy only (e.g. "The Grand Foyer"). */
  subjectName: string;
  /** The subject's currently RESOLVED art, if any (a room may be showing inherited area art). */
  currentArtUrl: string | null;
  onHang: (mediaId: number) => void;
  onTakeDown: () => void;
}

export function ArtDialog({
  open,
  onOpenChange,
  subjectName,
  currentArtUrl,
  onHang,
  onTakeDown,
}: ArtDialogProps) {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { data: library } = useQuery<PlayerMedia[]>({
    queryKey: ART_LIBRARY_KEY,
    queryFn: fetchPlayerMedia,
    enabled: open,
  });

  const uploadMutation = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append('image_file', file);
      form.append('title', file.name);
      return uploadPlayerMedia(form);
    },
    onSuccess: (media) => {
      queryClient.invalidateQueries({ queryKey: ART_LIBRARY_KEY }).catch(() => {});
      onHang(media.id);
      onOpenChange(false);
    },
    onError: (err: Error) => toast.error(err.message),
  });

  const handleHang = (media: PlayerMedia) => {
    onHang(media.id);
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogTitle>Art for {subjectName}</DialogTitle>

        {currentArtUrl && (
          <div className="flex items-center gap-3">
            <img
              src={currentArtUrl}
              alt={`Current art for ${subjectName}`}
              className="max-h-24 border object-cover"
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                onTakeDown();
                onOpenChange(false);
              }}
              data-testid="art-take-down"
            >
              Take it down
            </Button>
          </div>
        )}

        <div
          className="grid max-h-64 grid-cols-4 gap-2 overflow-y-auto"
          data-testid="art-library-grid"
        >
          {(library ?? []).map((media) => (
            <button
              key={media.id}
              type="button"
              className="border hover:ring-2 hover:ring-primary"
              onClick={() => handleHang(media)}
              title={media.title || undefined}
              data-testid={`art-option-${media.id}`}
            >
              <img
                src={media.cloudinary_url}
                alt={media.title || 'untitled art'}
                className="h-24 w-full object-cover"
              />
            </button>
          ))}
          {library != null && library.length === 0 && (
            <p className="col-span-4 font-body text-sm italic text-muted-foreground">
              Nothing in the library yet — upload something.
            </p>
          )}
        </div>

        <div>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) uploadMutation.mutate(file);
              event.target.value = '';
            }}
            data-testid="art-upload-input"
          />
          <Button
            type="button"
            size="sm"
            disabled={uploadMutation.isPending}
            onClick={() => fileInputRef.current?.click()}
            data-testid="art-upload-button"
          >
            {uploadMutation.isPending ? 'Uploading…' : 'Upload and hang'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
