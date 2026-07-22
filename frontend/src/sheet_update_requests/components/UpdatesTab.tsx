/**
 * UpdatesTab (#2631) — the character sheet's Updates & History section.
 *
 * The prose version timeline is owner/staff-only by default (the server
 * returns an empty list for everyone else — this component never
 * re-implements privacy client-side; it only hides the empty section for
 * non-owners so strangers don't see a pointless header). The owner
 * additionally gets the update-request form (profile prose rewrite or
 * distinction change, routed to their table GM) and their request list with
 * withdraw. Distinction approvals auto-debit XP at GM sign-off (#2628) —
 * there is no accept step.
 */

import { useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { useQuery } from '@tanstack/react-query';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';
import { useCharacterSheetQuery } from '@/character_sheets/queries';
import { getTableMemberships } from '@/tables/api';

import {
  useCreateUpdateRequestMutation,
  useProfileTextVersionsQuery,
  useUpdateRequestsQuery,
  useWithdrawMutation,
} from '../queries';
import {
  DISTINCTION_ACTIONS,
  PROFILE_TEXT_FIELDS,
  REQUEST_KINDS,
  REQUEST_STATUSES,
  type TableUpdateRequest,
} from '../types';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk). */
  characterId: number;
  isMyCharacter: boolean;
}

interface CatalogDistinction {
  id: number;
  name: string;
}

async function fetchDistinctionCatalog(): Promise<CatalogDistinction[]> {
  const res = await apiFetch('/api/distinctions/distinctions/');
  if (!res.ok) await throwApiError(res, 'Failed to load distinctions');
  return res.json() as Promise<CatalogDistinction[]>;
}

const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  [REQUEST_STATUSES.PENDING]: 'outline',
  [REQUEST_STATUSES.APPROVED]: 'default',
  [REQUEST_STATUSES.COMPLETED]: 'secondary',
  [REQUEST_STATUSES.REJECTED]: 'destructive',
  [REQUEST_STATUSES.WITHDRAWN]: 'secondary',
};

function formatStamp(version: {
  era_season_number?: number | null;
  ic_date?: string | null;
  created_at?: string;
}): string {
  const parts: string[] = [];
  if (version.era_season_number != null) parts.push(`Season ${version.era_season_number}`);
  if (version.ic_date) parts.push(new Date(version.ic_date).toLocaleDateString());
  if (parts.length === 0 && version.created_at) {
    parts.push(new Date(version.created_at).toLocaleDateString());
  }
  return parts.join(' · ');
}

function VersionTimeline({
  characterId,
  showEmptyState,
}: {
  characterId: number;
  showEmptyState: boolean;
}) {
  const { data: versions, isLoading } = useProfileTextVersionsQuery(characterId);

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }
  if (!versions || versions.length === 0) {
    if (!showEmptyState) return null;
    return (
      <section className="space-y-2">
        <h3 className="text-xl font-semibold">Sheet history</h3>
        <p className="py-4 text-center text-muted-foreground">No recorded history yet.</p>
      </section>
    );
  }

  const byField = new Map<string, typeof versions>();
  for (const version of versions) {
    const list = byField.get(version.field) ?? [];
    list.push(version);
    byField.set(version.field, list);
  }

  return (
    <div className="space-y-6" data-testid="profile-version-timeline">
      <h3 className="text-xl font-semibold">Sheet history</h3>
      {[...byField.entries()].map(([field, fieldVersions]) => (
        <section key={field} className="space-y-2">
          <h4 className="text-lg font-semibold capitalize">{field}</h4>
          {fieldVersions.map((version) => (
            <Card key={version.id}>
              <CardContent className="space-y-2 py-4">
                <div className="flex items-center justify-between gap-2 text-sm text-muted-foreground">
                  <span>{formatStamp(version)}</span>
                  {version.staff_edited && <Badge variant="outline">Staff edit</Badge>}
                </div>
                {version.reasoning && (
                  <p className="text-sm italic text-muted-foreground">{version.reasoning}</p>
                )}
                <p className="whitespace-pre-wrap text-sm">{version.text}</p>
              </CardContent>
            </Card>
          ))}
        </section>
      ))}
    </div>
  );
}

