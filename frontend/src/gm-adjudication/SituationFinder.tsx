/**
 * SituationFinder: kind-first browse over the GM discovery catalog (#3564).
 *
 * Mirrors telnet's `setsituation find`: search returns situation kinds first
 * (each carrying the checks that fit it, difficulty guidance for the current
 * risk, and pool guidance), then loose situation templates and challenges.
 * Kinds above the caller's tier never appear server-side, so there is no
 * client-side filtering here beyond forwarding the typed query and the
 * declared risk to `useDiscovery`.
 *
 * The host wires up what a chosen row actually does (stage a situation, call
 * a check, place a challenge) via `actions`, a button is hidden entirely
 * when the host doesn't supply a handler for that row kind, so this
 * component stays usable as a read-only reference browser too.
 */

import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useDiscovery } from './queries';
import type {
  DiscoveryChallenge,
  DiscoveryDifficultyGuide,
  DiscoveryKind,
  DiscoveryTemplate,
} from './types';
import { CatalogSuggestionDialog } from './CatalogSuggestionDialog';

export interface FinderActions {
  /** Label and handler for a template row's button; omit to hide the button. */
  template?: { label: string; onSelect: (template: DiscoveryTemplate) => void };
  challenge?: { label: string; onSelect: (challenge: DiscoveryChallenge) => void };
  /** Clicking a fitting check. `band` is the guide's recommended difficulty for the
   *  finder's risk, or null when there is no guide for it. */
  check?: {
    label: string;
    onSelect: (check: { id: number; name: string }, band: string | null) => void;
  };
}

export interface SituationFinderProps {
  risk: string | null;
  actions: FinderActions;
  /** When non-null, "Suggest an entry" is offered and dispatches as this character. */
  characterId: number | null;
}

interface KindCardProps {
  kind: DiscoveryKind;
  risk: string | null;
  actions: FinderActions;
  characterId: number | null;
}

interface DifficultyGuideBlockProps {
  risk: string | null;
  guide: DiscoveryDifficultyGuide | null;
  allGuides: DiscoveryDifficultyGuide[];
}

function DifficultyGuideBlock({ risk, guide, allGuides }: DifficultyGuideBlockProps) {
  if (guide) {
    return (
      <p>
        At {risk} risk: {guide.recommended_difficulty}. {guide.guidance_text}
      </p>
    );
  }
  if (allGuides.length > 0) {
    return (
      <ul className="space-y-0.5">
        {allGuides.map((g) => (
          <li key={g.risk}>
            {g.risk}: {g.recommended_difficulty}
          </li>
        ))}
      </ul>
    );
  }
  return <p className="text-muted-foreground">No difficulty guide yet</p>;
}

