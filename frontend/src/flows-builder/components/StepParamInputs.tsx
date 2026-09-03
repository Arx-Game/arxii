/**
 * StepParamInputs — one input per `ParamSpec` declared on a step's action,
 * plus the extra-params key/value editor for actions with
 * `allows_extra_params` (currently only `call_service_function`).
 *
 * Values are kept as the editor's native representation (string from an
 * `<Input>`, boolean from the `<Switch>`, a plain object from the
 * key/value editor) and are NOT coerced to the declared `ParamSpec.type`
 * here — `stepTree.ts`'s `coerceParams` does that at save time. This
 * mirrors `missions/components/PredicateBuilder.tsx`'s leaf-param inputs,
 * which store raw strings and coerce via `coercePredicate` before save.
 */
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Combobox, type ComboboxItem } from '@/components/ui/combobox';
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

import type { ClientStep, DslCatalog, ParamSpec, StepActionSpec } from '../types';
import { toDisplayString } from '@/lib/displayValue';

/** Params named `result_variable` always get this friendlier label. */
const RESULT_VARIABLE_LABEL = 'Store result as';

/** Actions whose `event_type` param picks from the event catalog rather than free text. */
const EMIT_ACTIONS = new Set(['emit_flow_event', 'emit_flow_event_for_each']);

interface StepParamInputsProps {
  step: ClientStep;
  spec: StepActionSpec;
  catalog: DslCatalog;
  idPrefix: string;
  onChange: (next: ClientStep) => void;
}

export function StepParamInputs({ step, spec, catalog, idPrefix, onChange }: StepParamInputsProps) {
  const setParam = (name: string, value: unknown) => {
    onChange({ ...step, parameters: { ...step.parameters, [name]: value } });
  };
  const removeParam = (name: string) => {
    const next = { ...step.parameters };
    delete next[name];
    onChange({ ...step, parameters: next });
  };

  const declaredNames = new Set(spec.params.map((param) => param.name));
  const extraEntries: [string, unknown][] = spec.allows_extra_params
    ? Object.entries(step.parameters).filter(([name]) => !declaredNames.has(name))
    : [];

  if (spec.params.length === 0 && !spec.allows_extra_params) return null;

  return (
    <div className="space-y-2" data-testid="step-param-inputs">
      {spec.params.map((param) => (
        <ParamField
          key={param.name}
          param={param}
          value={step.parameters[param.name]}
          action={spec.action}
          catalog={catalog}
          inputId={`${idPrefix}-param-${param.name}`}
          onChange={(value) => setParam(param.name, value)}
        />
      ))}
      {spec.allows_extra_params ? (
        <ExtraParamsEditor entries={extraEntries} onSet={setParam} onRemove={removeParam} />
      ) : null}
    </div>
  );
}

