import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { FieldProps } from '@/rituals/types';

export function TextField({ field, value, onChange, disabled }: FieldProps) {
  return (
    <div className="space-y-2">
      <Label htmlFor={field.name}>{field.label}</Label>
      <Input
        id={field.name}
        type="text"
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      />
      {field.help && <p className="text-xs text-muted-foreground">{field.help}</p>}
    </div>
  );
}
