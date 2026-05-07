import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type { FieldProps } from '@/rituals/types';

export function UnknownFieldFallback({ field, value, onChange, disabled }: FieldProps) {
  return (
    <div className="space-y-2">
      <Label htmlFor={field.name}>{field.label}</Label>
      <div className="space-y-2">
        <Input
          id={field.name}
          type="text"
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        />
        <div className="rounded bg-amber-950/50 p-2 text-sm text-amber-600">
          Unsupported field type '{field.type}' — frontend may need an update
        </div>
      </div>
      {field.help && <p className="text-xs text-muted-foreground">{field.help}</p>}
    </div>
  );
}
