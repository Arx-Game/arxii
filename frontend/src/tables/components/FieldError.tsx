import type { BulletinFieldErrors } from '../bulletinErrors';

/**
 * Render a single field's DRF error messages (2026-07 audit dedup).
 *
 * The bulletin/table forms all render the same `Array.isArray(errs[field]) &&
 * <p …>{errs[field].join(' ')}</p>` block per field plus a `non_field_errors`
 * + `detail` footer; SonarCloud flagged the copy-paste. This centralizes it.
 */
export function FieldError({
  errors,
  field,
  id,
  className = 'text-sm text-destructive',
}: {
  errors: BulletinFieldErrors;
  field: string;
  id?: string;
  className?: string;
}) {
  const value = errors[field];
  if (!Array.isArray(value)) return null;
  return (
    <p id={id} className={className}>
      {(value as string[]).join(' ')}
    </p>
  );
}

/** The shared `non_field_errors` + `detail` footer every bulletin/table form shows. */
export function FormErrors({
  errors,
  className = 'text-sm text-destructive',
}: {
  errors: BulletinFieldErrors;
  className?: string;
}) {
  return (
    <>
      {Array.isArray(errors.non_field_errors) && (
        <p className={className}>{errors.non_field_errors.join(' ')}</p>
      )}
      {typeof errors.detail === 'string' && <p className={className}>{errors.detail}</p>}
    </>
  );
}
