import { ChangeEvent } from 'react';
import { Label } from '@/components/ui/label';

interface CommandTextFieldProps {
  param: string;
  value: string;
  onChange: (e: ChangeEvent<HTMLInputElement>) => void;
}

export function CommandTextField({ param, value, onChange }: CommandTextFieldProps) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={param}>{param}</Label>
      <input
        id={param}
        type="text"
        value={value}
        onChange={onChange}
        className="w-full rounded border p-2"
      />
    </div>
  );
}
