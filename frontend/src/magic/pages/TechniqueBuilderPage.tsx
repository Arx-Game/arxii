/**
 * TechniqueBuilderPage — page for authoring a new Technique.
 *
 * Route: /techniques/build (ProtectedRoute)
 *
 * Loads all lookup lists required by TechniqueBuilderForm:
 *   - gifts: reused from character-creation's getTechniqueGifts (GET /api/magic/gifts/)
 *   - styles: reused from useTechniqueStyles (GET /api/magic/styles/)
 *   - effectTypes: reused from useEffectTypes (GET /api/magic/effect-types/)
 *   - capabilities: GET /api/conditions/capabilities/
 *   - damageTypes: GET /api/conditions/damage-types/
 *   - conditions: GET /api/conditions/templates/
 *
 * isStaff is read from the Redux account store (same pattern as CharacterCreationPage).
 */

import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '@/evennia_replacements/api';
import { useAccount } from '@/store/hooks';
import { Skeleton } from '@/components/ui/skeleton';
import { useTechniqueStyles, useEffectTypes } from '@/character-creation/queries';
import { getGifts } from '@/character-creation/api';
import type { components } from '@/generated/api';
import { TechniqueBuilderForm } from '../components/TechniqueBuilderForm';
import type { CapabilityType, DamageType } from '../components/TechniquePayloadEditors';

// ---------------------------------------------------------------------------
// Inline fetch helpers for conditions-module lookup lists
// ---------------------------------------------------------------------------

type ConditionTemplate = components['schemas']['ConditionTemplate'];

async function getCapabilities(): Promise<CapabilityType[]> {
  const res = await apiFetch('/api/conditions/capabilities/');
  if (!res.ok) throw new Error('Failed to load capabilities');
  return res.json() as Promise<CapabilityType[]>;
}

async function getDamageTypes(): Promise<DamageType[]> {
  const res = await apiFetch('/api/conditions/damage-types/');
  if (!res.ok) throw new Error('Failed to load damage types');
  return res.json() as Promise<DamageType[]>;
}

async function getConditionTemplates(): Promise<ConditionTemplate[]> {
  const res = await apiFetch('/api/conditions/templates/');
  if (!res.ok) throw new Error('Failed to load condition templates');
  // The endpoint may be paginated; handle both paginated and bare-array responses.
  const data = (await res.json()) as { results?: ConditionTemplate[] } | ConditionTemplate[];
  if (Array.isArray(data)) return data;
  return (data as { results?: ConditionTemplate[] }).results ?? [];
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export function TechniqueBuilderPage() {
  const navigate = useNavigate();
  const account = useAccount();
  const isStaff = account?.is_staff ?? false;

  // Lookup lists
  const { data: giftsData = [], isLoading: giftsLoading } = useQuery({
    queryKey: ['magic', 'gifts', 'list'],
    queryFn: () => getGifts(),
  });
  const { data: stylesData = [], isLoading: stylesLoading } = useTechniqueStyles();
  const { data: effectTypesData = [], isLoading: effectTypesLoading } = useEffectTypes();
  const { data: capabilitiesData = [], isLoading: capabilitiesLoading } = useQuery({
    queryKey: ['conditions', 'capabilities'],
    queryFn: getCapabilities,
    staleTime: 60_000,
  });
  const { data: damageTypesData = [], isLoading: damageTypesLoading } = useQuery({
    queryKey: ['conditions', 'damage-types'],
    queryFn: getDamageTypes,
    staleTime: 60_000,
  });
  const { data: conditionsData = [], isLoading: conditionsLoading } = useQuery({
    queryKey: ['conditions', 'templates'],
    queryFn: getConditionTemplates,
    staleTime: 60_000,
  });

  const isLoading =
    giftsLoading ||
    stylesLoading ||
    effectTypesLoading ||
    capabilitiesLoading ||
    damageTypesLoading ||
    conditionsLoading;

  if (isLoading) {
    return (
      <div className="container mx-auto max-w-3xl space-y-4 px-4 py-8">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  // Map gifts to minimal {id, name} shape (gift_detail.id = gift id in CharacterGift,
  // but here getTechniqueGifts returns Gift directly with id + name).
  const gifts = giftsData.map((g) => ({ id: g.id, name: g.name }));
  const styles = stylesData.map((s) => ({ id: s.id, name: s.name }));
  const effectTypes = effectTypesData.map((et) => ({ id: et.id, name: et.name }));
  const conditions = conditionsData.map((c) => ({ id: c.id, name: c.name }));

  return (
    <div className="container mx-auto max-w-3xl px-4 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight">Author a Technique</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {isStaff
            ? 'Staff mode — budget is advisory. Over-budget designs may still be saved.'
            : 'Design a new technique. Your design must fit within the tier budget to submit.'}
        </p>
      </div>

      <TechniqueBuilderForm
        mode={isStaff ? 'staff' : 'player'}
        gifts={gifts}
        styles={styles}
        effectTypes={effectTypes}
        capabilities={capabilitiesData}
        damageTypes={damageTypesData}
        conditions={conditions}
        onSuccess={() => navigate('/threads')}
      />
    </div>
  );
}
