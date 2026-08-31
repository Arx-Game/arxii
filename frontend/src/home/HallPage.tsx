/**
 * HallPage — the state-2 logged-in home at `/` (#3412 slice 2), Direction B
 * "Commonplace Book" idiom. Replaces the Gatefold advertisement for any
 * authenticated account (see `GatefoldPage`'s mount branch) — visitors never
 * reach this component.
 *
 * A zero-character account gets the existing `WelcomePanel` remedy content
 * (roster browse / create / pending application) in place of the character
 * grid — its own hasCharacters/pending-application logic is reused as-is,
 * never duplicated here. The Attention and World bands still render for a
 * zero-character account (an empty per-character Attention group, and World
 * band ambiance is account-independent) — only the character grid itself is
 * swapped out.
 *
 * GM/staff zero-character exception (#3478 fix round — spec is binding: a
 * GM/staff account "sees one extra slot alongside its characters," with no
 * zero-character carve-out): the `WelcomePanel` remedy is still shown (a
 * brand-new GM/staff account may also want the roster-browse/apply path),
 * but `CharactersBand` renders alongside it whenever `is_gm`/`is_staff` is
 * set — even with an empty `characters` array — so the GM slot's "Create GM
 * Profile" affordance (`GMSlot`, task 5) is reachable before the account has
 * ever picked up a PC. A plain player still gets the remedy alone.
 *
 * Loading vs. empty (review fix): the zero-character remedy is a real
 * degradation state, not a loading placeholder — showing it while
 * `useMyRosterEntriesQuery` is still resolving would flash the "you have no
 * characters" copy at an account that actually has some, on every `/` load.
 * Gated on the query's own `isLoading` with a quiet skeleton in between,
 * mirroring the skeleton-not-empty-state pattern `TidingsPage`/`WardrobePage`
 * already use for this exact race.
 *
 * Uses the viewer's own realm/mode tokens (NOT the Gatefold's forced-arx —
 * that's a visitor-advertisement rule, ADR-0227, not a logged-in rule).
 */
import { Plate, PlateHead } from '@/components/folio';
import { Skeleton } from '@/components/ui/skeleton';
import { WelcomePanel } from '@/components/WelcomePanel';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useAccount } from '@/store/hooks';
import { CharactersBand } from './hall/CharactersBand';
import { OffscreenActsPlate } from './hall/OffscreenActsPlate';
import { AttentionBand } from './hall/AttentionBand';
import { WorldBand } from './hall/WorldBand';

function CharactersLoadingSkeleton() {
  return (
    <div
      className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4"
      data-testid="characters-loading-skeleton"
    >
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-32 w-full" />
    </div>
  );
}

export function HallPage() {
  const { data: characters = [], isLoading } = useMyRosterEntriesQuery();
  const account = useAccount();
  const isGMOrStaff = !!account?.is_gm || !!account?.is_staff;

  return (
    <div className="container mx-auto space-y-4 px-4 py-6">
      {isLoading ? (
        <Plate className="p-4">
          <PlateHead as="h2" className="mb-3">
            Your Characters
          </PlateHead>
          <CharactersLoadingSkeleton />
        </Plate>
      ) : characters.length === 0 ? (
        <>
          <Plate className="p-4">
            <PlateHead as="h2" className="mb-3">
              Your Characters
            </PlateHead>
            <WelcomePanel />
          </Plate>
          {/* GM/staff zero-character exception — see header doc comment. */}
          {isGMOrStaff && <CharactersBand characters={characters} />}
        </>
      ) : (
        <CharactersBand characters={characters} />
      )}

      <OffscreenActsPlate characters={characters} />

      {/* 52rem, not a default Tailwind breakpoint (brief's explicit threshold) —
          arbitrary variant. Single column below stacks Attention above World
          (attention outranks ambiance). */}
      <div className="min-[52rem]:grid-cols-[1.55fr_1fr] grid grid-cols-1 gap-4">
        <AttentionBand characters={characters} />
        <WorldBand />
      </div>
    </div>
  );
}
