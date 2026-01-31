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
