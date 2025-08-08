import type { CharacterData } from '../../roster/types';

interface CharacterPortraitProps {
  character: CharacterData;
}

export function CharacterPortrait({ character }: CharacterPortraitProps) {
  return (
    <div className="flex flex-col items-start gap-4 sm:flex-row">
      <img
        src={character.portrait}
        alt={`${character.name} portrait`}
        className="h-48 w-48 rounded object-cover"
      />
      <h2 className="text-2xl font-bold">{character.name}</h2>
    </div>
  );
}
