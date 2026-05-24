"""Auto-linking of POSE Interactions to prior unlinked ACTION Interactions.

See docs/superpowers/specs/2026-05-23-unified-combat-ui-design.md §3.
"""

from django.db.models import Exists, OuterRef

from world.scenes.constants import InteractionMode
from world.scenes.models import Interaction, InteractionAction


def auto_link_pose_to_actions(pose: Interaction) -> list[InteractionAction]:
    """Attach this persona's unlinked ACTION Interactions in this scene to *pose*.

    Selects ACTION-mode Interactions where:
    - persona matches the pose's persona
    - scene matches the pose's scene
    - timestamp is strictly before the pose
    - the Interaction is not already attached to any other pose via
      InteractionAction.action_interaction

    Returns the created InteractionAction rows in chronological (timestamp) order.
    No-op when *pose* is not POSE-mode.

    NOTE: Uses bulk_create which bypasses clean(). Trusted to construct only
    valid rows — the queryset filter guarantees pose.mode == POSE (when the
    early return is satisfied) and action.mode == ACTION.
    """
    if pose.mode != InteractionMode.POSE:
        return []

    already_linked = InteractionAction.objects.filter(action_interaction=OuterRef("pk"))
    candidate_qs = (
        Interaction.objects.filter(
            persona=pose.persona,
            scene=pose.scene,
            mode=InteractionMode.ACTION,
            timestamp__lt=pose.timestamp,
        )
        .annotate(is_linked=Exists(already_linked))
        .filter(is_linked=False)
        .order_by("timestamp")
    )

    links = [
        InteractionAction(pose=pose, action_interaction=action, ordering=i)
        for i, action in enumerate(candidate_qs)
    ]
    return InteractionAction.objects.bulk_create(links)
