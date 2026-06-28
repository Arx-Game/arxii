import { useMemo } from 'react';

import { PersonaAvatar, type PersonaAvatarSource } from '@/components/PersonaAvatar';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';

import {
  useCharacterPersonasQuery,
  useSetActivePersonaMutation,
  type SwitchablePersona,
} from '../personaQueries';

interface PersonaSwitcherProps {
  characterSheetId: number;
  activePersonaId: number | null;
}

const TYPE_LABEL: Record<SwitchablePersona['persona_type'], string> = {
  primary: 'True self',
  established: 'Alt identity',
  temporary: 'Mask',
  alternate: 'Alternate form',
};

function avatarSource(p: SwitchablePersona): PersonaAvatarSource {
  return { name: p.name, thumbnailUrl: p.thumbnail_url, thumbnailMediaUrl: p.thumbnail_media_url };
}

/**
 * Top-bar control for the face the player is presenting as (#1043).
 *
 * Shows the worn identity and, when the character has more than one face, lets the
 * player switch via `POST /api/personas/set-active/`. The worn face is made
 * deliberately obvious so a player never acts as the wrong identity by accident.
 */
export function PersonaSwitcher({ characterSheetId, activePersonaId }: PersonaSwitcherProps) {
  const { data: personas = [] } = useCharacterPersonasQuery(characterSheetId);
  const setActive = useSetActivePersonaMutation();

  const worn = useMemo(
    () =>
      personas.find((p) => p.id === activePersonaId) ??
      personas.find((p) => p.persona_type === 'primary') ??
      personas[0],
    [personas, activePersonaId]
  );

  if (!worn) return null;

  // A single face — nothing to switch; just name the worn identity.
  if (personas.length <= 1) {
    return <span className="text-sm font-medium">{worn.name}</span>;
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="flex items-center gap-1.5 rounded px-2 py-1 text-sm font-medium ring-1 ring-primary/40 hover:bg-accent disabled:opacity-50"
        disabled={setActive.isPending}
        title="Switch which identity you are presenting as"
      >
        <span>{worn.name}</span>
        <span className="text-xs text-muted-foreground" aria-hidden>
          ▾
        </span>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-56">
        <DropdownMenuLabel>Presenting as</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuRadioGroup
          value={worn.id.toString()}
          onValueChange={(value) => {
            const id = Number(value);
            if (id !== worn.id) {
              setActive.mutate(id);
            }
          }}
        >
          {personas.map((p) => (
            <DropdownMenuRadioItem key={p.id} value={p.id.toString()} className="gap-2">
              <PersonaAvatar source={avatarSource(p)} size="sm" />
              <span className="flex flex-col">
                <span>{p.name}</span>
                <span className="text-xs text-muted-foreground">{TYPE_LABEL[p.persona_type]}</span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
