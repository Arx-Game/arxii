/**
 * The small pieces every staff edit mode row editor is built from (#4221, #4229): a
 * titled section, a plain select, and a picker wired to the one action it feeds.
 */

import { useState, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import type { StaffOption, StaffRowAction } from '@/character_sheets/api';
import { asItems } from './staffRowItems';

export type Run = (request: StaffRowAction, onDone?: () => void) => void;

export function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2 border-t pt-3" aria-label={title}>
      <h3 className="refsheet-eyebrow">{title}</h3>
      {children}
    </section>
  );
}

export function Select({
  label,
  value,
  onChange,
  options,
  blank = '—',
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  /** The empty row's text; ``null`` draws no empty row (the value is always set). */
  blank?: string | null;
}) {
  return (
    <select
      aria-label={label}
      className="h-9 rounded-md border bg-transparent px-2 text-sm"
      value={value}
      onChange={(event) => onChange(event.target.value)}
    >
      {blank !== null && <option value="">{blank}</option>}
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

/** A picker and the one action it feeds; ``allowBlank`` sends no id for the blank row. */
export function PickAndRun({
  label,
  options,
  action,
  onRun,
  blank,
  allowBlank = false,
}: {
  label: string;
  options: StaffOption[];
  action: string;
  /** ``null`` only when ``allowBlank`` lets the blank row through. */
  onRun: (id: number | null) => void;
  blank?: string;
  allowBlank?: boolean;
}) {
  const [value, setValue] = useState('');
  return (
    <span className="flex flex-wrap items-center gap-2">
      <Select
        label={label}
        value={value}
        onChange={setValue}
        options={asItems(options)}
        blank={blank}
      />
      <Button
        type="button"
        size="sm"
        disabled={!value && !allowBlank}
        onClick={() => onRun(value ? Number(value) : null)}
      >
        {action}
      </Button>
    </span>
  );
}
