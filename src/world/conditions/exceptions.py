"""
Typed exceptions for the conditions treatment system.

These exceptions carry ``user_message`` attributes so views and serializers can
surface safe, human-readable messages to API clients without exposing internal
error details (avoids ``str(exc)`` pitfalls flagged by CodeQL).
"""


class TreatmentError(Exception):
    user_message = "Treatment failed."


class TreatmentTargetMismatch(TreatmentError):
    user_message = "This treatment cannot target that effect."


class TreatmentParentMismatch(TreatmentError):
    user_message = "The targeted aftermath isn't linked to this treatment's parent condition."


class NoSupportingBondThread(TreatmentError):
    user_message = "You need a supporting bond with the target to attempt this treatment."


class TreatmentAlreadyAttempted(TreatmentError):
    user_message = "You've already attempted this treatment on the target this scene."


class TreatmentScenePrerequisiteFailed(TreatmentError):
    user_message = "You cannot attempt this treatment right now."


class TreatmentResonanceInsufficient(TreatmentError):
    user_message = "You don't have enough resonance to attempt this."


class TreatmentAnimaInsufficient(TreatmentError):
    user_message = "You don't have enough anima to attempt this."


class HelperEngagedForTreatment(TreatmentError):
    user_message = "You cannot treat someone while engaged in combat."
