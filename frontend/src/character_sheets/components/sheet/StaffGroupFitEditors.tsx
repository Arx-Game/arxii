/**
 * Staff edit mode, piece E (#4229): group fit. Faces, titles, ties on both sides,
 * covenant roles and mentor bonds, written by staff fiat when a character is placed
 * into a group that already shares them. Other characters are searched, never listed.
 */

import { useState, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  GUISE_FIELDS,
  type CharacterSheetStaffRows,
  type GuiseField,
  type StaffCovenantRoleRow,
  type StaffGroupOptions,
  type StaffPersonaRow,
  type StaffTieDirection,
  type StaffTieRow,
  type StaffTieSide,
} from '@/character_sheets/api';
import { useStaffGroupOptions } from '@/character_sheets/queries';
import { asItems } from './staffRowItems';
import { PickAndRun, Section, Select, type Run } from './staffRowPrimitives';

interface GroupProps {
  rows: CharacterSheetStaffRows;
  options: StaffGroupOptions;
  run: Run;
}

const GUISE_LABELS: Record<GuiseField, string> = {
  concept: 'Concept',
  quote: 'Quote',
  never_do: 'Would never do',
  protect: 'Would protect',
  fear: 'Fears',
  background: 'Background',
};

export function GroupFitEditors({
  sheetId,
  rows,
  run,
}: {
  sheetId: number;
  rows: CharacterSheetStaffRows;
  run: Run;
}) {
  const [query, setQuery] = useState('');
  const [searched, setSearched] = useState('');
  const { data: options } = useStaffGroupOptions(sheetId, searched, true);
  if (!options) return null;
  const search = (
    <span className="flex flex-wrap items-center gap-2">
      <Input
        aria-label="Find a character"
        placeholder="Find a character"
        className="h-9 w-56"
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter') setSearched(query.trim());
        }}
      />
      <Button type="button" size="sm" variant="outline" onClick={() => setSearched(query.trim())}>
        Find
      </Button>
    </span>
  );
  return (
    <>
      <PersonasEditor rows={rows} options={options} run={run} />
      <TitlesEditor rows={rows} options={options} run={run} />
      <TiesEditor rows={rows} options={options} run={run} search={search} />
      <CovenantsEditor rows={rows} options={options} run={run} />
      <MentorsEditor rows={rows} options={options} run={run} search={search} />
    </>
  );
}

function PersonasEditor({ rows, run }: GroupProps) {
  const [name, setName] = useState('');
  return (
    <Section title="Identities">
      {rows.personas.map((face) => (
        <PersonaRow key={face.id} face={face} run={run} />
      ))}
      <span className="flex flex-wrap items-center gap-2">
        <Input
          aria-label="New identity name"
          className="h-9 w-56"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
        <Button
          type="button"
          size="sm"
          disabled={!name.trim()}
          onClick={() =>
            run({ path: 'staff-personas', method: 'POST', body: { name: name.trim() } }, () =>
              setName('')
            )
          }
        >
          Add identity
        </Button>
      </span>
    </Section>
  );
}

function PersonaRow({ face, run }: { face: StaffPersonaRow; run: Run }) {
  const [name, setName] = useState(face.name);
  const [guise, setGuise] = useState(face.guise);
  const changed = GUISE_FIELDS.filter((field) => guise[field] !== face.guise[field]);
  return (
    <details className="rounded-md border p-2 text-sm" aria-label={face.name}>
      <summary className="cursor-pointer">
        {face.name} <span className="opacity-60">({face.persona_type})</span>
      </summary>
      <div className="mt-2 flex flex-col gap-2">
        <span className="flex flex-wrap items-center gap-2">
          <Input
            aria-label="Identity name"
            className="h-8 w-56"
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={!name.trim() || name === face.name}
            onClick={() =>
              run({
                path: 'staff-persona',
                method: 'PATCH',
                body: { persona: face.id, name: name.trim() },
              })
            }
          >
            Rename
          </Button>
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() =>
              run({ path: 'staff-persona-remove', method: 'POST', body: { persona: face.id } })
            }
          >
            Remove
          </Button>
        </span>
        {GUISE_FIELDS.map((field) => (
          <Textarea
            key={field}
            aria-label={GUISE_LABELS[field]}
            placeholder={GUISE_LABELS[field]}
            rows={field === 'background' ? 4 : 2}
            value={guise[field]}
            onChange={(event) => setGuise({ ...guise, [field]: event.target.value })}
          />
        ))}
        <span>
          <Button
            type="button"
            size="sm"
            disabled={changed.length === 0}
            onClick={() =>
              run({
                path: 'staff-persona',
                method: 'PATCH',
                body: {
                  persona: face.id,
                  ...Object.fromEntries(changed.map((field) => [field, guise[field]])),
                },
              })
            }
          >
            Save cover bio
          </Button>
        </span>
      </div>
    </details>
  );
}

