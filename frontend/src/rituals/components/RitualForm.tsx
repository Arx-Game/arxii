import { getFieldComponent } from './fields';
import type { RitualInputSchema } from '../types';

export interface RitualFormProps {
  schema: RitualInputSchema;
  values: Record<string, string | number | null>;
  onChange: (values: Record<string, string | number | null>) => void;
  disabled?: boolean;
  /** Active character_sheet_id for the performance; passed through to fields. */
  characterSheetId?: number;
}

export function RitualForm({
  schema,
  values,
  onChange,
  disabled,
  characterSheetId,
}: RitualFormProps) {
  const handleFieldChange = (fieldName: string, newValue: string | number | null) => {
    const updatedValues = { ...values, [fieldName]: newValue };
    onChange(updatedValues);
  };

  return (
    <div className="space-y-4">
      {schema.fields.map((field) => {
        const FieldComponent = getFieldComponent(field.type);
        const fieldValue = values[field.name] ?? null;

        return (
          <FieldComponent
            key={field.name}
            field={field}
            value={fieldValue}
            onChange={(newValue) => handleFieldChange(field.name, newValue)}
            disabled={disabled}
            formValues={values}
            characterSheetId={characterSheetId}
          />
        );
      })}
    </div>
  );
}
