/**
 * Types for the goal-log affordance (#3045).
 *
 * `CharacterGoalViewSet` / `GoalJournalViewSet` (`world.goals.views`) have no
 * `@extend_schema` and their serializers aren't drf-spectacular-inferrable
 * (character-scoped `ViewSet`s, not `ModelViewSet`s), so these mirror
 * `world.goals.serializers.CharacterGoalSerializer` /
 * `GoalJournalSerializer` / `GoalJournalCreateSerializer` by hand rather than
 * re-exporting a generated component.
 */

export interface CharacterGoal {
  id: number;
  domain: number;
  domain_name: string;
  points: number;
  notes: string;
  updated_at: string;
}

export interface MyGoalsResponse {
  goals: CharacterGoal[];
  total_points: number;
  points_remaining: number;
  revision: {
    last_revised_at: string | null;
    can_revise: boolean;
  };
}

export interface GoalJournalEntry {
  id: number;
  domain: number | null;
  domain_name: string | null;
  title: string;
  content: string;
  is_public: boolean;
  xp_awarded: number;
  created_at: string;
}

export interface CreateGoalJournalRequest {
  domain?: number | null;
  title: string;
  content: string;
  is_public?: boolean;
}
