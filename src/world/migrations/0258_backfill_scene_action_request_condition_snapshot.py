"""Snapshot the condition each existing treat request is aimed at (#4475).

Data only. The columns came in 0257. A request that points at a live condition
instance gets that instance's template and name, so the record still says what was
treated once play deletes the instance. Requests the previous release writes between
this migration and the release swap carry no snapshot; deleting their instance fills
it in (``settle_treatment_requests_for_condition``).
"""

from django.db import migrations
from django.db.models import OuterRef, Subquery


def snapshot_treated_conditions(apps, schema_editor):
    SceneActionRequest = apps.get_model("arxii", "SceneActionRequest")
    ConditionInstance = apps.get_model("arxii", "ConditionInstance")

    instance = ConditionInstance.objects.filter(pk=OuterRef("target_condition_instance_id"))
    SceneActionRequest.objects.filter(
        target_condition_instance__isnull=False, target_condition_name=""
    ).update(
        target_condition_template_id=Subquery(instance.values("condition_id")[:1]),
        target_condition_name=Subquery(instance.values("condition__name")[:1]),
    )


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0257_scene_action_request_condition_snapshot"),
    ]

    operations = [
        migrations.RunPython(snapshot_treated_conditions, migrations.RunPython.noop),
    ]
