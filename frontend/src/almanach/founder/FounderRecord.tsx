/**
 * FounderRecord (#3983 Plan B Task 6, plate F-VI "The Record") — the review
 * plate: every value quoted straight from the draft, nothing composed.
 * Submit posts `toClaimPayload(draft, template)` through `submitHouseClaim`;
 * on success the draft is cleared and the parent (`FounderAlmanach`) is told
 * so it can show the full-bleed `SubmittedPlate` in place of the whole
 * chassis (this component itself only ever renders inside `.almanac`'s
 * `.chapter` slot, never full-bleed — see `FounderAlmanach.tsx`).
 *
 * `landLine`/`estateLine` arrive pre-composed from `FounderAlmanach`
 * (`landBaseLine`, `./steps`, plus this plate's own shapes/produces
 * suffix) rather than being rebuilt here — `RecordSoFar`'s abbreviated "the
 * land" row needs the same base clause, so the shell builds it once and
 * hands both callers a plain string.
 */
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import type { HouseClaimStatus, HouseTemplateOption } from '@/character-creation/api';
import { submitHouseClaim } from '@/character-creation/api';
import type { ClaimKinRelation } from '@/character-creation/types';

import { REVIEW_NOTE } from '../copy';
import { tierNoun } from '../ladder/tree';
import { useCharter } from '../queries';

import { RELATION_WORDS } from './familyShape';
import { toClaimPayload, type FounderDraft, type UseFounderDraftResult } from './founderDraft';

/** Generational order "the family" line groups kin by (#3983 Plan B's
 * ruling): `head` is handled separately (at most one, first in the line),
 * `ward`/`position` never appear here (household, not lineage). The
 * founder's own synthetic entry is inserted at the START of her own
 * `founder_relation` group, ahead of any real kin sharing that relation —
 * matching the plate's own worked example (Marisol, the founder, ahead of
 * her nameless brother, both `child`). */
const GENERATION_ORDER: ClaimKinRelation[] = [
  'mother',
  'father',
  'spouse',
  'sibling',
  'child',
  'grandparent',
];

function styledName(name: string, particle: string, houseName: string): string {
  return `${name} ${particle} ${houseName}`.replace(/\s+/g, ' ').trim();
}

/** "the family" line (plate F-VI): every kin quoted by name, styled with
 * the charter particle (`taken_in` for a spouse — married in — `born` for
 * everyone else, including the head), and a trailing descriptor — the head
 * gets none (implicit, first in the line); everyone else gets
 * `RELATION_WORDS`; a nameless kin renders as `a <relation word>, to be
 * defined` rather than a styled name it doesn't have.
 *
 * The plate's own worked example additionally styles the head with a
 * gendered courtesy title ("Duchess Estuosa za Candela") — omitted here for
 * the same reason `FounderFamilyChapter`'s tree omits "daughter of": no
 * title/rank field exists on `FounderKin`, and no gender-name lookup reaches
 * these components (see that chapter's own report finding). */
function familyLine(
  draft: FounderDraft,
  youName: string,
  particle: { born: string; taken_in: string } | undefined
): string {
  const born = particle?.born ?? '';
  const takenIn = particle?.taken_in ?? '';
  const namedKin = draft.kin.filter((kin) => !kin.is_household);
  const entries: string[] = [];

  const headKin = namedKin.find((kin) => kin.relation === 'head');
  if (headKin) {
    entries.push(styledName(headKin.name, born, draft.house_name));
  } else if (draft.founder_relation === 'head') {
    entries.push(styledName(youName, born, draft.house_name));
  }

  for (const relation of GENERATION_ORDER) {
    if (draft.founder_relation === relation) {
      const particleWord = relation === 'spouse' ? takenIn : born;
      entries.push(
        `${styledName(youName, particleWord, draft.house_name)}, ${
          draft.founder_is_heir ? 'heir' : 'younger'
        }`
      );
    }
    for (const kin of namedKin) {
      if (kin.relation !== relation) continue;
      const word = RELATION_WORDS[relation];
      if (kin.name === '') {
        entries.push(`a ${word}, to be defined`);
        continue;
      }
      const particleWord = relation === 'spouse' ? takenIn : born;
      entries.push(`${styledName(kin.name, particleWord, draft.house_name)}, ${word}`);
    }
  }

  return entries.join(' · ');
}

export interface FounderRecordProps {
  draft: FounderDraft;
  characterDraftId: number;
  template: HouseTemplateOption;
  quiddityName: string;
  seatName: string;
  seatTier: string;
  swornTo: string;
  landLine: string;
  estateLine: string;
  realmId: number;
  youName: string;
  reset: UseFounderDraftResult['reset'];
  onBack: () => void;
  onSubmitted: (claim: HouseClaimStatus) => void;
}

export function FounderRecord({
  draft,
  characterDraftId,
  template,
  quiddityName,
  seatName,
  seatTier,
  swornTo,
  landLine,
  estateLine,
  realmId,
  youName,
  reset,
  onBack,
  onSubmitted,
}: FounderRecordProps) {
  const queryClient = useQueryClient();
  const { data: charter } = useCharter(realmId);

  const submit = useMutation({
    mutationFn: () => submitHouseClaim(characterDraftId, toClaimPayload(draft, template)),
    onSuccess: (claim) => {
      reset();
      void queryClient.invalidateQueries({
        queryKey: ['character-creation', 'house-claim', characterDraftId],
      });
      onSubmitted(claim);
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <main className="chapter">
      <h3>
        House {draft.house_name}{' '}
        <span className="tier">
          {tierNoun(seatTier, 1)} of {seatName}
          {swornTo !== '' && <> · sworn to {swornTo}</>}
        </span>
      </h3>
      <div className="row3">
        <div className="field">
          <span className="label">quiddity</span>
          <div className="val">
            {quiddityName !== '' ? quiddityName : <abbr title="none">—</abbr>}
          </div>
        </div>
        <div className="field">
          <span className="label">words</span>
          <div className="val">
            {draft.words !== '' ? draft.words : <abbr title="none">—</abbr>}
          </div>
        </div>
        <div className="field">
          <span className="label">colors</span>
          <div className="val">
            {draft.colors !== '' ? draft.colors : <abbr title="none">—</abbr>}
          </div>
        </div>
      </div>
      <div className="field">
        <span className="label">the house</span>
        <div className="prose">
          {draft.backstory !== '' ? draft.backstory : <abbr title="none">—</abbr>}
        </div>
      </div>
      <div className="field">
        <span className="label">the family</span>
        <div className="val">{familyLine(draft, youName, charter?.particle)}</div>
      </div>
      <div className="field">
        <span className="label">the land</span>
        <div className="val">{landLine !== '' ? landLine : <abbr title="none">—</abbr>}</div>
      </div>
      <div className="field">
        <span className="label">the estate</span>
        <div className="val">{estateLine !== '' ? estateLine : <abbr title="none">—</abbr>}</div>
      </div>
      <div className="savebar">
        <span className="note">{REVIEW_NOTE}</span>
        <button type="button" className="btn ghost" onClick={onBack}>
          Back
        </button>
        <button
          type="button"
          className="btn"
          disabled={submit.isPending}
          onClick={() => submit.mutate()}
        >
          Submit for review
        </button>
      </div>
    </main>
  );
}
