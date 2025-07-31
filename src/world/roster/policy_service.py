"""
Policy service for roster application evaluation.
Handles policy checks without circular import dependencies.

This service can be safely imported by both models and serializers because:
- It only imports model constants/enums (not model classes)
- It doesn't import any serializers
- Models can import this service at method-level
- Serializers can import this service at method-level
"""

from world.roster.models import RosterType, ValidationErrorCodes, ValidationMessages


class RosterPolicyService:
    """Service for evaluating roster application policies."""

    @staticmethod
    def get_policy_issues(player_data, character):
        """
        Get policy issues that would affect approval (but not creation).

        Args:
            player_data: The PlayerData instance applying
            character: The character ObjectDB instance being applied for

        Returns:
            list: List of policy issue dictionaries with 'code' and 'message'
        """
        issues = []

        # Check roster restrictions
        roster_entry = getattr(character, "roster_entry", None)
        if not roster_entry:
            return issues

        roster_name = roster_entry.roster.name

        # Restricted characters require special approval
        if roster_name == RosterType.RESTRICTED:
            issues.append(
                {
                    "code": ValidationErrorCodes.RESTRICTED_REQUIRES_REVIEW,
                    "message": ValidationMessages.RESTRICTED_REQUIRES_REVIEW,
                }
            )

        # Inactive rosters are problematic
        if not roster_entry.roster.is_active:
            issues.append(
                {
                    "code": ValidationErrorCodes.INACTIVE_ROSTER,
                    "message": ValidationMessages.INACTIVE_ROSTER,
                }
            )

        # TODO: Add more policy checks when trust system is ready:
        # - Character requires higher trust level
        # - Player involved in conflicting storylines
        # - Player not allowed to apply to this roster type
        # - Too many pending applications

        return issues

    @staticmethod
    def get_comprehensive_policy_info(application):
        """
        Get comprehensive policy information for reviewers.

        Args:
            application: RosterApplication instance

        Returns:
            dict: Complete policy evaluation for staff review
        """
        policy_issues = RosterPolicyService.get_policy_issues(
            application.player_data, application.character
        )

        info = {
            "basic_eligibility": "Passed",  # Application exists, so basic checks passed
            "policy_issues": policy_issues,
            "requires_staff_review": bool(policy_issues),  # Any issues = needs staff
            "auto_approvable": len(policy_issues)
            == 0,  # No issues = could auto-approve
        }

        # Add context about the application
        info["player_current_characters"] = [
            char.db_key for char in application.player_data.get_available_characters()
        ]
        info["character_previous_players"] = application.character.tenures.count()

        return info