function RequestRow({ request }: { request: TableUpdateRequest }) {
  const withdraw = useWithdrawMutation();

  const details = request.distinction_details;

  return (
    <Card data-testid="update-request-row">
      <CardContent className="space-y-2 py-4">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium">
            {request.kind === REQUEST_KINDS.PROFILE_TEXT
              ? `Profile: ${request.profile_text_details?.field ?? ''}`
              : `Distinction: ${
                  details?.distinction_name ?? details?.held_distinction_name ?? ''
                } (${details?.action === DISTINCTION_ACTIONS.REMOVE ? 'shed' : 'gain'}${
                  details?.xp_cost ? `, ${details.xp_cost} XP` : ''
                })`}
          </span>
          <Badge variant={STATUS_VARIANTS[request.status ?? ''] ?? 'outline'}>
            {request.status}
          </Badge>
        </div>
        <p className="text-sm text-muted-foreground">{request.player_reasoning}</p>
        {request.gm_notes && (
          <p className="text-sm">
            <span className="font-medium">GM notes:</span> {request.gm_notes}
          </p>
        )}
        {request.status === REQUEST_STATUSES.PENDING && (
          <Button
            size="sm"
            variant="outline"
            disabled={withdraw.isPending}
            onClick={() => withdraw.mutate(request.id)}
          >
            Withdraw
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function SubmitRequestForm({ characterId }: { characterId: number }) {
  const { data: sheetPayload } = useCharacterSheetQuery(characterId);
  const { data: membershipsPage } = useQuery({
    queryKey: ['sheet-update-requests', 'memberships', characterId],
    queryFn: () => getTableMemberships({ active: true }),
  });
  const { data: catalog } = useQuery({
    queryKey: ['distinction-catalog'],
    queryFn: fetchDistinctionCatalog,
  });
  const createRequest = useCreateUpdateRequestMutation();

  const myMemberships = useMemo(
    () =>
      (membershipsPage?.results ?? []).filter(
        (membership) => (membership as { character_sheet?: number }).character_sheet === characterId
      ),
    [membershipsPage, characterId]
  );

  const [membershipId, setMembershipId] = useState<number | ''>('');
  const [kind, setKind] = useState<string>(REQUEST_KINDS.PROFILE_TEXT);
  const [field, setField] = useState<string>(PROFILE_TEXT_FIELDS[0].value);
  const [proposedText, setProposedText] = useState('');
  const [action, setAction] = useState<string>(DISTINCTION_ACTIONS.ADD);
  const [distinctionId, setDistinctionId] = useState<number | ''>('');
  const [heldId, setHeldId] = useState<number | ''>('');
  const [reasoning, setReasoning] = useState('');

  const selectedMembership = membershipId || myMemberships[0]?.id || '';
  const heldDistinctions = sheetPayload?.distinctions ?? [];
  const currentText =
    field === 'background'
      ? (sheetPayload?.story?.background ?? '')
      : (sheetPayload?.story?.personality ?? '');

  if (myMemberships.length === 0) {
    return (
      <p className="py-4 text-sm text-muted-foreground">
        Sheet updates go through the GM whose table you play at — join a table to submit one.
      </p>
    );
  }

  const submit = () => {
    if (!selectedMembership || !reasoning.trim()) return;
    if (kind === REQUEST_KINDS.PROFILE_TEXT) {
      createRequest.mutate({
        membership: selectedMembership as number,
        kind,
        reasoning,
        field,
        proposed_text: proposedText,
      });
    } else {
      createRequest.mutate({
        membership: selectedMembership as number,
        kind,
        reasoning,
        action,
        distinction:
          action === DISTINCTION_ACTIONS.ADD && distinctionId !== '' ? distinctionId : undefined,
        character_distinction:
          action === DISTINCTION_ACTIONS.REMOVE && heldId !== '' ? heldId : undefined,
      });
    }
    setProposedText('');
    setReasoning('');
  };

  const selectClass = 'w-full rounded-md border bg-background p-2 text-sm';

  return (
    <div className="space-y-3">
      {myMemberships.length > 1 && (
        <label className="block text-sm">
          Table
          <select
            className={selectClass}
            value={selectedMembership}
            onChange={(e) => setMembershipId(Number(e.target.value))}
          >
            {myMemberships.map((membership) => (
              <option key={membership.id} value={membership.id}>
                {(membership as { table_name?: string }).table_name ?? `Table ${membership.table}`}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className="block text-sm">
        What kind of update
        <select className={selectClass} value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value={REQUEST_KINDS.PROFILE_TEXT}>Profile text (free)</option>
          <option value={REQUEST_KINDS.DISTINCTION_CHANGE}>Distinction change</option>
        </select>
      </label>

      {kind === REQUEST_KINDS.PROFILE_TEXT ? (
        <>
          <label className="block text-sm">
            Field
            <select
              className={selectClass}
              value={field}
              onChange={(e) => {
                setField(e.target.value);
                setProposedText('');
              }}
            >
              {PROFILE_TEXT_FIELDS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            New text (full replacement)
            <Textarea
              rows={8}
              value={proposedText}
              placeholder={currentText ? 'Rewrite the current text…' : 'Write the new text…'}
              onChange={(e) => setProposedText(e.target.value)}
            />
          </label>
          {currentText && (
            <details className="text-sm text-muted-foreground">
              <summary className="cursor-pointer">Current {field}</summary>
              <p className="whitespace-pre-wrap pt-2">{currentText}</p>
            </details>
          )}
        </>
      ) : (
        <>
          <label className="block text-sm">
            Change
            <select
              className={selectClass}
              value={action}
              onChange={(e) => setAction(e.target.value)}
            >
              <option value={DISTINCTION_ACTIONS.ADD}>Gain / rank up</option>
              <option value={DISTINCTION_ACTIONS.REMOVE}>Lose / shed</option>
            </select>
          </label>
          {action === DISTINCTION_ACTIONS.ADD ? (
            <label className="block text-sm">
              Distinction (one already held ranks it up a step)
              <select
                className={selectClass}
                value={distinctionId}
                onChange={(e) => setDistinctionId(Number(e.target.value))}
              >
                <option value="">Choose…</option>
                {(catalog ?? []).map((distinction) => (
                  <option key={distinction.id} value={distinction.id}>
                    {distinction.name}
                  </option>
                ))}
              </select>
            </label>
          ) : (
            <label className="block text-sm">
              Held distinction
              <select
                className={selectClass}
                value={heldId}
                onChange={(e) => setHeldId(Number(e.target.value))}
              >
                <option value="">Choose…</option>
                {heldDistinctions.map((held) => (
                  <option key={held.id} value={held.id}>
                    {held.name} (rank {held.rank})
                  </option>
                ))}
              </select>
            </label>
          )}
        </>
      )}

      <label className="block text-sm">
        Reason
        <Textarea
          rows={3}
          value={reasoning}
          placeholder="Why does the story support this change?"
          onChange={(e) => setReasoning(e.target.value)}
        />
      </label>

      <Button
        disabled={
          createRequest.isPending ||
          !reasoning.trim() ||
          (kind === REQUEST_KINDS.PROFILE_TEXT && !proposedText.trim()) ||
          (kind === REQUEST_KINDS.DISTINCTION_CHANGE &&
            ((action === DISTINCTION_ACTIONS.ADD && distinctionId === '') ||
              (action === DISTINCTION_ACTIONS.REMOVE && heldId === '')))
        }
        onClick={submit}
      >
        Submit to your GM
      </Button>
    </div>
  );
}

export function UpdatesTab({ characterId, isMyCharacter }: Props) {
  const { data: myRequests } = useUpdateRequestsQuery({ role: 'mine' }, isMyCharacter);

  const requestsForSheet = (myRequests?.results ?? []).filter(
    (request) => request.character_sheet === characterId
  );

  return (
    <div className="space-y-8">
      {isMyCharacter && (
        <Card>
          <CardHeader>
            <CardTitle>Request a sheet update</CardTitle>
          </CardHeader>
          <CardContent>
            <SubmitRequestForm characterId={characterId} />
          </CardContent>
        </Card>
      )}

      {isMyCharacter && requestsForSheet.length > 0 && (
        <section className="space-y-2">
          <h3 className="text-xl font-semibold">My requests</h3>
          {requestsForSheet.map((request) => (
            <RequestRow key={request.id} request={request} />
          ))}
        </section>
      )}

      <VersionTimeline characterId={characterId} showEmptyState={isMyCharacter} />
    </div>
  );
}
