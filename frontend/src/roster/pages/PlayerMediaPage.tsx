import { usePlayerMediaQuery } from '../queries';
import { MediaUploadForm } from '../components/MediaUploadForm';
import { GalleryManagement } from '../components/GalleryManagement';

export function PlayerMediaPage() {
  const { data: media, refetch } = usePlayerMediaQuery();

  return (
    <div className="container mx-auto space-y-4 p-4">
      <h2 className="text-xl font-semibold">My Media</h2>
      <ul className="space-y-2">
        {media?.map((m) => (
          <li key={m.id} className="border p-2">
            <p>{m.title || m.cloudinary_public_id}</p>
          </li>
        ))}
      </ul>

      <MediaUploadForm onUploadComplete={refetch} />
      <GalleryManagement />
    </div>
  );
}
