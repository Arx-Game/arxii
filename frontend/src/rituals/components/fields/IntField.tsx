import type React from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { FieldProps } from '@/rituals/types';

export function IntField({ field, value, onChange, disabled }: FieldProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const inputValue = e.target.value;
    if (inputValue === '' || inputValue === '-') {
      onChange(null);
      return;
    }

    const parsed = parseInt(inputValue, 10);
    if (Number.isNaN(parsed)) {
      onChange(null);
    } else {
      onChange(parsed);
    }
  };

  return (
    <div className="space-y-2">
      <Label htmlFor={field.name}>{field.label}</Label>
      <Input
        id={field.name}
        type="number"
        value={value ?? ''}
        onChange={handleChange}
        disabled={disabled}
      />
      {field.help && <p className="text-xs text-muted-foreground">{field.help}</p>}
    </div>
  );
}
