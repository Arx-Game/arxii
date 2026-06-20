import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Label } from '@/components/ui/label';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import MyTenureSelect from '@/components/MyTenureSelect';
import { CategoryConsentRow } from '../components/CategoryConsentRow';
import {
  useConsentCategories,
  useConsentPreference,
  useCreatePreference,
  useUpdatePreference,
  useCategoryRules,
} from '../queries';

// ---------------------------------------------------------------------------
// Inner — renders once a tenureId is selected
// ---------------------------------------------------------------------------

interface ConsentPanelProps {
  tenureId: number;
}

function ConsentPanel({ tenureId }: ConsentPanelProps) {
  const { data: preference, isLoading: prefLoading } = useConsentPreference(tenureId);
  const { data: categories, isLoading: catLoading } = useConsentCategories();
  const { data: rulesData, isLoading: rulesLoading } = useCategoryRules(tenureId);

  const createPreference = useCreatePreference();
  const updatePreference = useUpdatePreference();

  // -------------------------------------------------------------------------
  // Ensure a persisted preference row exists before mutating
  // -------------------------------------------------------------------------

  async function ensurePreference(): Promise<number> {
    if (preference?.id) {
      return preference.id;
    }
    // The for-tenure endpoint returned a synthesised default without an id.
    const created = await createPreference.mutateAsync({ tenure: tenureId });
    return created.id;
  }

  async function handleSwitchChange(checked: boolean) {
    const id = await ensurePreference();
    updatePreference.mutate({ id, body: { allow_social_actions: checked } });
  }

  // -------------------------------------------------------------------------
  // Loading states
  // -------------------------------------------------------------------------

  if (prefLoading || catLoading) {
    return (
      <div className="mt-4 space-y-4">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  const allowSocial = preference?.allow_social_actions ?? true;
  const allCategories = categories?.results ?? [];
  const rules = rulesData?.results ?? [];
  const preferenceId = preference?.id;

  return (
    <div className="mt-4 space-y-4">
      {/* Master switch */}
      <Card>
        <CardHeader>
          <CardTitle>Social targeting</CardTitle>
          <CardDescription>
            Controls whether this character can be targeted by social actions from other players.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between">
            <Label htmlFor="allow-social">Pause all social targeting</Label>
            <Switch
              id="allow-social"
              checked={!allowSocial}
              onCheckedChange={(checked) => handleSwitchChange(!checked)}
              disabled={createPreference.isPending || updatePreference.isPending}
            />
          </div>
        </CardContent>
      </Card>

      {/* Per-category rules — only shown when we have a persisted preference */}
      {preferenceId && allCategories.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Category permissions</CardTitle>
            <CardDescription>
              Fine-tune which players can target this character for each type of social action.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {rulesLoading ? (
              <>
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </>
            ) : (
              allCategories.map((category) => {
                const rule = rules.find((r) => r.category === category.id);
                return (
                  <CategoryConsentRow
                    key={category.id}
                    tenureId={tenureId}
                    preferenceId={preferenceId}
                    category={category}
                    rule={rule}
                  />
                );
              })
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page root
// ---------------------------------------------------------------------------

function PrivacyPageInner() {
  const [selectedTenureId, setSelectedTenureId] = useState<number | null>(null);

  return (
    <div className="mt-4 space-y-4">
      <MyTenureSelect value={selectedTenureId} onChange={setSelectedTenureId} label="Character" />
      {selectedTenureId !== null && <ConsentPanel tenureId={selectedTenureId} />}
    </div>
  );
}

export function PrivacyPage() {
  return (
    <ErrorBoundary>
      <PrivacyPageInner />
    </ErrorBoundary>
  );
}
