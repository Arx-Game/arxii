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
    # Peeked before the bulk_create (#3816 fix round 2): reading
    # pose.cached_action_links (rather than peeking) would force a query on a
    # cold cache on a freshly-created pose, and reading it AFTER the write
    # would re-query the DB (which now includes the rows just inserted
    # below) and then append them again -- doubling the list, which sticks
    # for every later read of this identity-mapped instance in this worker
    # process. A cold cache is simply left alone.
    existing = pose.__dict__.get("cached_action_links")
    created = InteractionAction.objects.bulk_create(links)
    if existing is not None:
        pose.cached_action_links = [*existing, *created]
    return created
