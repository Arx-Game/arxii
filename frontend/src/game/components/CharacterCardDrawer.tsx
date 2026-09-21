import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import { BackgroundSection, StatsSection, CharacterLink } from '@/components/character';
import { FriendButton } from '@/friends/components/FriendButton';
import { useRosterEntryByNameQuery, useRosterEntryQuery } from '@/roster/queries';
import type { PoseUnitAvatarClickPersona } from '@/scenes/components/PoseUnit';
import { JournalComposerDialog } from '@/journals/components/JournalComposerDialog';
import { MessagePlayerDialog } from './MessagePlayerDialog';

export interface CharacterCardDrawerProps {
  /** The clicked bubble's persona identity; `null` means the drawer is closed. */
  persona: PoseUnitAvatarClickPersona | null;
  onClose: () => void;
  /** The viewer's active character's RosterEntry id, for the FriendButton. */
  viewerEntryId: number | null;
  /** Fired with the persona's name; caller sets composer mode + closes. */
  onWhisper: (name: string) => void;
}

/**
 * Avatar-click identity card (#2156) — opens in-place over the conversation
 * (a `Sheet` drawer, not a page navigation) with quick Friend/Whisper actions.
 *
 * PRIVACY (never out alts / disguise integrity): the persona payload carried by
 * an `Interaction` has no roster-entry or character-sheet id — only id/name/
 * thumbnail. This is deliberate: resolving identity through anything other than
 * the PUBLIC roster search would leak a disguised or temporary persona's real
 * character. So this card resolves the profile ONLY via `useRosterEntryByNameQuery`
 * (the same public, `AllowAny` `/api/roster/entries/?name=` search
 * `RosterListPage` uses) and only accepts an EXACT name match (the filter itself
 * is `icontains` server-side). No match — a disguise, a temporary persona, or an
 * unlisted character — renders name + avatar + "This face isn't on the public
 * roster." and no sheet data, no FriendButton. Never resolve through
 * `receiver_persona_ids`, scene participation, or any other non-public linkage.
 *
 * Quick actions: "Declare a tie" (#3957) leads to the VIEWER's own tie page in declare
 * mode — the route's `:id` is the character whose side the tie is, which is the viewer,
 * not the person in the drawer — carrying the clicked persona and its name so the page
 * can print who the tie is toward and the picker opens on the right person. The roster
 * match still gates the link, so a disguise or a temporary persona offers no door at
 * all. It replaced "Record an impression", whose writeup dialog went with the writeups.
 * "Write a journal" (#2160) opens `JournalComposerDialog` pre-tagged with the resolved
 * character's name once `entry` resolves. "Message the player" (#2160) opens
 * `MessagePlayerDialog` - an OOC message to whoever currently plays this
 * character, pre-addressed to their live tenure
 * (`entry.tenures.find(t => t.end_date === null)`) - hidden when there's no
 * live tenure, since a vacant character has no one to address (same gating
 * philosophy as the FriendButton viewer-required gate below).
 *
 * Radix note: `SheetContent`'s `hideOverlay` only removes the dimming backdrop —
 * the underlying Dialog is still `modal` (focus-trapped, outside pointer events
 * disabled) unless `Sheet` itself is given `modal={false}`, which most of this
 * repo's other `Sheet` usages don't do either. Making the conversation genuinely
 * interactive behind the drawer needs `modal={false}` *and* suppressing the
 * default dismiss-on-outside-interaction, which is more surface than this task's
 * brief calls for — accepting the brief's own fallback: overlay + click-outside
 * (or Esc, or the close button) to close.
 */
export function CharacterCardDrawer({
  persona,
  onClose,
  viewerEntryId,
  onWhisper,
}: CharacterCardDrawerProps) {
  const { data: searchResult, isLoading: searching } = useRosterEntryByNameQuery(persona?.name);
  const match = searchResult?.results.find((entry) => entry.character.name === persona?.name);
  const matchId = match?.id;
  const { data: entry } = useRosterEntryQuery(matchId ?? 0);
  const liveTenure = entry?.tenures.find((tenure) => tenure.end_date === null) ?? null;

  const [journalOpen, setJournalOpen] = useState(false);
  const [messageOpen, setMessageOpen] = useState(false);

  const handleWhisper = () => {
    if (!persona) return;
    onWhisper(persona.name);
    onClose();
  };

  const renderSearching = () => {
    if (searching) {
      return <p className="mt-4 text-sm text-muted-foreground">Loading…</p>;
    }
    if (match && entry) {
      return (
        <div className="mt-4 space-y-4">
          <BackgroundSection background={entry.character.background} />
          <StatsSection
            age={entry.character.age}
            birthday={entry.character.birthday}
            gender={entry.character.gender}
            race={entry.character.race}
            charClass={entry.character.char_class}
            level={entry.character.level}
            concept={entry.character.concept}
            family={entry.character.family}
            vocation={entry.character.vocation}
            socialRank={entry.character.social_rank}
          />
          <CharacterLink id={match.id} className="text-sm underline">
            Full profile →
          </CharacterLink>
        </div>
      );
    }
    return (
      <p className="mt-4 text-sm text-muted-foreground">This face isn't on the public roster.</p>
    );
  };

  return (
    <Sheet
      open={persona !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
        {persona && (
          <>
            <SheetHeader>
              <div className="flex items-center gap-3">
                <PersonaAvatar
                  source={{ name: persona.name, thumbnailUrl: persona.thumbnail_url }}
                  size="lg"
                />
                <SheetTitle>{persona.name}</SheetTitle>
              </div>
            </SheetHeader>

            <div className="mt-4 flex flex-wrap items-center gap-3">
              {matchId != null && (
                <FriendButton
                  viewerEntryId={viewerEntryId}
                  targetEntryId={matchId}
                  targetName={persona.name}
                />
              )}
              <Button type="button" variant="outline" size="sm" onClick={handleWhisper}>
                Whisper
              </Button>
              {matchId != null && viewerEntryId != null && (
                <Link
                  to={
                    `/characters/${viewerEntryId}/ties/new` +
                    `?persona=${persona.id}&name=${encodeURIComponent(persona.name)}`
                  }
                  className="rounded border px-3 py-1 text-sm hover:bg-accent"
                >
                  Declare a tie
                </Link>
              )}
              {entry && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setJournalOpen(true)}
                >
                  Write a journal
                </Button>
              )}
              {entry && liveTenure && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setMessageOpen(true)}
                >
                  Message the player
                </Button>
              )}
            </div>

            {entry && (
              <JournalComposerDialog
                open={journalOpen}
                onClose={() => setJournalOpen(false)}
                initialTags={[entry.character.name]}
              />
            )}
            {entry && liveTenure && (
              <MessagePlayerDialog
                open={messageOpen}
                onClose={() => setMessageOpen(false)}
                recipientTenureId={liveTenure.id}
                recipientDisplay={entry.character.name}
              />
            )}

            {renderSearching()}
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
