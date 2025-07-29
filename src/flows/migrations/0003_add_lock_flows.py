"""Add flows for locking and unlocking exits."""

from django.db import migrations


def create_lock_flows(apps, schema_editor):
    FlowDefinition = apps.get_model("flows", "FlowDefinition")
    FlowStepDefinition = apps.get_model("flows", "FlowStepDefinition")

    lock_flow, _ = FlowDefinition.objects.get_or_create(
        name="lock_exit",
        defaults={"description": "Lock an exit using a key."},
    )
    FlowStepDefinition.objects.get_or_create(
        flow=lock_flow,
        parent=None,
        action="call_service_function",
        variable_name="register_behavior_package",
        defaults={
            "parameters": {
                "obj": "@target",
                "package_name": "locked_exit",
                "hook": "can_traverse",
                "data": {
                    "attribute": "key_id",
                    "value": "@key.key_id",
                },
            }
        },
    )

    unlock_flow, _ = FlowDefinition.objects.get_or_create(
        name="unlock_exit",
        defaults={"description": "Unlock an exit using a key."},
    )
    FlowStepDefinition.objects.get_or_create(
        flow=unlock_flow,
        parent=None,
        action="call_service_function",
        variable_name="remove_behavior_package",
        defaults={
            "parameters": {
                "obj": "@target",
                "package_name": "locked_exit",
            }
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("flows", "0002_add_basic_flows"),
    ]

    operations = [
        migrations.RunPython(create_lock_flows, reverse_code=migrations.RunPython.noop),
    ]
