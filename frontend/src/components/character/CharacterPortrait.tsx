import type { CharacterData, TenureMedia } from '../../roster/types';

interface CharacterPortraitProps {
  name: CharacterData['name'];
  profilePicture?: TenureMedia['cloudinary_url'] | null;
}

export function CharacterPortrait({ name, profilePicture }: CharacterPortraitProps) {
  return (
    <div className="flex flex-col items-start gap-4 sm:flex-row">
      {profilePicture ? (
        <img
          src={profilePicture}
          alt={`${name} portrait`}
          className="h-48 w-48 rounded object-cover"
        />
      ) : (
        <div className="h-48 w-48 rounded bg-gray-200" />
      )}
      <h2 className="text-2xl font-bold">{name}</h2>
    </div>
  );
}
