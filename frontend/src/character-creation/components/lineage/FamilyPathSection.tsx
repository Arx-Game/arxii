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
import { useUpdateDraft, useVacancies } from '../../queries';
import { allowedFamilyPaths, resolveFamilyTemplate, Stage } from '../../types';
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
import { ChoiceRow, Field } from '../../folio';
import { FamilyTemplateForm } from './FamilyTemplateForm';
import { InheritedFactsPanel } from './InheritedFactsPanel';
import { ServicePanel } from './ServicePanel';
import { VacancyPicker } from './VacancyPicker';

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
  const { data: vacancies } = useVacancies(draft.id);
  const kinVacancyChosen =
    vacancies?.some((v) => v.id === draft.selected_vacancy && v.basis === 'kin') ?? false;

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

      {path === 'named' && <NamedFamilyPath draft={draft} template={template} copy={copy} />}

      {path === 'claimed' && (
        <ClaimedFamilyPath
          draft={draft}
          template={template}
          families={families}
          familiesLoading={familiesLoading}
          copy={copy}
        />
      )}

      {path === 'none' && <TarotNamingRitual draft={draft} />}

      {path !== '' && !kinVacancyChosen && (
        <ServicePanel draft={draft} heading={copy?.service_heading ?? 'Service'} />
      )}

      {showInventedParents && <InventedParentsCard draft={draft} />}
    </section>
  );
}

function NamedFamilyPath({
  draft,
  template,
  copy,
}: {
  draft: CharacterDraft;
  template: OriginTemplate;
  copy: CGExplanations | undefined;
}) {
  const updateDraft = useUpdateDraft();
  const [name, setName] = useState(draft.draft_data.new_family_name ?? '');
  const offered = template.family_templates;
  const familyTemplate = resolveFamilyTemplate(draft);
  const picks = draft.draft_data.family_aspect_picks ?? {};

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

  const toggleAspect = (definitionId: number, optionId: number, maxPicks: number) => {
    const current = picks[String(definitionId)] ?? [];
    let next: number[];
    if (current.includes(optionId)) next = current.filter((id) => id !== optionId);
    else if (maxPicks === 1) next = [optionId];
    else if (current.length >= maxPicks) return;
    else next = [...current, optionId];
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { family_aspect_picks: { ...picks, [definitionId]: next } } },
    });
  };

  return (
    <div className="max-w-xl space-y-4">
      {offered.length > 1 && (
        <ChoiceRow
          label={copy?.family_template_heading ?? 'Family template'}
          options={offered.map((t) => ({ value: t.id, label: t.name }))}
          value={familyTemplate?.id ?? null}
          clearable
          onChange={(value) =>
            updateDraft.mutate({
              draftId: draft.id,
              data: { draft_data: { family_template_id: value } },
            })
          }
        />
      )}
      <Field id="new-family-name" label="Family name">
        <Input
          id="new-family-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          onBlur={commit}
          placeholder="Name your family"
        />
      </Field>
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
      {familyTemplate && (
        <FamilyTemplateForm
          template={familyTemplate}
          picks={Object.fromEntries(Object.entries(picks).map(([k, v]) => [Number(k), v]))}
          onToggle={toggleAspect}
        />
      )}
      {familyTemplate && familyTemplate.served_house_choices.length > 0 && (
        <ChoiceRow
          label={copy?.served_house_heading ?? 'Whom did your family serve'}
          options={familyTemplate.served_house_choices.map((h) => ({ value: h.id, label: h.name }))}
          value={draft.served_house}
          onChange={(value) =>
            updateDraft.mutate({ draftId: draft.id, data: { served_house_id: value } })
          }
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
  copy: CGExplanations | undefined;
}

function ClaimedFamilyPath({
  draft,
  template,
  families,
  familiesLoading,
  copy,
}: ClaimedFamilyPathProps) {
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

      {draft.family && (
        <InheritedFactsPanel family={families?.find((f) => f.id === draft.family?.id)} />
      )}
      {draft.family && (
        <ClaimVacancies draft={draft} organizationFamilyId={draft.family.id} copy={copy} />
      )}

      {showHouseFounding && <HouseFoundingPanel draft={draft} />}
    </div>
  );
}

function ClaimVacancies({
  draft,
  organizationFamilyId,
  copy,
}: {
  draft: CharacterDraft;
  organizationFamilyId: number;
  copy: CGExplanations | undefined;
}) {
  const updateDraft = useUpdateDraft();
  const { data } = useVacancies(draft.id);
  const kin = (data ?? []).filter(
    (v) => v.basis === 'kin' && v.organization.family?.id === organizationFamilyId
  );
  if (kin.length === 0) return <KinSlotPicker draft={draft} familyId={organizationFamilyId} />;
  return (
    <div className="space-y-2">
      <Label className="text-sm font-medium text-muted-foreground">
        {copy?.vacancy_heading ?? 'Your place in the family'}
      </Label>
      <VacancyPicker
        draft={draft}
        vacancies={kin}
        onPick={(id) =>
          updateDraft.mutate({ draftId: draft.id, data: { selected_vacancy_id: id } })
        }
      />
    </div>
  );
}
