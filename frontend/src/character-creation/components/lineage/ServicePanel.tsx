/** Retainer openings at staff houses, available on any family path (#3648). */

import { Label } from '@/components/ui/label';
import { useUpdateDraft, useVacancies } from '../../queries';
import type { CharacterDraft, Vacancy } from '../../types';
import { VacancyPicker } from './VacancyPicker';

export function ServicePanel({ draft, heading }: { draft: CharacterDraft; heading: string }) {
  const updateDraft = useUpdateDraft();
  const { data } = useVacancies(draft.id);
  const ownFamilyId = draft.family?.id ?? null;
  const retainer = (data ?? []).filter(
    (v) => v.basis === 'retainer' && v.organization.family?.id !== ownFamilyId
  );
  if (retainer.length === 0) return null;
  const groups = new Map<string, Vacancy[]>();
  for (const vacancy of retainer) {
    const list = groups.get(vacancy.organization.name) ?? [];
    list.push(vacancy);
    groups.set(vacancy.organization.name, list);
  }
  return (
    <section className="space-y-4">
      <h3 className="theme-heading text-lg font-semibold">{heading}</h3>
      {[...groups.entries()].map(([orgName, vacancies]) => (
        <div key={orgName} className="space-y-2">
          <Label className="text-sm font-medium text-muted-foreground">{orgName}</Label>
          <VacancyPicker
            draft={draft}
            vacancies={vacancies}
            onPick={(id) =>
              updateDraft.mutate({ draftId: draft.id, data: { selected_vacancy_id: id } })
            }
          />
        </div>
      ))}
    </section>
  );
}
