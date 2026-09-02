/**
 * The submit button's text for a story-hierarchy form dialog.
 *
 * Every one of these dialogs (story, chapter, episode, beat, transition, table)
 * wants the same four-way answer and differs only in the noun, so they share this
 * rather than each carrying its own copy.
 */
export function formSubmitLabel(isPending: boolean, isEdit: boolean, noun: string): string {
  if (isPending) return isEdit ? 'Saving…' : 'Creating…';
  return isEdit ? `Save ${noun}` : `Create ${noun}`;
}