function KindCard({ kind, risk, actions, characterId }: KindCardProps) {
  const [suggestOpen, setSuggestOpen] = useState(false);
  const band = kind.difficulty_guide?.recommended_difficulty ?? null;

  return (
    <div
      className="space-y-2 rounded-md border p-3"
      data-testid="finder-kind"
      data-kind-id={kind.id}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold">{kind.name}</span>
        <Badge variant="outline">{kind.minimum_gm_level}</Badge>
      </div>
      {kind.description && <p className="text-sm text-muted-foreground">{kind.description}</p>}

      {kind.check_fits.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-semibold uppercase text-muted-foreground">Checks that fit</p>
          {kind.check_fits.map((fit) => (
            <div
              key={fit.check_type.id}
              className="flex items-center justify-between gap-2"
              data-testid="finder-check-fit"
              data-check-id={fit.check_type.id}
            >
              <span>
                <span className="font-medium">{fit.check_type.name}</span>
                {fit.fit_notes && <span className="text-muted-foreground"> - {fit.fit_notes}</span>}
              </span>
              {actions.check && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() =>
                    actions.check?.onSelect(
                      { id: fit.check_type.id, name: fit.check_type.name },
                      band
                    )
                  }
                >
                  {actions.check.label}
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      <div data-testid="finder-guide" className="text-sm">
        <DifficultyGuideBlock
          risk={risk}
          guide={kind.difficulty_guide}
          allGuides={kind.all_guides}
        />
      </div>

      {kind.pool_guides.map((poolGuide) => (
        <div
          key={poolGuide.pool.id}
          data-testid="finder-pool-guide"
          className="space-y-0.5 text-sm"
        >
          <span className="flex items-center gap-2">
            <span className="font-medium">{poolGuide.pool.name}</span>
            {poolGuide.is_default && <Badge variant="secondary">default</Badge>}
          </span>
          <p className="text-muted-foreground">{poolGuide.selection_criteria}</p>
          <p className="text-xs text-muted-foreground">
            Advisory only: the pool is still your pick
          </p>
        </div>
      ))}

      {characterId != null && (
        <>
          <Button
            size="sm"
            variant="ghost"
            data-testid="finder-suggest"
            onClick={() => setSuggestOpen(true)}
          >
            Suggest an entry
          </Button>
          <CatalogSuggestionDialog
            open={suggestOpen}
            onOpenChange={setSuggestOpen}
            characterId={characterId}
            kindName={kind.name}
          />
        </>
      )}
    </div>
  );
}

export function SituationFinder({ risk, actions, characterId }: SituationFinderProps) {
  const [query, setQuery] = useState('');
  const [bottomSuggestOpen, setBottomSuggestOpen] = useState(false);
  const trimmedQuery = query.trim();
  const { data } = useDiscovery(trimmedQuery, risk, true);

  const kinds = data?.kinds ?? [];
  const templates = data?.templates ?? [];
  const challenges = data?.challenges ?? [];
  const nothingMatched = kinds.length === 0 && templates.length === 0 && challenges.length === 0;

  return (
    <div className="space-y-3" data-testid="situation-finder">
      <Input
        data-testid="finder-search"
        placeholder="Search kinds, situations and challenges"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <p className="text-sm font-semibold text-muted-foreground">
        {trimmedQuery ? `Matches for "${trimmedQuery}"` : 'Kinds within your tier'}
      </p>

      {trimmedQuery !== '' && nothingMatched && (
        <p data-testid="finder-empty" className="text-sm text-muted-foreground">
          No matches for &quot;{trimmedQuery}&quot;.
        </p>
      )}

      {kinds.length > 0 && (
        <div className="space-y-2">
          {kinds.map((kind) => (
            <KindCard
              key={kind.id}
              kind={kind}
              risk={risk}
              actions={actions}
              characterId={characterId}
            />
          ))}
        </div>
      )}

      {kinds.length === 0 && characterId != null && (
        <>
          <Button
            size="sm"
            variant="ghost"
            data-testid="finder-suggest"
            onClick={() => setBottomSuggestOpen(true)}
          >
            Suggest an entry
          </Button>
          <CatalogSuggestionDialog
            open={bottomSuggestOpen}
            onOpenChange={setBottomSuggestOpen}
            characterId={characterId}
          />
        </>
      )}

      {templates.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-semibold">Situations</p>
          {templates.map((template) => (
            <div
              key={template.id}
              className="flex items-center justify-between gap-2 rounded-md border p-2"
              data-testid="finder-template"
              data-template-id={template.id}
            >
              <div>
                <p className="font-medium">{template.name}</p>
                <p className="text-xs text-muted-foreground">{template.category_name}</p>
                {template.description_template && (
                  <p className="text-sm">{template.description_template}</p>
                )}
              </div>
              {actions.template && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => actions.template?.onSelect(template)}
                >
                  {actions.template.label}
                </Button>
              )}
            </div>
          ))}
        </div>
      )}

      {challenges.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm font-semibold">Challenges</p>
          {challenges.map((challenge) => (
            <div
              key={challenge.id}
              className="flex items-center justify-between gap-2 rounded-md border p-2"
              data-testid="finder-challenge"
              data-challenge-id={challenge.id}
            >
              <div>
                <p className="font-medium">{challenge.name}</p>
                <p className="text-xs text-muted-foreground">
                  {challenge.category_name} - severity {challenge.severity ?? 0}
                </p>
                {challenge.goal && <p className="text-sm">{challenge.goal}</p>}
              </div>
              {actions.challenge && (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => actions.challenge?.onSelect(challenge)}
                >
                  {actions.challenge.label}
                </Button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
