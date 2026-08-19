/**
 * EditAreaDialog — the #3269 Phase C area-metadata editor: the `edit_area`
 * action finally gets a UI. Name/level/slug plus realm/climate/society (by
 * name, from the manager catalogs), description, colour tag, ward permit
 * eligibility. Shows the effective (inherited) climate and warns when
 * setting a climate below REGION level (per-ward climates roll their own
 * weather).
 */
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';

import { AREA_LEVELS, type WorldBuilderArea, type WorldBuilderAreaManager } from '../types';

const REGION_LEVEL = 50;
const CLEAR = '__clear__';

export interface EditAreaDialogProps {
  area: WorldBuilderArea;
  catalogs: WorldBuilderAreaManager['catalogs'];
  open: boolean;
  onOpenChange: (open: boolean) => void;
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
}

function NamedSelect({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Label className="w-28 text-xs">{label}</Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger className="h-8 flex-1">
          <SelectValue placeholder="unset" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={CLEAR}>— clear —</SelectItem>
          {options.map((name) => (
            <SelectItem key={name} value={name}>
              {name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export function EditAreaDialog({
  area,
  catalogs,
  open,
  onOpenChange,
  runAction,
}: EditAreaDialogProps) {
  const [name, setName] = useState(area.name);
  const [level, setLevel] = useState(String(area.level));
  const [realm, setRealm] = useState(area.realm ?? '');
  const [climate, setClimate] = useState(area.climate ?? '');
  const [society, setSociety] = useState(area.dominant_society ?? '');
  const [description, setDescription] = useState(area.description ?? '');
  const [color, setColor] = useState(area.color ?? '');
  const [permit, setPermit] = useState<string>(area.permit_eligibility ?? '');

  useEffect(() => {
    if (open) {
      setName(area.name);
      setLevel(String(area.level));
      setRealm(area.realm ?? '');
      setClimate(area.climate ?? '');
      setSociety(area.dominant_society ?? '');
      setDescription(area.description ?? '');
      setColor(area.color ?? '');
      setPermit(area.permit_eligibility ?? '');
    }
  }, [open, area]);

  const climateWarning = climate !== '' && climate !== CLEAR && Number(level) < REGION_LEVEL;

  const submit = () => {
    const named = (value: string) => (value === CLEAR ? '' : value || undefined);
    runAction('edit_area', {
      area_id: area.id,
      name: name.trim() || undefined,
      level: Number(level),
      realm: named(realm),
      climate: named(climate),
      dominant_society: named(society),
      description,
      color,
      permit_eligibility: permit || undefined,
    });
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Edit {area.name}</DialogTitle>
          {area.effective_climate && (
            <p className="text-xs text-muted-foreground">
              Effective climate: {area.effective_climate}
            </p>
          )}
        </DialogHeader>
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <Label className="w-28 text-xs">Name</Label>
            <Input className="h-8" value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="flex items-center gap-2">
            <Label className="w-28 text-xs">Level</Label>
            <Select value={level} onValueChange={setLevel}>
              <SelectTrigger className="h-8 flex-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AREA_LEVELS.map((option) => (
                  <SelectItem key={option.value} value={String(option.value)}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <NamedSelect label="Realm" value={realm} options={catalogs.realms} onChange={setRealm} />
          <NamedSelect
            label="Climate"
            value={climate}
            options={catalogs.climates}
            onChange={setClimate}
          />
          {climateWarning && (
            <p className="text-xs text-amber-600" data-testid="climate-warning">
              This area is below Region level — a climate here rolls its own weather, independently
              of its parents.
            </p>
          )}
          <NamedSelect
            label="Society"
            value={society}
            options={catalogs.societies}
            onChange={setSociety}
          />
          <div className="flex items-center gap-2">
            <Label className="w-28 text-xs">Permits</Label>
            <Select value={permit} onValueChange={setPermit}>
              <SelectTrigger className="h-8 flex-1">
                <SelectValue placeholder="unchanged" />
              </SelectTrigger>
              <SelectContent>
                {catalogs.permit_options.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex items-center gap-2">
            <Label className="w-28 text-xs">Colour tag</Label>
            <Input
              className="h-8"
              value={color}
              onChange={(e) => setColor(e.target.value)}
              placeholder="|y"
            />
          </div>
          <div className="flex flex-col gap-1">
            <Label className="text-xs">Description</Label>
            <Textarea
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} data-testid="edit-area-submit">
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
