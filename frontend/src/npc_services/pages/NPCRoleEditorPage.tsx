/**
 * NPC Role editor (#728 — Mission Studio).
 *
 * Drill-down editor for one NPCRole: its descriptive/rapport fields plus the
 * service offers it holds (mission + permit kinds). Mission offers expose the
 * MissionOfferDetails panel (template, weight, cooldown, requirements rule).
 * Replaces the deleted GiverEditorPage against the unified npc-services surface.
 */
import { Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { StudioBreadcrumb } from '@/missions/components/StudioBreadcrumb';
import {
  PredicateBuilder,
  coercePredicate,
  validatePredicate,
  type PredicateNode,
} from '@/missions/components/PredicateBuilder';
import { useMissionTemplates, usePredicateLeaves } from '@/missions/queries';
import { useBuildingKindsQuery } from '@/buildings/queries';
import { useQuery } from '@tanstack/react-query';

import { ApiValidationError, flattenErrorMessage, listAreasFlat } from '../api';
import {
  useCreateMissionDetails,
  useCreateOffer,
  useCreatePermitDetails,
  useDeleteOffer,
  useDeleteRole,
  useMissionDetailsForRole,
  useOffersForRole,
  usePatchMissionDetails,
  usePatchOffer,
  usePatchPermitDetails,
  usePatchRole,
  usePermitDetailsForRole,
  useRole,
} from '../queries';
import type { MissionOfferDetails, NPCServiceOffer, PermitOfferDetails } from '../types';

const EMPTY_RULE: PredicateNode = {};

function errText(err: unknown, fallback: string): string {
  return err instanceof ApiValidationError ? flattenErrorMessage(err.fieldErrors) : fallback;
}

function numOrNull(raw: string): number | null {
  const t = raw.trim();
  if (t === '') return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export function NPCRoleEditorPage() {
  const { id } = useParams<{ id: string }>();
  const roleId = id ? Number(id) : null;
  const { data: role, isLoading } = useRole(roleId);

  if (isLoading || !role || roleId === null) {
    return (
      <div className="flex justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-3xl space-y-6 py-6">
      <StudioBreadcrumb
        crumbs={[{ label: 'NPC Roles', to: '/staff/npc-services/roles' }, { label: role.name }]}
      />
      <RoleFieldsCard roleId={roleId} />
      <OffersSection roleId={roleId} />
    </div>
  );
}

function RoleFieldsCard({ roleId }: { roleId: number }) {
  const { data: role } = useRole(roleId);
  const patch = usePatchRole();
  const del = useDeleteRole();
  const navigate = useNavigate();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [template, setTemplate] = useState('');
  const [rapport, setRapport] = useState('');
  const [faction, setFaction] = useState('');
  const [isActive, setIsActive] = useState(true);

  useEffect(() => {
    if (!role) return;
    setName(role.name ?? '');
    setDescription(role.description ?? '');
    setTemplate(role.default_description_template ?? '');
    setRapport(role.default_rapport_starting_value?.toString() ?? '');
    setFaction(role.faction_affiliation?.toString() ?? '');
    setIsActive(role.is_active ?? true);
  }, [role]);

  const save = () => {
    patch.mutate({
      id: roleId,
      body: {
        name: name.trim(),
        description,
        default_description_template: template,
        default_rapport_starting_value: numOrNull(rapport) ?? 0,
        faction_affiliation: numOrNull(faction),
        is_active: isActive,
      },
    });
  };

  const remove = () => {
    if (!window.confirm('Delete this role and all its offers?')) return;
    del.mutate(roleId, { onSuccess: () => navigate('/staff/npc-services/roles') });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Role</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Field label="Name">
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Description">
          <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
        </Field>
        <Field label="Default description template">
          <Textarea value={template} onChange={(e) => setTemplate(e.target.value)} rows={2} />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Default rapport">
            <Input type="number" value={rapport} onChange={(e) => setRapport(e.target.value)} />
          </Field>
          <Field label="Faction affiliation (id)">
            <Input
              type="number"
              value={faction}
              onChange={(e) => setFaction(e.target.value)}
              placeholder="optional"
            />
          </Field>
        </div>
        <label className="flex items-center gap-2 text-sm">
          <Switch checked={isActive} onCheckedChange={setIsActive} />
          Active (offered to players)
        </label>
        {patch.isError && (
          <p className="text-sm text-destructive">{errText(patch.error, 'Could not save.')}</p>
        )}
        <div className="flex justify-between">
          <Button size="sm" onClick={save} disabled={!name.trim() || patch.isPending}>
            {patch.isPending ? 'Saving…' : 'Save role'}
          </Button>
          <Button size="sm" variant="destructive" onClick={remove} disabled={del.isPending}>
            Delete
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function OffersSection({ roleId }: { roleId: number }) {
  const { data: offersData, isLoading } = useOffersForRole(roleId);
  const { data: detailsData } = useMissionDetailsForRole(roleId);
  const { data: permitDetailsData } = usePermitDetailsForRole(roleId);
  const offers = offersData?.results ?? [];
  const detailsByOffer = new Map<number, MissionOfferDetails>();
  for (const d of detailsData?.results ?? []) {
    if (typeof d.offer === 'number') detailsByOffer.set(d.offer, d);
  }
  const permitDetailsByOffer = new Map<number, PermitOfferDetails>();
  for (const d of permitDetailsData?.results ?? []) {
    if (typeof d.offer === 'number') permitDetailsByOffer.set(d.offer, d);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Offers</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="flex justify-center py-4">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : offers.length === 0 ? (
          <p className="text-sm text-muted-foreground">No offers yet.</p>
        ) : (
          offers.map((offer) => (
            <OfferCard
              key={offer.id}
              roleId={roleId}
              offer={offer}
              details={detailsByOffer.get(offer.id) ?? null}
              permitDetails={permitDetailsByOffer.get(offer.id) ?? null}
            />
          ))
        )}
        <AddOfferForm roleId={roleId} />
      </CardContent>
    </Card>
  );
}

function OfferCard({
  roleId,
  offer,
  details,
  permitDetails,
}: {
  roleId: number;
  offer: NPCServiceOffer;
  details: MissionOfferDetails | null;
  permitDetails: PermitOfferDetails | null;
}) {
  const patchOffer = usePatchOffer(roleId);
  const patchDetails = usePatchMissionDetails(roleId);
  const del = useDeleteOffer(roleId);
  const leavesQuery = usePredicateLeaves();
  const leaves = leavesQuery.data ?? [];

  const [label, setLabel] = useState(offer.label ?? '');
  const [drawMode, setDrawMode] = useState(offer.draw_mode ?? 'menu');
  const [rapportReq, setRapportReq] = useState(offer.rapport_requirement?.toString() ?? '');
  const [isFinal, setIsFinal] = useState(offer.is_final ?? false);
  const [rule, setRule] = useState<PredicateNode>(
    (offer.eligibility_rule as PredicateNode) ?? EMPTY_RULE
  );
  const [weight, setWeight] = useState(details?.weight?.toString() ?? '');
  const [reqOverride, setReqOverride] = useState<PredicateNode>(
    (details?.requirements_override as PredicateNode) ?? EMPTY_RULE
  );
  const [roleCooldown, setRoleCooldown] = useState(details?.role_cooldown_duration ?? '');
  const [drawPriority, setDrawPriority] = useState(details?.draw_priority?.toString() ?? '');
  const [rapportDeltaSuccess, setRapportDeltaSuccess] = useState(
    offer.rapport_delta_success?.toString() ?? ''
  );
  const [rapportDeltaFailure, setRapportDeltaFailure] = useState(
    offer.rapport_delta_failure?.toString() ?? ''
  );
  const [checkType, setCheckType] = useState(offer.check_type?.toString() ?? '');
  const [checkDifficulty, setCheckDifficulty] = useState(offer.check_difficulty?.toString() ?? '');
  const [offerCooldown, setOfferCooldown] = useState(offer.cooldown ?? '');

  // Only validate/coerce once the predicate-leaf catalog has loaded — otherwise
  // every leaf reads as "unknown" and a valid persisted rule becomes un-saveable.
  const ruleErrors = leavesQuery.isSuccess ? validatePredicate(rule, leaves) : [];
  const reqErrors = leavesQuery.isSuccess ? validatePredicate(reqOverride, leaves) : [];

  const save = () => {
    if (ruleErrors.length > 0 || reqErrors.length > 0) return;
    patchOffer.mutate({
      id: offer.id,
      body: {
        label: label.trim(),
        draw_mode: drawMode,
        rapport_requirement: numOrNull(rapportReq) ?? 0,
        is_final: isFinal,
        rapport_delta_success: numOrNull(rapportDeltaSuccess) ?? 0,
        rapport_delta_failure: numOrNull(rapportDeltaFailure) ?? 0,
        check_type: numOrNull(checkType),
        check_difficulty: numOrNull(checkDifficulty) ?? 0,
        cooldown: offerCooldown.trim() || null,
        eligibility_rule: leavesQuery.isSuccess ? coercePredicate(rule, leaves) : rule,
      },
    });
    if (offer.kind === 'mission' && details) {
      // Null weight / cooldown intentionally fall back to the MissionTemplate.
      patchDetails.mutate({
        id: details.id,
        body: {
          weight: numOrNull(weight),
          requirements_override: leavesQuery.isSuccess
            ? coercePredicate(reqOverride, leaves)
            : reqOverride,
          role_cooldown_duration: roleCooldown.trim() || null,
          draw_priority: numOrNull(drawPriority) ?? 0,
        },
      });
    }
  };

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="flex items-center justify-between">
        <Badge variant={offer.kind === 'mission' ? 'default' : 'secondary'}>{offer.kind}</Badge>
        <Button
          size="sm"
          variant="ghost"
          className="text-destructive"
          onClick={() => del.mutate(offer.id)}
        >
          Remove
        </Button>
      </div>

      <Field label="Label">
        <Input value={label} onChange={(e) => setLabel(e.target.value)} />
      </Field>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Draw mode">
          <Select value={drawMode} onValueChange={(v) => setDrawMode(v as 'menu' | 'pool')}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="menu">Menu</SelectItem>
              <SelectItem value="pool">Pool</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field label="Rapport requirement">
          <Input type="number" value={rapportReq} onChange={(e) => setRapportReq(e.target.value)} />
        </Field>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <Switch checked={isFinal} onCheckedChange={setIsFinal} />
        Final action (ends the interaction)
      </label>

      <div className="space-y-3 rounded-md border border-dashed p-3">
        <p className="text-xs font-medium text-muted-foreground">
          Rapport &amp; check (non-final actions)
        </p>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Rapport Δ on success">
            <Input
              type="number"
              value={rapportDeltaSuccess}
              onChange={(e) => setRapportDeltaSuccess(e.target.value)}
            />
          </Field>
          <Field label="Rapport Δ on failure">
            <Input
              type="number"
              value={rapportDeltaFailure}
              onChange={(e) => setRapportDeltaFailure(e.target.value)}
            />
          </Field>
          <Field label="Check type (id)">
            <Input
              type="number"
              value={checkType}
              onChange={(e) => setCheckType(e.target.value)}
              placeholder="optional — gates a perform_check"
            />
          </Field>
          <Field label="Check difficulty">
            <Input
              type="number"
              value={checkDifficulty}
              onChange={(e) => setCheckDifficulty(e.target.value)}
            />
          </Field>
        </div>
        <Field label="Offer cooldown (e.g. 7 00:00:00)">
          <Input
            value={offerCooldown}
            onChange={(e) => setOfferCooldown(e.target.value)}
            placeholder="blank → no cooldown"
          />
        </Field>
      </div>

      {offer.kind === 'mission' &&
        (details ? (
          <div className="space-y-3 rounded-md border border-dashed p-3">
            <p className="text-xs font-medium text-muted-foreground">Mission details</p>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Weight (POOL draw)">
                <Input
                  type="number"
                  value={weight}
                  onChange={(e) => setWeight(e.target.value)}
                  placeholder="blank → template default"
                />
              </Field>
              <Field label="Draw priority">
                <Input
                  type="number"
                  value={drawPriority}
                  onChange={(e) => setDrawPriority(e.target.value)}
                  placeholder="0 = general pool"
                />
              </Field>
            </div>
            <Field label="Role cooldown (e.g. 7 00:00:00)">
              <Input
                value={roleCooldown}
                onChange={(e) => setRoleCooldown(e.target.value)}
                placeholder="blank → template cooldown"
              />
            </Field>
            <PredicateBuilder
              label="Requirements override"
              value={reqOverride}
              onChange={setReqOverride}
            />
            {reqErrors.length > 0 && <p className="text-sm text-destructive">{reqErrors[0]}</p>}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">
            This mission offer has no MissionOfferDetails row yet — pick a template via the
            add-offer flow.
          </p>
        ))}

      {offer.kind === 'permit' && (
        <PermitDetailsPanel roleId={roleId} offerId={offer.id} details={permitDetails} />
      )}

      <PredicateBuilder label="Eligibility rule" value={rule} onChange={setRule} />
      {ruleErrors.length > 0 && <p className="text-sm text-destructive">{ruleErrors[0]}</p>}

      {(patchOffer.isError || patchDetails.isError) && (
        <p className="text-sm text-destructive">
          {errText(patchOffer.error ?? patchDetails.error, 'Could not save the offer.')}
        </p>
      )}
      <Button
        size="sm"
        onClick={save}
        disabled={
          ruleErrors.length > 0 || reqErrors.length > 0 || patchOffer.isPending || !label.trim()
        }
      >
        {patchOffer.isPending ? 'Saving…' : 'Save offer'}
      </Button>
    </div>
  );
}

function PermitDetailsPanel({
  roleId,
  offerId,
  details,
}: {
  roleId: number;
  offerId: number;
  details: PermitOfferDetails | null;
}) {
  const buildingKinds = useBuildingKindsQuery();
  const areas = useQuery({ queryKey: ['areas', 'flat'], queryFn: listAreasFlat });
  const createDetails = useCreatePermitDetails(roleId);
  const patchDetails = usePatchPermitDetails(roleId);

  const [buildingKind, setBuildingKind] = useState(details?.building_kind?.toString() ?? '');
  const [wards, setWards] = useState<Set<number>>(
    () => new Set((details?.default_approved_wards ?? []) as number[])
  );
  const [maxSize, setMaxSize] = useState(details?.default_max_target_size?.toString() ?? '');
  const [cost, setCost] = useState(details?.permit_cost_currency?.toString() ?? '');

  const toggleWard = (id: number) => {
    setWards((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const save = () => {
    const body = {
      building_kind: numOrNull(buildingKind),
      default_approved_wards: [...wards],
      default_max_target_size: numOrNull(maxSize) ?? 10,
      permit_cost_currency: numOrNull(cost) ?? 0,
    };
    if (details) {
      patchDetails.mutate({ id: details.id, body });
    } else {
      createDetails.mutate({ offer: offerId, ...body });
    }
  };

  const pending = createDetails.isPending || patchDetails.isPending;
  const error = createDetails.error ?? patchDetails.error;

  return (
    <div className="space-y-3 rounded-md border border-dashed p-3">
      <p className="text-xs font-medium text-muted-foreground">Permit details</p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Building kind">
          <Select value={buildingKind} onValueChange={setBuildingKind}>
            <SelectTrigger>
              <SelectValue placeholder="Pick a building kind" />
            </SelectTrigger>
            <SelectContent>
              {(buildingKinds.data?.results ?? []).map((kind) => (
                <SelectItem key={kind.id} value={String(kind.id)}>
                  {kind.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
        <Field label="Max target size">
          <Input
            type="number"
            value={maxSize}
            onChange={(e) => setMaxSize(e.target.value)}
            placeholder="default 10"
          />
        </Field>
      </div>
      <Field label="Permit cost (coppers — approval fee, not construction)">
        <Input
          type="number"
          value={cost}
          onChange={(e) => setCost(e.target.value)}
          placeholder="0 = free"
        />
      </Field>
      <Field label="Default approved wards">
        {areas.isLoading ? (
          <p className="text-sm text-muted-foreground">Loading areas…</p>
        ) : (
          <div className="grid max-h-40 grid-cols-2 gap-1 overflow-y-auto rounded-md border p-2">
            {(areas.data ?? []).map((area) => (
              <label key={area.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={wards.has(area.id)}
                  onChange={() => toggleWard(area.id)}
                />
                {area.name}
              </label>
            ))}
          </div>
        )}
      </Field>
      {error != null && (
        <p className="text-sm text-destructive">
          {errText(error, 'Could not save the permit details.')}
        </p>
      )}
      <Button size="sm" variant="secondary" onClick={save} disabled={pending}>
        {pending ? 'Saving…' : details ? 'Save permit details' : 'Create permit details'}
      </Button>
    </div>
  );
}

function AddOfferForm({ roleId }: { roleId: number }) {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<'mission' | 'permit'>('mission');
  const [label, setLabel] = useState('');
  const [templateId, setTemplateId] = useState<string>('');
  const createOffer = useCreateOffer(roleId);
  const createDetails = useCreateMissionDetails(roleId);
  const deleteOffer = useDeleteOffer(roleId);
  // page_size: the paginator max (2026-07 audit) — this picker read only page 1
  // (25 rows), so the 26th authored template couldn't be assigned to an offer.
  const { data: templatesData } = useMissionTemplates({ page_size: 100 });
  const templates = templatesData?.results ?? [];

  const submit = () => {
    if (!label.trim()) return;
    if (kind === 'mission' && !templateId) return;
    createOffer.mutate(
      { role: roleId, kind, label: label.trim() },
      {
        onSuccess: (offer) => {
          if (kind === 'mission') {
            createDetails.mutate(
              { offer: offer.id, mission_template: Number(templateId) },
              {
                onSuccess: () => {
                  setOpen(false);
                  setLabel('');
                  setTemplateId('');
                },
                // Compensating rollback: the details create failed (usually the
                // (role, mission_template) uniqueness), so drop the now-orphaned
                // offer rather than leave a mission offer with no template.
                onError: () => deleteOffer.mutate(offer.id),
              }
            );
          } else {
            setOpen(false);
            setLabel('');
          }
        },
      }
    );
  };

  if (!open) {
    return (
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        Add offer
      </Button>
    );
  }

  return (
    <div className="space-y-3 rounded-md border border-dashed p-3">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Kind">
          <Select value={kind} onValueChange={(v) => setKind(v as 'mission' | 'permit')}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="mission">Mission</SelectItem>
              <SelectItem value="permit">Permit</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field label="Label">
          <Input value={label} onChange={(e) => setLabel(e.target.value)} />
        </Field>
      </div>

      {kind === 'mission' && (
        <Field label="Mission template">
          <Select value={templateId} onValueChange={setTemplateId}>
            <SelectTrigger>
              <SelectValue placeholder="Choose a template" />
            </SelectTrigger>
            <SelectContent>
              {templates.map((t) => (
                <SelectItem key={t.id} value={t.id.toString()}>
                  {t.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>
      )}

      {(createOffer.isError || createDetails.isError) && (
        <p className="text-sm text-destructive">
          {errText(createOffer.error ?? createDetails.error, 'Could not add the offer.')}
        </p>
      )}
      <div className="flex gap-2">
        <Button
          size="sm"
          onClick={submit}
          disabled={
            !label.trim() ||
            (kind === 'mission' && !templateId) ||
            createOffer.isPending ||
            createDetails.isPending
          }
        >
          {createOffer.isPending || createDetails.isPending ? 'Adding…' : 'Add'}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}
