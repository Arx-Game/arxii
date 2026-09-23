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
 * membership, `born_into_family_id`) picks from `useAllHouses()`
 * (`AlmanachHouseSummary`, which now carries `family_id` — #3983 Task 10
 * fold-in) narrowed to rows with a non-null `family_id`: that kwarg takes a
 * `Family` pk, never an `Organization` id, so a house with no family on
 * record (`family_id === null`) can't be picked here. The blank option
 * (no `born_into_family_id` sent) means "just this house" — the kin's
 * primary membership already comes from `relation`, so leaving this blank
 * is the ordinary case.
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

import { useAllHouses, useGenders } from '../queries';
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
  born_into_family_id?: number;
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
  const { data: houses } = useAllHouses();
  const bornIntoOptions = (houses?.results ?? []).filter(
    (house): house is typeof house & { family_id: number } => house.family_id != null
  );
  const [name, setName] = useState('');
  const [relation, setRelation] = useState<KinRelation>(defaultHousehold ? 'ward' : 'child');
  const [parentId, setParentId] = useState('');
  const [spouseId, setSpouseId] = useState('');
  const [genderId, setGenderId] = useState('');
  const [age, setAge] = useState('');
  const [bornIntoFamilyId, setBornIntoFamilyId] = useState('');

  useEffect(() => {
    if (!open) return;
    setName('');
    setRelation(defaultHousehold ? 'ward' : 'child');
    setParentId('');
    setSpouseId('');
    setGenderId('');
    setAge('');
    setBornIntoFamilyId('');
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
      ...(bornIntoFamilyId !== '' ? { born_into_family_id: Number(bornIntoFamilyId) } : {}),
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
        <div className="field">
          <Label htmlFor="add-kin-born-into">born into</Label>
          <Select value={bornIntoFamilyId} onValueChange={setBornIntoFamilyId}>
            <SelectTrigger id="add-kin-born-into">
              <SelectValue placeholder="the house itself" />
            </SelectTrigger>
            <SelectContent>
              {bornIntoOptions.map((house) => (
                <SelectItem key={house.id} value={String(house.family_id)}>
                  {house.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
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
