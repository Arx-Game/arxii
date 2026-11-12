"""Player channels (#3299): move off Evennia's ChannelDB onto world.channels.

Data only (no schema operation; 0392 made the tables).

Forward:
1. The PUBLIC channel exists (the replacement for Evennia's stock "Public" channel).
2. Every non-covert Organization without an ORG channel gets one (the replacement for
   the Evennia ``house_<pk>`` channels, and the channel every org is provisioned with
   from now on), except an org that backs a Covenant: covenant membership lives in
   CharacterCovenantRole, so that channel would be unreachable. Naming mirrors
   ``world.channels.services.provision_org_channel``: the org name cut to 80, " (org)"
   on a clash or on the reserved public name, then " (org <pk>)". Repeated here because
   a migration must not import live services.
3. Evennia ChannelDB rows keyed "Public" (any case) or "house_<anything>" are deleted,
   with the Attributes they owned (Evennia's pre_delete signal does that for live
   models; the historical model has no signal). Subscription and Tag through-rows go
   with the channel. MudInfo and every other ChannelDB row are untouched.
4. Every Evennia channel nick on every account or object is deleted: nick Attributes in
   category "channel" (alias -> channel key), and "inputline" nicks whose replacement
   starts with "@channel " or "channel " (``pub hi`` -> ``@channel public = hi``). The
   stock @channel command is gone, so nothing could answer them; that includes the
   superuser's MudInfo nick. Other inputline nicks are kept.

Disposition: OOC play state. The old Public and house channel history and every
subscription to them are a deliberate discard. Evennia keeps no channel history in the
database (its comms migration 0020 removed Msg.db_receivers_channels; channel lines go
to the channel log files under server/logs), so no Msg row references these channels
and none is deleted here; the log files are left on disk and nothing reads them. Players
opt in again: no one is auto-subscribed to the new channels.

Reverse: noop. The deleted Evennia channels and nicks are not rebuilt (DEFAULT_CHANNELS
is now empty, so nothing would recreate or use them), and the created channels are left
for 0392's reverse, which drops their tables.
"""

# seed-data-ok: carries rows the database already holds into the new store - the
# Evennia Public channel and each house_<pk> channel become world.channels rows, and
# each existing non-covert, non-covenant Organization gets the ORG channel every org is
# now made with.
# Nothing authored is invented; the only text written is the public channel's fixed
# description, identical to ensure_public_channel's.

from django.db import migrations

PUBLIC_CHANNEL_NAME = "Public"
PUBLIC_CHANNEL_DESCRIPTION = (
    "The game-wide out-of-character channel. Everyone can read and post here."
)
KIND_PUBLIC = "public"
KIND_ORG = "org"
CHANNEL_NAME_MAX = 80
ORG_NAME_SUFFIX = " (org)"
CHANNEL_NICK_PREFIXES = ("@channel ", "channel ")
NICK_ATTRTYPE = "nick"
NICK_CATEGORY_CHANNEL = "channel"
NICK_CATEGORY_INPUTLINE = "inputline"
# Evennia stores a nick as (regex, template, raw pattern, replacement).
NICK_TUPLE_LEN = 4


def _org_channel_name(channel_model, organization) -> str:
    name = organization.name[:CHANNEL_NAME_MAX]
    if name == PUBLIC_CHANNEL_NAME or channel_model.objects.filter(name=name).exists():
        name = organization.name[: CHANNEL_NAME_MAX - len(ORG_NAME_SUFFIX)] + ORG_NAME_SUFFIX
        if channel_model.objects.filter(name=name).exists():
            suffix = f" (org {organization.pk})"
            name = organization.name[: CHANNEL_NAME_MAX - len(suffix)] + suffix
    return name


def _is_channel_nick(attribute) -> bool:
    if attribute.db_category == NICK_CATEGORY_CHANNEL:
        return True
    value = attribute.db_value
    if not isinstance(value, (tuple, list)) or len(value) < NICK_TUPLE_LEN:
        return False
    replacement = value[NICK_TUPLE_LEN - 1]
    return isinstance(replacement, str) and replacement.startswith(CHANNEL_NICK_PREFIXES)


def _delete_channel_nicks(attribute_model) -> None:
    """Channel nicks only: a few rows, pickled values, so matched in Python."""
    nicks = attribute_model.objects.filter(
        db_attrtype=NICK_ATTRTYPE,
        db_category__in=(NICK_CATEGORY_CHANNEL, NICK_CATEGORY_INPUTLINE),
    )
    doomed = [nick.pk for nick in nicks if _is_channel_nick(nick)]
    if doomed:
        attribute_model.objects.filter(pk__in=doomed).delete()


def carry_channels_off_evennia(apps, schema_editor):
    Channel = apps.get_model("arxii", "Channel")
    Organization = apps.get_model("arxii", "Organization")
    ChannelDB = apps.get_model("comms", "ChannelDB")
    Attribute = apps.get_model("typeclasses", "Attribute")

    if not Channel.objects.filter(name=PUBLIC_CHANNEL_NAME).exists():
        Channel.objects.create(
            name=PUBLIC_CHANNEL_NAME,
            kind=KIND_PUBLIC,
            description=PUBLIC_CHANNEL_DESCRIPTION,
        )

    Covenant = apps.get_model("arxii", "Covenant")
    skip = set(Covenant.objects.values_list("organization_id", flat=True))
    has_channel = set(
        Channel.objects.filter(organization__isnull=False).values_list("organization_id", flat=True)
    )
    for organization in Organization.objects.filter(is_covert=False).order_by("pk"):
        if organization.pk in has_channel or organization.pk in skip:
            continue
        Channel.objects.create(
            name=_org_channel_name(Channel, organization),
            kind=KIND_ORG,
            organization=organization,
        )

    _delete_channel_nicks(Attribute)

    retired = ChannelDB.objects.filter(
        db_key__iexact=PUBLIC_CHANNEL_NAME
    ) | ChannelDB.objects.filter(db_key__startswith="house_")
    retired_ids = list(retired.values_list("pk", flat=True))
    if not retired_ids:
        return
    attribute_ids = list(
        ChannelDB.db_attributes.through.objects.filter(channeldb_id__in=retired_ids).values_list(
            "attribute_id", flat=True
        )
    )
    ChannelDB.objects.filter(pk__in=retired_ids).delete()
    Attribute.objects.filter(pk__in=attribute_ids).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("arxii", "0402_channel_channelban_channelmessage_and_more"),
        ("comms", "0022_defaultchannel_alter_channeldb_id_alter_msg_id_and_more"),
        ("typeclasses", "0017_use_index_instead_of_index_together_in_tags"),
    ]

    operations = [
        migrations.RunPython(carry_channels_off_evennia, migrations.RunPython.noop),
    ]
