import type { ReactNode } from 'react';
import type { CharacterData, RosterEntryData } from '@/roster/types';

interface CharacterPortraitProps {
  name: CharacterData['name'];
  profilePicture?: RosterEntryData['profile_picture'];
  /** Optional subtitle content rendered under the name (e.g. covenant/family lines, #1446). */
  children?: ReactNode;
}

export function CharacterPortrait({ name, profilePicture, children }: CharacterPortraitProps) {
  const url = profilePicture?.media.cloudinary_url;
  return (
    <div className="flex flex-col items-start gap-4 sm:flex-row">
      {url ? (
        <img src={url} alt={`${name} portrait`} className="h-48 w-48 rounded object-cover" />
      ) : (
        <div className="h-48 w-48 rounded bg-gray-200" />
      )}
      <div>
        <h2 className="text-2xl font-bold">{name}</h2>
        {children}
      </div>
    </div>
  );
}
