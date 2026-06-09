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

import { ApiValidationError, flattenErrorMessage } from '../api';
import {
  useCreateMissionDetails,
  useCreateOffer,
  useDeleteOffer,
  useDeleteRole,
  useMissionDetailsForRole,
  useOffersForRole,
  usePatchMissionDetails,
  usePatchOffer,
  usePatchRole,
  useRole,
} from '../queries';
import type { MissionOfferDetails, NPCServiceOffer } from '../types';

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

  useEffect(() => {
    if (!role) return;
    setName(role.name ?? '');
    setDescription(role.description ?? '');
    setTemplate(role.default_description_template ?? '');
    setRapport(role.default_rapport_starting_value?.toString() ?? '');
    setFaction(role.faction_affiliation?.toString() ?? '');
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
  const offers = offersData?.results ?? [];
  const detailsByOffer = new Map<number, MissionOfferDetails>();
  for (const d of detailsData?.results ?? []) {
    if (typeof d.offer === 'number') detailsByOffer.set(d.offer, d);
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
}: {
  roleId: number;
  offer: NPCServiceOffer;
  details: MissionOfferDetails | null;
}) {
  const patchOffer = usePatchOffer(roleId);
  const patchDetails = usePatchMissionDetails(roleId);
  const del = useDeleteOffer(roleId);
  const leaves = usePredicateLeaves().data ?? [];

  const [label, setLabel] = useState(offer.label ?? '');
  const [drawMode, setDrawMode] = useState(offer.draw_mode ?? 'menu');
  const [rapportReq, setRapportReq] = useState(offer.rapport_requirement?.toString() ?? '');
  const [isFinal, setIsFinal] = useState(offer.is_final ?? false);
  const [rule, setRule] = useState<PredicateNode>(
    (offer.eligibility_rule as PredicateNode) ?? EMPTY_RULE
  );
  const [weight, setWeight] = useState(details?.weight?.toString() ?? '');

  const ruleErrors = validatePredicate(rule, leaves);

  const save = () => {
    if (ruleErrors.length > 0) return;
    patchOffer.mutate({
      id: offer.id,
      body: {
        label: label.trim(),
        draw_mode: drawMode,
        rapport_requirement: numOrNull(rapportReq) ?? 0,
        is_final: isFinal,
        eligibility_rule: coercePredicate(rule, leaves),
      },
    });
    if (offer.kind === 'mission' && details) {
      patchDetails.mutate({ id: details.id, body: { weight: numOrNull(weight) ?? 1 } });
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

      {offer.kind === 'mission' &&
        (details ? (
          <Field label="Weight">
            <Input type="number" value={weight} onChange={(e) => setWeight(e.target.value)} />
          </Field>
        ) : (
          <p className="text-sm text-muted-foreground">
            This mission offer has no MissionOfferDetails row yet — pick a template via the
            add-offer flow.
          </p>
        ))}

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
        disabled={ruleErrors.length > 0 || patchOffer.isPending || !label.trim()}
      >
        {patchOffer.isPending ? 'Saving…' : 'Save offer'}
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
  const { data: templatesData } = useMissionTemplates({});
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