function TitlesEditor({ rows, options, run }: GroupProps) {
  const [face, setFace] = useState('');
  const [reward, setReward] = useState('');
  const [deed, setDeed] = useState('');
  return (
    <Section title="Titles">
      {rows.titles.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {rows.titles.map((title) => (
            <li key={title.id} className="flex items-center gap-2">
              <span>
                {title.name} <span className="opacity-60">({title.persona_name})</span>
              </span>
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() =>
                  run({ path: 'staff-title-remove', method: 'POST', body: { title: title.id } })
                }
              >
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}
      <span className="flex flex-wrap items-center gap-2">
        <Select label="Face" value={face} onChange={setFace} options={asItems(options.faces)} />
        <Select
          label="Title reward"
          value={reward}
          onChange={(value) => {
            setReward(value);
            setDeed('');
          }}
          options={asItems(options.title_rewards)}
        />
        <Select
          label="Deed"
          value={deed}
          onChange={(value) => {
            setDeed(value);
            setReward('');
          }}
          options={asItems(options.deeds)}
        />
        <Button
          type="button"
          size="sm"
          disabled={!face || (!reward && !deed)}
          onClick={() =>
            run({
              path: 'staff-titles',
              method: 'POST',
              body: {
                persona: Number(face),
                reward: reward ? Number(reward) : null,
                legend_entry: deed ? Number(deed) : null,
              },
            })
          }
        >
          Grant title
        </Button>
      </span>
      {rows.noble_titles.length > 0 && (
        <ul className="text-sm">
          {rows.noble_titles.map((title) => (
            <li key={title.id}>{title.name}</li>
          ))}
        </ul>
      )}
      <PickAndRun
        label="Noble title"
        options={options.noble_titles}
        action="Seat on title"
        onRun={(id) =>
          id !== null && run({ path: 'staff-noble-title', method: 'POST', body: { title: id } })
        }
      />
    </Section>
  );
}

function TiesEditor({ rows, options, run, search }: GroupProps & { search: ReactNode }) {
  const [other, setOther] = useState('');
  const [direction, setDirection] = useState<StaffTieDirection>('toward');
  const [type, setType] = useState('');
  const [awareness, setAwareness] = useState('private');
  return (
    <Section title="Ties">
      {rows.ties.map((tie) => (
        <TieRow key={tie.other} tie={tie} options={options} run={run} />
      ))}
      {search}
      <span className="flex flex-wrap items-center gap-2">
        <Select
          label="Character"
          value={other}
          onChange={setOther}
          options={asItems(options.characters)}
        />
        <Select
          label="Side"
          value={direction}
          onChange={(value) => setDirection(value === 'from' ? 'from' : 'toward')}
          options={[
            { value: 'toward', label: 'This character toward them' },
            { value: 'from', label: 'Them toward this character' },
          ]}
          blank={null}
        />
        <LabelPickers
          options={options}
          type={type}
          setType={setType}
          awareness={awareness}
          setAwareness={setAwareness}
        />
        <Button
          type="button"
          size="sm"
          disabled={!other || !type}
          onClick={() =>
            run({
              path: 'staff-tie-labels',
              method: 'POST',
              body: { other: Number(other), direction, type: Number(type), awareness },
            })
          }
        >
          Declare
        </Button>
      </span>
    </Section>
  );
}

function LabelPickers({
  options,
  type,
  setType,
  awareness,
  setAwareness,
}: {
  options: StaffGroupOptions;
  type: string;
  setType: (value: string) => void;
  awareness: string;
  setAwareness: (value: string) => void;
}) {
  return (
    <>
      <Select
        label="Relationship"
        value={type}
        onChange={setType}
        options={asItems(options.relationship_types)}
      />
      <Select
        label="Awareness"
        value={awareness}
        onChange={setAwareness}
        options={options.awareness.map((choice) => ({ value: choice.value, label: choice.label }))}
        blank={null}
      />
    </>
  );
}

function TieRow({ tie, options, run }: { tie: StaffTieRow; options: StaffGroupOptions; run: Run }) {
  return (
    <div className="rounded-md border p-2 text-sm" aria-label={`Tie with ${tie.other_name}`}>
      <p className="font-medium">{tie.other_name}</p>
      <div className="grid gap-2 sm:grid-cols-2">
        <TieSide
          heading="Toward them"
          side={tie.toward}
          other={tie.other}
          direction="toward"
          options={options}
          run={run}
        />
        <TieSide
          heading="Toward this character"
          side={tie.back}
          other={tie.other}
          direction="from"
          options={options}
          run={run}
        />
      </div>
    </div>
  );
}

function TieSide({
  heading,
  side,
  other,
  direction,
  options,
  run,
}: {
  heading: string;
  side: StaffTieSide | null;
  other: number;
  direction: StaffTieDirection;
  options: StaffGroupOptions;
  run: Run;
}) {
  const [summary, setSummary] = useState(side?.summary ?? '');
  if (!side) {
    return (
      <div aria-label={heading}>
        <p className="opacity-60">{heading}: none</p>
      </div>
    );
  }
  const tiers = [{ id: 0, name: 'None' }, ...options.tiers];
  return (
    <div className="flex flex-col gap-1" aria-label={heading}>
      <p className="opacity-70">{heading}</p>
      {side.labels.map((label) => (
        <span key={label.id} className="flex flex-wrap items-center gap-2">
          <span>
            {label.name}
            {label.waiting && <span className="opacity-60"> (binds at pickup)</span>}
          </span>
          <Select
            label={`${label.name} awareness`}
            value={label.awareness}
            onChange={(value) =>
              run({
                path: 'staff-tie-label',
                method: 'PATCH',
                body: { label: label.id, awareness: value },
              })
            }
            options={options.awareness.map((c) => ({ value: c.value, label: c.label }))}
            blank={null}
          />
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() =>
              run({
                path: 'staff-tie-label',
                method: 'PATCH',
                body: { label: label.id, end: true },
              })
            }
          >
            End
          </Button>
        </span>
      ))}
      <Select
        label={`${heading} tier`}
        value={String(side.tier)}
        onChange={(value) =>
          run({
            path: 'staff-tie',
            method: 'PATCH',
            body: { other, direction, tier: Number(value) },
          })
        }
        options={tiers.map((tier) => ({ value: String(tier.id), label: tier.name }))}
        blank={null}
      />
      <span className="flex items-center gap-2">
        <Input
          aria-label={`${heading} summary`}
          className="h-8"
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
        />
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={summary === side.summary}
          onClick={() =>
            run({ path: 'staff-tie', method: 'PATCH', body: { other, direction, summary } })
          }
        >
          Save
        </Button>
      </span>
    </div>
  );
}

function CovenantsEditor({ rows, options, run }: GroupProps) {
  const [covenant, setCovenant] = useState('');
  const [role, setRole] = useState('');
  const [rank, setRank] = useState('');
  const chosen = options.covenants.find((c) => String(c.id) === covenant);
  return (
    <Section title="Covenants">
      {rows.covenant_roles.map((membership) => (
        <MembershipRow key={membership.id} membership={membership} options={options} run={run} />
      ))}
      <span className="flex flex-wrap items-center gap-2">
        <Select
          label="Covenant"
          value={covenant}
          onChange={(value) => {
            setCovenant(value);
            setRole('');
            setRank('');
          }}
          options={asItems(options.covenants)}
        />
        <Select
          label="Role"
          value={role}
          onChange={setRole}
          options={asItems(chosen?.roles ?? [])}
        />
        <Select
          label="Rank"
          value={rank}
          onChange={setRank}
          options={asItems(chosen?.ranks ?? [])}
          blank="Base rank"
        />
        <Button
          type="button"
          size="sm"
          disabled={!covenant || !role}
          onClick={() =>
            run({
              path: 'staff-covenant-roles',
              method: 'POST',
              body: {
                covenant: Number(covenant),
                covenant_role: Number(role),
                rank: rank ? Number(rank) : null,
              },
            })
          }
        >
          Swear in
        </Button>
      </span>
    </Section>
  );
}

/** One change to a membership: the action takes exactly one per call. */
interface MembershipChange {
  covenant_role?: number;
  rank?: number;
  engaged?: boolean;
  as_secondary?: boolean;
  end?: boolean;
}

function MembershipRow({
  membership,
  options,
  run,
}: {
  membership: StaffCovenantRoleRow;
  options: StaffGroupOptions;
  run: Run;
}) {
  const covenant = options.covenants.find((c) => c.id === membership.covenant);
  const change = (body: MembershipChange) =>
    run({
      path: 'staff-covenant-role',
      method: 'PATCH',
      body: { membership: membership.id, ...body },
    });
  return (
    <span
      className="flex flex-wrap items-center gap-2 text-sm"
      aria-label={membership.covenant_name}
    >
      <span className="w-40 truncate">{membership.covenant_name}</span>
      <Select
        label={`${membership.covenant_name} role`}
        value={String(membership.role)}
        onChange={(value) => change({ covenant_role: Number(value) })}
        options={asItems(covenant?.roles ?? [{ id: membership.role, name: membership.role_name }])}
        blank={null}
      />
      <Select
        label={`${membership.covenant_name} rank`}
        value={String(membership.rank)}
        onChange={(value) => change({ rank: Number(value) })}
        options={asItems(covenant?.ranks ?? [{ id: membership.rank, name: membership.rank_name }])}
        blank={null}
      />
      <Button
        type="button"
        size="sm"
        variant="outline"
        onClick={() =>
          change({
            engaged: !membership.engaged,
            as_secondary: membership.standing === 'minor',
          })
        }
      >
        {membership.engaged ? 'Disengage' : 'Engage'}
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={() => change({ end: true })}>
        End
      </Button>
    </span>
  );
}

function MentorsEditor({ rows, options, run, search }: GroupProps & { search: ReactNode }) {
  const [covenant, setCovenant] = useState('');
  const [other, setOther] = useState('');
  const [asMentor, setAsMentor] = useState('mentor');
  return (
    <Section title="Mentor bonds">
      {rows.mentor_bonds.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {rows.mentor_bonds.map((bond) => (
            <li key={bond.id} className="flex flex-wrap items-center gap-2">
              <span>
                {bond.as_mentor ? 'Mentor of' : 'Sidekick of'} {bond.other_name}, in{' '}
                {bond.covenant_name}
              </span>
              {bond.warning && <span className="text-amber-700">{bond.warning}</span>}
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() =>
                  run({ path: 'staff-mentor-bond-end', method: 'POST', body: { bond: bond.id } })
                }
              >
                End
              </Button>
            </li>
          ))}
        </ul>
      )}
      {search}
      <span className="flex flex-wrap items-center gap-2">
        <Select
          label="Bond covenant"
          value={covenant}
          onChange={setCovenant}
          options={asItems(options.covenants)}
        />
        <Select
          label="Bond character"
          value={other}
          onChange={setOther}
          options={asItems(options.characters)}
        />
        <Select
          label="This character is"
          value={asMentor}
          onChange={setAsMentor}
          options={[
            { value: 'mentor', label: 'The mentor' },
            { value: 'sidekick', label: 'The sidekick' },
          ]}
          blank={null}
        />
        <Button
          type="button"
          size="sm"
          disabled={!covenant || !other}
          onClick={() =>
            run({
              path: 'staff-mentor-bonds',
              method: 'POST',
              body: {
                covenant: Number(covenant),
                other: Number(other),
                as_mentor: asMentor === 'mentor',
              },
            })
          }
        >
          Bond
        </Button>
      </span>
    </Section>
  );
}
