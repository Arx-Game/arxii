/**
 * A picture shown through a crop that has not been saved yet (#4151): the cropper's
 * live previews. Saved looks are shown through their server-cropped `look_url` instead.
 */
import { type CropRect, type ImageSize, cropImageStyle } from './cropMath';
import { cn } from '@/lib/utils';

interface CropPreviewProps {
  src: string;
  crop: CropRect;
  image: ImageSize;
  /** Show the square at the top of the crop, as the looks strip and chips do. */
  squareTop?: boolean;
  className?: string;
}

export function CropPreview({ src, crop, image, squareTop = false, className }: CropPreviewProps) {
  return (
    <div className={cn('gallery-crop-preview', className)}>
      <img src={src} alt="" draggable={false} style={cropImageStyle(crop, image, squareTop)} />
    </div>
  );
}
