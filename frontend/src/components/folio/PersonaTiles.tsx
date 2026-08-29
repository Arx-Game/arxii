import {
  useCharacterPersonasQuery,
  useSetActivePersonaMutation,
  type SwitchablePersona,
} from '@/game/personaQueries';
import { cn } from '@/lib/utils';

export interface PersonaTilesProps {
  characterSheetId: number;
  activePersonaId: number | null;
  className?: string;
}

function thumbnailFor(p: SwitchablePersona): string | null {
  return p.thumbnail_media_url ?? p.thumbnail_url ?? null;
}

/**
 * Commonplace Book folio primitive (#3412, Direction B — ratified 2026-08-28).
 *
 * A row of small square tabs beneath a portrait, one per persona the
 * character can wear — the active tile takes the primary border/text
 * treatment, the rest sit muted. Selecting a tile calls the existing
 * `useSetActivePersonaMutation` (same mutation `PersonaSwitcher` uses; both
 * read/write the same `useCharacterPersonasQuery` cache, so switching from
 * either surface reads back identically from the other).
 *
 * Renders NOTHING for a single-persona character (ruled) — there is nothing
 * to switch between, so no tab strip. Each tile shows its persona's
 * thumbnail when set (`thumbnail_media_url` over `thumbnail_url`, mirroring
 * `PersonaSwitcher`/`PersonaAvatar`'s own precedence), else the persona's
 * name as small text — never initials-only, per the ruling ("name-only
 * otherwise").
 */
export function PersonaTiles({ characterSheetId, activePersonaId, className }: PersonaTilesProps) {
  const { data: personas = [] } = useCharacterPersonasQuery(characterSheetId);
  const setActive = useSetActivePersonaMutation();

  if (personas.length <= 1) return null;

  return (
    <div className={cn('flex flex-wrap gap-1', className)} role="tablist" aria-label="Personas">
      {personas.map((p) => {
        const active = p.id === activePersonaId;
        const thumb = thumbnailFor(p);
        return (
          <button
            key={p.id}
            type="button"
            role="tab"
            aria-selected={active}
            title={active ? `${p.name} (currently worn)` : `Switch to ${p.name}`}
            disabled={setActive.isPending}
            onClick={() => {
              if (!active) setActive.mutate(p.id);
            }}
            className={cn(
              'flex h-8 w-8 shrink-0 items-center justify-center overflow-hidden',
              'rounded-none border disabled:opacity-50',
              active
                ? 'border-primary text-primary'
                : 'border-border text-muted-foreground hover:text-foreground'
            )}
          >
            {thumb ? (
              <img src={thumb} alt="" className="h-full w-full object-cover" />
            ) : (
              <span
                className={cn(
                  'line-clamp-2 px-0.5 text-center text-[9px] font-medium leading-tight'
                )}
              >
                {p.name}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