function ParamField({
  param,
  value,
  action,
  catalog,
  inputId,
  onChange,
}: {
  param: ParamSpec;
  value: unknown;
  action: string;
  catalog: DslCatalog;
  inputId: string;
  onChange: (value: unknown) => void;
}) {
  const display = toDisplayString(value);
  const label = param.name === 'result_variable' ? RESULT_VARIABLE_LABEL : param.name;

  if (EMIT_ACTIONS.has(action) && param.name === 'event_type') {
    return (
      <FieldShell label={label} description={param.description} inputId={inputId}>
        <Select value={display} onValueChange={onChange}>
          <SelectTrigger id={inputId} className="h-8">
            <SelectValue placeholder="Defaults to variable_name…" />
          </SelectTrigger>
          <SelectContent>
            {catalog.events.map((event) => (
              <SelectItem key={event.name} value={event.name}>
                {event.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FieldShell>
    );
  }

  if (param.choices.length > 0) {
    return (
      <FieldShell label={label} description={param.description} inputId={inputId}>
        <Select value={display} onValueChange={onChange}>
          <SelectTrigger id={inputId} className="h-8">
            <SelectValue placeholder="Pick a value…" />
          </SelectTrigger>
          <SelectContent>
            {param.choices.map((choice) => (
              <SelectItem key={choice} value={choice}>
                {choice}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </FieldShell>
    );
  }

  if (param.type === 'bool') {
    return (
      <div className="flex items-center gap-2">
        <Switch id={inputId} checked={value === true} onCheckedChange={onChange} />
        <Label htmlFor={inputId} className="text-xs">
          {label}
        </Label>
      </div>
    );
  }

  if (param.type === 'int' || param.type === 'float') {
    return (
      <FieldShell label={label} description={param.description} inputId={inputId}>
        <Input
          id={inputId}
          type="number"
          step={param.type === 'float' ? 'any' : 1}
          value={display}
          onChange={(e) => onChange(e.target.value)}
        />
      </FieldShell>
    );
  }

  if (param.type === 'dict') {
    return (
      <FieldShell label={label} description={param.description} inputId={inputId}>
        <DictEditor value={value} onChange={onChange} />
      </FieldShell>
    );
  }

  // 'json' and 'str' both render as free text; a 'json' value is
  // JSON.parse'd from this raw string at save time by coerceParams.
  return (
    <FieldShell label={label} description={param.description} inputId={inputId}>
      <Input id={inputId} value={display} onChange={(e) => onChange(e.target.value)} />
    </FieldShell>
  );
}

function FieldShell({
  label,
  description,
  inputId,
  children,
}: {
  label: string;
  description: string;
  inputId: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <Label htmlFor={inputId} className="text-xs">
        {label}
      </Label>
      {children}
      {description ? <div className="text-xs text-muted-foreground">{description}</div> : null}
    </div>
  );
}

/**
 * Key/value row editor for a `dict`-typed param (e.g. `emit_flow_event`'s
 * `data`) — or, when the author passes the whole dict via a flow variable
 * (e.g. `data: "@vars"`), a free-text reference input instead. The mode
 * follows the current value's shape (string -> reference, object -> table);
 * each "use X instead" control both flips the mode and resets the value to
 * that mode's empty form, so switching is an explicit discard rather than a
 * silent one (the original bug: a string value got coerced to `{}` on
 * every render just by opening this editor).
 */
function DictEditor({ value, onChange }: { value: unknown; onChange: (next: unknown) => void }) {
  if (typeof value === 'string') {
    return (
      <div className="space-y-1">
        <Input
          aria-label="Reference"
          placeholder="@some_variable"
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
        <Button
          size="sm"
          variant="link"
          className="h-auto p-0 text-xs"
          onClick={() => onChange({})}
        >
          Use key/value entries instead
        </Button>
      </div>
    );
  }

  const dict: Record<string, unknown> =
    value && typeof value === 'object' && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : {};
  const entries = Object.entries(dict);

  const setKey = (index: number, newKey: string) => {
    const next: Record<string, unknown> = {};
    entries.forEach(([k, v], i) => {
      next[i === index ? newKey : k] = v;
    });
    onChange(next);
  };
  const setValue = (index: number, newValue: string) => {
    const next: Record<string, unknown> = {};
    entries.forEach(([k, v], i) => {
      next[k] = i === index ? newValue : v;
    });
    onChange(next);
  };
  const addEntry = () => onChange({ ...dict, '': '' });
  const removeEntry = (index: number) => {
    const next: Record<string, unknown> = {};
    entries.forEach(([k, v], i) => {
      if (i !== index) next[k] = v;
    });
    onChange(next);
  };

  return (
    <div className="space-y-1">
      {entries.map(([key, val], index) => (
        // Rows are addressed by position (not by `key`, which the user is
        // actively editing), so an index key is correct here.
        <div key={index} className="flex items-center gap-1">
          <Input
            aria-label="Key"
            className="h-7"
            value={key}
            onChange={(e) => setKey(index, e.target.value)}
          />
          <Input
            aria-label="Value"
            className="h-7"
            value={toDisplayString(val)}
            onChange={(e) => setValue(index, e.target.value)}
          />
          <Button
            size="sm"
            variant="ghost"
            onClick={() => removeEntry(index)}
            aria-label="Remove entry"
          >
            −
          </Button>
        </div>
      ))}
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" onClick={addEntry}>
          + Add entry
        </Button>
        <Button
          size="sm"
          variant="link"
          className="h-auto p-0 text-xs"
          onClick={() => onChange('')}
        >
          Use a reference instead
        </Button>
      </div>
    </div>
  );
}

/** Key/value editor for the extra kwargs an `allows_extra_params` action accepts. */
function ExtraParamsEditor({
  entries,
  onSet,
  onRemove,
}: {
  entries: [string, unknown][];
  onSet: (name: string, value: unknown) => void;
  onRemove: (name: string) => void;
}) {
  const renameKey = (oldKey: string, newKey: string) => {
    if (!newKey || newKey === oldKey) return;
    const value = entries.find(([k]) => k === oldKey)?.[1];
    onRemove(oldKey);
    onSet(newKey, value ?? '');
  };

  return (
    <div className="space-y-1 rounded border border-dashed p-2">
      <div className="text-xs font-medium text-muted-foreground">Extra parameters</div>
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-center gap-1">
          <Input
            aria-label="Parameter name"
            className="h-7"
            defaultValue={key}
            onBlur={(e) => renameKey(key, e.target.value.trim())}
          />
          <Input
            aria-label="Parameter value"
            className="h-7"
            value={toDisplayString(value)}
            onChange={(e) => onSet(key, e.target.value)}
          />
          <Button
            size="sm"
            variant="ghost"
            onClick={() => onRemove(key)}
            aria-label="Remove parameter"
          >
            −
          </Button>
        </div>
      ))}
      <AddExtraParamRow onAdd={(name) => onSet(name, '')} existingNames={entries.map(([k]) => k)} />
    </div>
  );
}

function AddExtraParamRow({
  onAdd,
  existingNames,
}: {
  onAdd: (name: string) => void;
  existingNames: string[];
}) {
  const [name, setName] = useState('');
  const add = () => {
    const trimmed = name.trim();
    if (!trimmed || existingNames.includes(trimmed)) return;
    onAdd(trimmed);
    setName('');
  };
  return (
    <div className="flex items-center gap-1">
      <Input
        aria-label="New parameter name"
        className="h-7"
        placeholder="parameter name"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <Button size="sm" variant="outline" onClick={add}>
        + Add
      </Button>
    </div>
  );
}

/** Searchable service-function picker + free-entry dotted-path input, sharing one value. */
export function ServiceFunctionField({
  value,
  serviceFunctions,
  inputId,
  onChange,
}: {
  value: string;
  serviceFunctions: DslCatalog['service_functions'];
  inputId: string;
  onChange: (value: string) => void;
}) {
  const items: ComboboxItem[] = serviceFunctions.map((fn) => ({
    value: fn.name,
    label: fn.name,
    secondaryText: fn.description || undefined,
  }));
  return (
    <div className="space-y-1">
      <Combobox
        items={items}
        value={value}
        onValueChange={onChange}
        placeholder="Search service functions…"
        searchPlaceholder="Search…"
        emptyMessage="No match — type the dotted path below."
      />
      <Input
        id={inputId}
        placeholder="or type a dotted path…"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-8"
      />
    </div>
  );
}
