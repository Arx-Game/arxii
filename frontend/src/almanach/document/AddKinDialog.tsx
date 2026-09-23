/**
 * AddKinDialog (#3983 Task 9, plate S-IV's "⊕ a child · a spouse" /
 * "⊕ a person of the household · a position" doors) — mints a new
 * `Kinsperson` via `almanach_edit_kin`'s create branch (`kinsperson_id`
 * absent). Both doors open the same dialog; `defaultHousehold` seeds
 * `relation="ward"` and pins `is_household` true (the household band's
 * entry point never needs a parent/spouse pick), while the tree's own door
 * seeds `relation="child"`.
 *
 * Follows `PlantRungDialog`'s shape (`Dialog`/`DialogContent`/
 * `DialogFooter`/`DialogTitle`, Cancel outlined + a primary submit).
 *
 * The plate's "born into" field (a secondary, non-primary family
 * membership, `born_into_family_id`) is deliberately NOT built here: that
 * kwarg takes a `Family` pk, and the only house picker this app exposes
 * (`AlmanachHouseSummary`, `useAllHouses`) carries the house's own
 * `Organization` id, never its `family_id` — sending the org id as a family
 * id would silently target the wrong row (or refuse with "no such family").
 * A stated omission, not a guess; closing it needs `AlmanachHouseSummary`
 * to carry `family_id` first.
 */
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

import { useGenders } from '../queries';
import type { AlmanachFamilyNode } from '../types';

export type KinRelation =
  | 'head'
  | 'mother'
  | 'father'
  | 'spouse'
  | 'sibling'
  | 'child'
  | 'grandparent'
  | 'ward'
  | 'position';

const RELATION_CHOICES: { value: KinRelation; label: string }[] = [
  { value: 'head', label: 'head of house' },
  { value: 'mother', label: 'mother' },
  { value: 'father', label: 'father' },
  { value: 'spouse', label: 'spouse' },
  { value: 'sibling', label: 'sibling' },
  { value: 'child', label: 'child' },
  { value: 'grandparent', label: 'grandparent' },
  { value: 'ward', label: 'ward' },
  { value: 'position', label: 'household position' },
];

export interface CreateKinFields {
  org_id: number;
  name: string;
  relation: KinRelation;
  parent_kinsperson_id?: number;
  spouse_kinsperson_id?: number;
  gender_id?: number;
  age?: number;
  is_deceased?: boolean;
  is_household?: boolean;
}

export interface AddKinDialogProps {
  houseId: number;
  /** The tree's own nodes, for the parent/spouse pick. */
  nodes: AlmanachFamilyNode[];
  defaultHousehold: boolean;
  open: boolean;
  onClose: () => void;
  onConfirm: (fields: CreateKinFields) => void;
}

export function AddKinDialog({
  houseId,
  nodes,
  defaultHousehold,
  open,
  onClose,
  onConfirm,
}: AddKinDialogProps) {
  const { data: genders } = useGenders();
  const [name, setName] = useState('');
  const [relation, setRelation] = useState<KinRelation>(defaultHousehold ? 'ward' : 'child');
  const [parentId, setParentId] = useState('');
  const [spouseId, setSpouseId] = useState('');
  const [genderId, setGenderId] = useState('');
  const [age, setAge] = useState('');

  useEffect(() => {
    if (!open) return;
    setName('');
    setRelation(defaultHousehold ? 'ward' : 'child');
    setParentId('');
    setSpouseId('');
    setGenderId('');
    setAge('');
  }, [open, defaultHousehold]);

  const trimmedName = name.trim();
  const needsParent = relation === 'child';
  const needsSpouse = relation === 'spouse';
  const canSubmit =
    trimmedName !== '' && (!needsParent || parentId !== '') && (!needsSpouse || spouseId !== '');

  const submit = () => {
    if (!canSubmit) return;
    onConfirm({
      org_id: houseId,
      name: trimmedName,
      relation,
      ...(needsParent && parentId !== '' ? { parent_kinsperson_id: Number(parentId) } : {}),
      ...(needsSpouse && spouseId !== '' ? { spouse_kinsperson_id: Number(spouseId) } : {}),
      ...(genderId !== '' ? { gender_id: Number(genderId) } : {}),
      ...(age.trim() !== '' ? { age: Number(age) } : {}),
      ...(defaultHousehold ? { is_household: true } : {}),
    });
    onClose();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <DialogContent className="almanach max-w-md">
        <DialogTitle>
          {defaultHousehold ? 'A person of the household' : 'A child · a spouse'}
        </DialogTitle>
        <div className="field">
          <Label htmlFor="add-kin-name">name</Label>
          <Input
            id="add-kin-name"
            autoFocus
            value={name}
            onChange={(event) => setName(event.target.value)}
            autoComplete="off"
          />
        </div>
        <div className="field">
          <Label htmlFor="add-kin-relation">relation</Label>
          <Select value={relation} onValueChange={(value) => setRelation(value as KinRelation)}>
            <SelectTrigger id="add-kin-relation">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {RELATION_CHOICES.map((choice) => (
                <SelectItem key={choice.value} value={choice.value}>
                  {choice.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        {needsParent && (
          <div className="field">
            <Label htmlFor="add-kin-parent">parent</Label>
            <Select value={parentId} onValueChange={setParentId}>
              <SelectTrigger id="add-kin-parent">
                <SelectValue placeholder="pick a parent" />
              </SelectTrigger>
              <SelectContent>
                {nodes.map((node) => (
                  <SelectItem key={node.id} value={String(node.id)}>
                    {node.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        {needsSpouse && (
          <div className="field">
            <Label htmlFor="add-kin-spouse">spouse</Label>
            <Select value={spouseId} onValueChange={setSpouseId}>
              <SelectTrigger id="add-kin-spouse">
                <SelectValue placeholder="pick a spouse" />
              </SelectTrigger>
              <SelectContent>
                {nodes.map((node) => (
                  <SelectItem key={node.id} value={String(node.id)}>
                    {node.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
        <div className="row2">
          <div className="field">
            <Label htmlFor="add-kin-gender">gender</Label>
            <Select value={genderId} onValueChange={setGenderId}>
              <SelectTrigger id="add-kin-gender">
                <SelectValue placeholder="unspecified" />
              </SelectTrigger>
              <SelectContent>
                {(genders ?? []).map((gender) => (
                  <SelectItem key={gender.id} value={String(gender.id)}>
                    {gender.display_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="field">
            <Label htmlFor="add-kin-age">age</Label>
            <Input
              id="add-kin-age"
              type="number"
              min={0}
              value={age}
              onChange={(event) => setAge(event.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" onClick={submit} disabled={!canSubmit}>
            Add
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
