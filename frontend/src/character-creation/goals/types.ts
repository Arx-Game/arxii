/**
 * Goal domain from the backend API.
 * Represents a ModifierType with category='goal'.
 */
export interface GoalDomain {
  id: number;
  name: string;
  description: string;
  display_order: number;
  is_optional: boolean;
}

/**
 * A goal being edited in the draft.
 */
export interface DraftGoal {
  domain: string; // domain name (lowercase)
  text: string; // freeform goal description
  points: number; // points allocated
}
