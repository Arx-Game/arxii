import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import type { FieldProps } from '@/rituals/types';

export function SelectField({ field, value, onChange, disabled }: FieldProps) {
  const handleChange = (selectedValue: string) => {
    // Try to parse as number if the choice value is a number
    const choice = field.choices?.find((c) => String(c.value) === selectedValue);
    if (choice) {
      onChange(choice.value);
    }
  };

  return (
    <div className="space-y-2">
      <Label htmlFor={field.name}>{field.label}</Label>
      <Select value={String(value ?? '')} onValueChange={handleChange} disabled={disabled}>
        <SelectTrigger id={field.name}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {field.choices?.map((choice) => (
            <SelectItem key={choice.value} value={String(choice.value)}>
              {choice.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {field.help && <p className="text-xs text-muted-foreground">{field.help}</p>}
    </div>
  );
}
