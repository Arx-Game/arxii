/**
 * Family path section (#3617).
 *
 * Rendered below the Upbringing's prompts. When the Upbringing allows more
 * than one family path, a path picker PATCHes family_path; then the
 * path-specific UI: name a new family, claim a staff-authored one, or the
 * tarot naming ritual for no family at all.
 */

import { useEffect, useState } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { useUpdateDraft } from '../../queries';
import { allowedFamilyPaths, Stage } from '../../types';
import type {
  CGExplanations,
  CharacterDraft,
  Family,
  FamilyPath,
  OriginTemplate,
} from '../../types';
import {
  FamilyCard,
  FamilyNamePreview,
  HouseFoundingPanel,
  InventedParentsCard,
  KinSlotPicker,
  TarotNamingRitual,
} from '../LineageStage';

interface FamilyPathSectionProps {
  draft: CharacterDraft;
  template: OriginTemplate;
  path: FamilyPath | '';
  families: Family[] | undefined;
  familiesLoading: boolean;
  copy: CGExplanations | undefined;
}

const PATH_LABELS: Record<FamilyPath, string> = {
  claimed: 'Claim a family',
  named: 'Name a new family',
  none: 'No family',
};

/** Server-side collision authority (validators.get_lineage_errors) for this stage. */
function familyErrorsFor(draft: CharacterDraft): string[] {
  return (draft.stage_errors[Stage.LINEAGE] ?? []).filter((error) =>
    error.toLowerCase().includes('family')
  );
}

export function FamilyPathSection({
  draft,
  template,
  path,
  families,
  familiesLoading,
  copy,
}: FamilyPathSectionProps) {
  const updateDraft = useUpdateDraft();
  const allowed = allowedFamilyPaths(template);
  const showPathPicker = allowed.length > 1;

  const setPath = (next: string) =>
    updateDraft.mutate({ draftId: draft.id, data: { family_path: next as FamilyPath } });

  const showInventedParents =
    (path === 'named' || path === 'claimed') &&
    !draft.claimed_kin_slot &&
    !draft.claimed_kin_pool &&
    !draft.defer_parents;

  return (
    <section className="space-y-6">
      <div>
        <h3 className="theme-heading text-lg font-semibold">
          {copy?.family_path_heading ?? 'Your Family'}
        </h3>
      </div>

      {showPathPicker && (
        <RadioGroup
          value={path || undefined}
          onValueChange={setPath}
          className="flex flex-wrap gap-6"
        >
          {allowed.map((option) => (
            <div key={option} className="flex items-center gap-2">
              <RadioGroupItem value={option} id={`family-path-${option}`} />
              <Label htmlFor={`family-path-${option}`}>{PATH_LABELS[option]}</Label>
            </div>
          ))}
        </RadioGroup>
      )}

      {path === 'named' && <NamedFamilyPath draft={draft} />}

      {path === 'claimed' && (
        <ClaimedFamilyPath
          draft={draft}
          template={template}
          families={families}
          familiesLoading={familiesLoading}
        />
      )}

      {path === 'none' && <TarotNamingRitual draft={draft} />}

      {showInventedParents && <InventedParentsCard draft={draft} />}
    </section>
  );
}

function NamedFamilyPath({ draft }: { draft: CharacterDraft }) {
  const updateDraft = useUpdateDraft();
  const [name, setName] = useState(draft.draft_data.new_family_name ?? '');

  useEffect(() => {
    setName(draft.draft_data.new_family_name ?? '');
  }, [draft.draft_data.new_family_name]);

  const commit = () => {
    if ((draft.draft_data.new_family_name ?? '') === name.trim()) return;
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { new_family_name: name.trim() } },
    });
  };

  return (
    <div className="max-w-md space-y-2">
      <Label htmlFor="new-family-name">Family name</Label>
      <Input
        id="new-family-name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onBlur={commit}
        placeholder="Name your family"
      />
      {familyErrorsFor(draft).map((error) => (
        <p key={error} className="text-sm text-destructive">
          {error}
        </p>
      ))}
      {name && (
        <FamilyNamePreview
          firstName={draft.draft_data.first_name}
          family={{ name, born_particle: '', taken_in_particle: '' }}
        />
      )}
    </div>
  );
}

interface ClaimedFamilyPathProps {
  draft: CharacterDraft;
  template: OriginTemplate;
  families: Family[] | undefined;
  familiesLoading: boolean;
}

function ClaimedFamilyPath({ draft, template, families, familiesLoading }: ClaimedFamilyPathProps) {
  const updateDraft = useUpdateDraft();

  const handleFamilySelect = (familyId: string) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: { family_id: parseInt(familyId, 10) },
    });
  };

  const houseFamilies = families?.filter((f) => f.kind.styles_as_house) ?? [];
  const otherFamilies = families?.filter((f) => !f.kind.styles_as_house) ?? [];
  const showHouseFounding =
    !draft.family && (template.claimable_kind_ids.length === 0 || houseFamilies.length > 0);

  return (
    <div className="space-y-4">
      {familiesLoading ? (
        <div className="h-10 animate-pulse rounded bg-muted" />
      ) : (
        <div className="space-y-6">
          {houseFamilies.length > 0 && (
            <div className="space-y-2">
              <Label className="text-sm font-medium text-muted-foreground">Houses</Label>
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {houseFamilies.map((family) => (
                  <FamilyCard
                    key={family.id}
                    family={family}
                    isSelected={draft.family?.id === family.id}
                    onSelect={() => handleFamilySelect(family.id.toString())}
                  />
                ))}
              </div>
            </div>
          )}

          {otherFamilies.length > 0 && (
            <div className="space-y-2">
              <Label className="text-sm font-medium text-muted-foreground">Families</Label>
              <Select value={draft.family?.id?.toString() ?? ''} onValueChange={handleFamilySelect}>
                <SelectTrigger className="w-full max-w-xs">
                  <SelectValue placeholder="Select a family" />
                </SelectTrigger>
                <SelectContent>
                  {otherFamilies.map((family) => (
                    <SelectItem key={family.id} value={family.id.toString()}>
                      {family.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {(families?.length ?? 0) === 0 && (
            <p className="text-sm text-muted-foreground">
              No families are open to this upbringing. Contact staff.
            </p>
          )}
        </div>
      )}

      {familyErrorsFor(draft).map((error) => (
        <p key={error} className="text-sm text-destructive">
          {error}
        </p>
      ))}

      {draft.family && (
        <FamilyNamePreview
          firstName={draft.draft_data.first_name}
          family={families?.find((f) => f.id === draft.family?.id)}
        />
      )}

      {draft.family && <KinSlotPicker draft={draft} familyId={draft.family.id} />}

      {showHouseFounding && <HouseFoundingPanel draft={draft} />}
    </div>
  );
}
