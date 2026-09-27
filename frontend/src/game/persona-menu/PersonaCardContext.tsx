import { createContext, useContext } from 'react';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';

// Same shape as PoseUnit's avatar-click payload (#2156) — reused rather than
// redeclared (id, name, thumbnail_url).
export type CardPersona = PoseUnitAvatarClickPersona;

/** Lets any persona surface open the character card GamePage owns (#4030 View sheet). */
export const PersonaCardContext = createContext<{
  openCharacterCard: (persona: CardPersona) => void;
} | null>(null);

export function usePersonaCard() {
  return useContext(PersonaCardContext);
}
