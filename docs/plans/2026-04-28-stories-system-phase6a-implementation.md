# Phase 6a: Character Focus Backend Payload Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend `/api/user/` to expose `available_characters` (portraits, character_type, roster_status, personas, last_location, in-use flag) and `pending_applications`. Broadcast `puppet_changed` WS events on `@ic` puppet swaps and on session-driven unpuppets so other tabs can react.

**Architecture:** Augment `AccountPlayerSerializer` in `src/web/api/serializers.py` with three new nested serializers (Persona, AvailableCharacter, PendingApplication). Derive `character_type` from typeclass via a small helper module. Add a `WebsocketMessageType.PUPPET_CHANGED` enum entry. Broadcast in `Account.puppet_character_in_session` after a successful swap, and override `Account.unpuppet_object` to broadcast on disconnect-driven unpuppets.

**Tech Stack:** Django, DRF, Evennia, pytest via `arx test`. Frontend: TypeScript (types-only changes).

**Reference design:** `docs/plans/2026-04-28-character-focus-and-portrait-grid-design.md`

**Constraints from CLAUDE.md / project conventions:**
- All concrete models use `SharedMemoryModel` (no new models in this phase, but follow if any are needed)
- No relative imports — use absolute imports
- No JSON fields
- Use FactoryBoy in tests, never `create_object()` directly (`CharacterFactory`, `GMCharacterFactory`, `StaffCharacterFactory` exist in `src/evennia_extensions/factories.py`)
- Use `git -C <abspath>` instead of `cd && git`
- `arx test` for running tests, never `python -m`
- Run `arx test` (without `--keepdb`) once before declaring tasks complete to match CI fresh-DB behavior

---

### Task 1: Add `character_type` derivation helper

**Files:**
- Create: `src/web/api/character_type.py`
- Test: `src/web/tests/test_character_type.py`

**Step 1: Write the failing test**

```python
# src/web/tests/test_character_type.py
"""Tests for character_type derivation from typeclass path."""

from django.test import TestCase

from evennia_extensions.factories import (
    CharacterFactory,
    GMCharacterFactory,
    StaffCharacterFactory,
)
from web.api.character_type import derive_character_type


class DeriveCharacterTypeTests(TestCase):
    """Map typeclass paths to high-level character_type strings."""

    def test_default_character_is_pc(self) -> None:
        char = CharacterFactory()
        assert derive_character_type(char) == "PC"

    def test_gm_character_is_gm(self) -> None:
        char = GMCharacterFactory()
        assert derive_character_type(char) == "GM"

    def test_staff_character_is_staff(self) -> None:
        char = StaffCharacterFactory()
        assert derive_character_type(char) == "STAFF"
```

**Step 2: Run test (expect failure)**

Run: `echo "yes" | uv run arx test web.tests.test_character_type --keepdb`
Expected: `ModuleNotFoundError: No module named 'web.api.character_type'`

**Step 3: Write minimal implementation**

```python
# src/web/api/character_type.py
"""Derive high-level character_type for the account payload."""

from typing import Final

from evennia.objects.models import ObjectDB

TYPECLASS_TO_CHARACTER_TYPE: Final[dict[str, str]] = {
    "typeclasses.gm_characters.GMCharacter": "GM",
    "typeclasses.gm_characters.StaffCharacter": "STAFF",
}


def derive_character_type(character: ObjectDB) -> str:
    """Map a Character typeclass path to a high-level account-payload type.

    Returns "PC" for the default Character typeclass, "GM" for GMCharacter,
    "STAFF" for StaffCharacter. Future typeclasses (e.g., NPC) plug in here.
    """
    return TYPECLASS_TO_CHARACTER_TYPE.get(character.db_typeclass_path, "PC")
```

**Step 4: Run test (expect pass)**

Run: `echo "yes" | uv run arx test web.tests.test_character_type --keepdb`
Expected: 3 tests pass

**Step 5: Commit**

```bash
git -C /c/Users/apost/PycharmProjects/arxii add src/web/api/character_type.py src/web/tests/test_character_type.py
git -C /c/Users/apost/PycharmProjects/arxii commit -m "$(cat <<'EOF'
feat(web/api): add character_type helper for account payload

Maps typeclass path → "PC" | "GM" | "STAFF" for the upcoming
available_characters payload field. Future typeclasses plug into
TYPECLASS_TO_CHARACTER_TYPE.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Add `PersonaPayloadSerializer` for the personas list

**Files:**
- Modify: `src/web/api/serializers.py` (add new serializer class)
- Test: `src/web/tests/test_account_player_serializer_personas.py`

**Goal:** Serialize a single Persona instance to `{ id, name, persona_type, display_name }`. PRIMARY + ESTABLISHED only — TEMPORARY excluded by upstream filtering.

**Step 1: Write the failing test**

```python
# src/web/tests/test_account_player_serializer_personas.py
"""Tests for PersonaPayloadSerializer used in the account payload."""

from django.test import TestCase

from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import PersonaType
from world.scenes.models import Persona
from web.api.serializers import PersonaPayloadSerializer


class PersonaPayloadSerializerTests(TestCase):
    """Serializer should expose only the fields the frontend needs."""

    def test_serializes_primary_persona(self) -> None:
        sheet = CharacterSheetFactory()
        primary = sheet.primary_persona
        data = PersonaPayloadSerializer(primary).data
        assert data == {
            "id": primary.id,
            "name": primary.name,
            "persona_type": "primary",
            "display_name": primary.name,
        }

    def test_serializes_established_persona(self) -> None:
        sheet = CharacterSheetFactory()
        established = Persona.objects.create(
            character_sheet=sheet,
            name="Hooded Stranger",
            persona_type=PersonaType.ESTABLISHED,
        )
        data = PersonaPayloadSerializer(established).data
        assert data["persona_type"] == "established"
        assert data["name"] == "Hooded Stranger"
        assert data["id"] == established.id
```

**Step 2: Run test (expect failure)**

Run: `echo "yes" | uv run arx test web.tests.test_account_player_serializer_personas --keepdb`
Expected: ImportError for `PersonaPayloadSerializer`

**Step 3: Write minimal implementation**

Add to `src/web/api/serializers.py`:

```python
from world.scenes.models import Persona


class PersonaPayloadSerializer(serializers.ModelSerializer):
    """Persona entry inside the account payload's available_characters."""

    display_name = serializers.SerializerMethodField()

    def get_display_name(self, obj: Persona) -> str:
        # Currently identical to name; reserved for future formatting (color codes, titles, etc.)
        return obj.name

    class Meta:
        model = Persona
        fields = ["id", "name", "persona_type", "display_name"]
```

**Step 4: Run test (expect pass)**

Run: `echo "yes" | uv run arx test web.tests.test_account_player_serializer_personas --keepdb`
Expected: 2 tests pass

**Step 5: Commit**

```bash
git -C /c/Users/apost/PycharmProjects/arxii add src/web/api/serializers.py src/web/tests/test_account_player_serializer_personas.py
git -C /c/Users/apost/PycharmProjects/arxii commit -m "$(cat <<'EOF'
feat(web/api): add PersonaPayloadSerializer for account payload

Exposes id, name, persona_type, display_name for use in the upcoming
available_characters list. display_name is currently identical to name
but reserved for future formatting (color codes, titles).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Add `AvailableCharacterSerializer`

**Files:**
- Modify: `src/web/api/serializers.py` (add new serializer class)
- Test: `src/web/tests/test_account_player_serializer_available_chars.py`

**Goal:** Serialize a `RosterEntry` (representing one of the account's active characters) into the shape:

```ts
{
  id: number;            // ObjectDB id of the character
  name: string;
  portrait_url: string | null;
  character_type: "PC" | "GM" | "STAFF";
  roster_status: string;  // e.g. "Active"
  personas: Persona[];    // PRIMARY + ESTABLISHED, ordered PRIMARY first
  last_location: { id; name } | null;
  currently_puppeted_in_session: bool;
}
```

**Design notes:**
- Input instance is a `RosterEntry` (one per character on the account's active tenures).
- `id` is `roster_entry.character_sheet.character.id` — the ObjectDB id, which is what the frontend uses to puppet via `@ic`.
- `portrait_url` comes from `roster_entry.profile_picture.cloudinary_url` if `profile_picture` is set, else `None`.
- `personas` is the character_sheet's personas filtered to `PRIMARY + ESTABLISHED`, ordered with PRIMARY first then ESTABLISHED by `created_at`.
- `last_location` reads `character.location` (Evennia ObjectDB FK). Serialize as `{id, name}` if set, else `None`.
- `currently_puppeted_in_session` requires a queryset-level annotation OR access to the request's user's `get_puppeted_characters()`. Pass via serializer context: `context["puppeted_character_ids"]: set[int]`.

**Step 1: Write the failing test**

```python
# src/web/tests/test_account_player_serializer_available_chars.py
"""Tests for AvailableCharacterSerializer used in the account payload."""

from django.test import TestCase

from evennia_extensions.factories import (
    AccountFactory,
    CharacterFactory,
    GMCharacterFactory,
    StaffCharacterFactory,
)
from world.character_sheets.factories import CharacterSheetFactory
from world.scenes.constants import PersonaType
from world.scenes.models import Persona
from world.roster.factories import (
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models import RosterType
from web.api.serializers import AvailableCharacterSerializer


class AvailableCharacterSerializerTests(TestCase):
    """RosterEntry → AvailableCharacter payload entry."""

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.active_roster = RosterFactory(name=RosterType.ACTIVE)

    def _make_entry(self, character_factory=CharacterFactory) -> tuple:
        """Build an account → tenure → entry → sheet → character chain."""
        character = character_factory()
        sheet = CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet=sheet, roster=self.active_roster)
        RosterTenureFactory(
            player_data=self.account.player_data,
            roster_entry=entry,
        )
        return entry, sheet, character

    def test_basic_pc_payload(self) -> None:
        entry, sheet, character = self._make_entry()
        data = AvailableCharacterSerializer(
            entry, context={"puppeted_character_ids": set()}
        ).data
        assert data["id"] == character.id
        assert data["name"] == character.key
        assert data["character_type"] == "PC"
        assert data["roster_status"] == RosterType.ACTIVE
        assert data["currently_puppeted_in_session"] is False

    def test_gm_character_payload(self) -> None:
        entry, _sheet, _char = self._make_entry(character_factory=GMCharacterFactory)
        data = AvailableCharacterSerializer(
            entry, context={"puppeted_character_ids": set()}
        ).data
        assert data["character_type"] == "GM"

    def test_staff_character_payload(self) -> None:
        entry, _sheet, _char = self._make_entry(character_factory=StaffCharacterFactory)
        data = AvailableCharacterSerializer(
            entry, context={"puppeted_character_ids": set()}
        ).data
        assert data["character_type"] == "STAFF"

    def test_personas_excludes_temporary(self) -> None:
        entry, sheet, _char = self._make_entry()
        # Sheet already has PRIMARY (auto-created via factory)
        Persona.objects.create(
            character_sheet=sheet,
            name="Hooded Stranger",
            persona_type=PersonaType.ESTABLISHED,
        )
        Persona.objects.create(
            character_sheet=sheet,
            name="Disguise",
            persona_type=PersonaType.TEMPORARY,
        )
        data = AvailableCharacterSerializer(
            entry, context={"puppeted_character_ids": set()}
        ).data
        persona_types = [p["persona_type"] for p in data["personas"]]
        assert "temporary" not in persona_types
        assert persona_types[0] == "primary"
        assert "established" in persona_types

    def test_currently_puppeted_flag(self) -> None:
        entry, _sheet, character = self._make_entry()
        data = AvailableCharacterSerializer(
            entry, context={"puppeted_character_ids": {character.id}}
        ).data
        assert data["currently_puppeted_in_session"] is True

    def test_last_location_when_set(self) -> None:
        entry, _sheet, character = self._make_entry()
        from evennia.utils.create import create_object
        room = create_object(
            "typeclasses.rooms.Room", key="Throne Room", nohome=True, nolocation=True
        )
        character.location = room
        character.save()
        data = AvailableCharacterSerializer(
            entry, context={"puppeted_character_ids": set()}
        ).data
        assert data["last_location"] == {"id": room.id, "name": "Throne Room"}

    def test_last_location_when_unset(self) -> None:
        entry, _sheet, character = self._make_entry()
        character.location = None
        character.save()
        data = AvailableCharacterSerializer(
            entry, context={"puppeted_character_ids": set()}
        ).data
        assert data["last_location"] is None

    def test_portrait_url_when_unset(self) -> None:
        entry, _sheet, _char = self._make_entry()
        data = AvailableCharacterSerializer(
            entry, context={"puppeted_character_ids": set()}
        ).data
        assert data["portrait_url"] is None
```

**Step 2: Run test (expect failure)**

Run: `echo "yes" | uv run arx test web.tests.test_account_player_serializer_available_chars --keepdb`
Expected: ImportError for `AvailableCharacterSerializer`

**Note for the implementer:** Before continuing, verify `RosterEntryFactory`, `RosterTenureFactory`, `RosterFactory` exist in `src/world/roster/factories.py`. If they don't exist or have a different API, adapt the test setUp accordingly — but don't change the assertions.

**Step 3: Write minimal implementation**

Add to `src/web/api/serializers.py`:

```python
from world.scenes.constants import PersonaType
from world.roster.models import RosterEntry
from web.api.character_type import derive_character_type


class AvailableCharacterSerializer(serializers.Serializer):
    """An entry in the account payload's available_characters list.

    Input: a RosterEntry. Context must provide `puppeted_character_ids: set[int]`.
    """

    id = serializers.SerializerMethodField()
    name = serializers.SerializerMethodField()
    portrait_url = serializers.SerializerMethodField()
    character_type = serializers.SerializerMethodField()
    roster_status = serializers.CharField(source="roster.name", read_only=True)
    personas = serializers.SerializerMethodField()
    last_location = serializers.SerializerMethodField()
    currently_puppeted_in_session = serializers.SerializerMethodField()

    def get_id(self, obj: RosterEntry) -> int:
        return obj.character_sheet.character.id

    def get_name(self, obj: RosterEntry) -> str:
        return obj.character_sheet.character.key

    def get_portrait_url(self, obj: RosterEntry) -> str | None:
        if obj.profile_picture is None:
            return None
        return obj.profile_picture.cloudinary_url

    def get_character_type(self, obj: RosterEntry) -> str:
        return derive_character_type(obj.character_sheet.character)

    def get_personas(self, obj: RosterEntry) -> list[dict]:
        personas = (
            obj.character_sheet.personas
            .filter(persona_type__in=[PersonaType.PRIMARY, PersonaType.ESTABLISHED])
            .order_by("persona_type", "created_at")
        )
        # PRIMARY sorts before ESTABLISHED alphabetically ("e" < "p"), so reverse:
        # Actually we want PRIMARY first then ESTABLISHED ordered by created_at.
        primary = personas.filter(persona_type=PersonaType.PRIMARY)
        established = personas.filter(persona_type=PersonaType.ESTABLISHED).order_by(
            "created_at"
        )
        ordered = list(primary) + list(established)
        return PersonaPayloadSerializer(ordered, many=True).data

    def get_last_location(self, obj: RosterEntry) -> dict | None:
        location = obj.character_sheet.character.location
        if location is None:
            return None
        return {"id": location.id, "name": location.key}

    def get_currently_puppeted_in_session(self, obj: RosterEntry) -> bool:
        puppeted_ids = self.context.get("puppeted_character_ids", set())
        return obj.character_sheet.character.id in puppeted_ids
```

**Step 4: Run test (expect pass)**

Run: `echo "yes" | uv run arx test web.tests.test_account_player_serializer_available_chars --keepdb`
Expected: 8 tests pass

**Step 5: Commit**

```bash
git -C /c/Users/apost/PycharmProjects/arxii add src/web/api/serializers.py src/web/tests/test_account_player_serializer_available_chars.py
git -C /c/Users/apost/PycharmProjects/arxii commit -m "$(cat <<'EOF'
feat(web/api): add AvailableCharacterSerializer

Serializes a RosterEntry into the shape consumed by the upcoming
character portrait grid: id, name, portrait_url, character_type,
roster_status, personas (PRIMARY + ESTABLISHED only), last_location,
currently_puppeted_in_session.

The puppeted_character_ids set is passed via serializer context to
avoid querying account.get_puppeted_characters() per row.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Add `PendingApplicationSerializer`

**Files:**
- Modify: `src/web/api/serializers.py` (add new serializer)
- Test: `src/web/tests/test_account_player_serializer_pending_apps.py`

**Goal:** Serialize a `RosterApplication` to `{ id, character_name, status, applied_date }`. Filter to `status == PENDING` is upstream's responsibility.

**Step 1: Write the failing test**

```python
# src/web/tests/test_account_player_serializer_pending_apps.py
"""Tests for PendingApplicationSerializer."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.roster.models import ApplicationStatus, RosterApplication
from web.api.serializers import PendingApplicationSerializer


class PendingApplicationSerializerTests(TestCase):
    def test_serializes_pending_application(self) -> None:
        account = AccountFactory()
        character = CharacterFactory(key="Lyra")
        app = RosterApplication.objects.create(
            player_data=account.player_data,
            character=character,
            application_text="please",
            status=ApplicationStatus.PENDING,
        )
        data = PendingApplicationSerializer(app).data
        assert data["id"] == app.id
        assert data["character_name"] == "Lyra"
        assert data["status"] == "pending"
        assert data["applied_date"] is not None
```

**Step 2: Run test (expect failure)**

Run: `echo "yes" | uv run arx test web.tests.test_account_player_serializer_pending_apps --keepdb`
Expected: ImportError

**Step 3: Write minimal implementation**

Add to `src/web/api/serializers.py`:

```python
from world.roster.models import RosterApplication


class PendingApplicationSerializer(serializers.ModelSerializer):
    """Pending RosterApplication entry for the account payload."""

    character_name = serializers.CharField(source="character.key", read_only=True)

    class Meta:
        model = RosterApplication
        fields = ["id", "character_name", "status", "applied_date"]
```

**Step 4: Run test (expect pass)**

Run: `echo "yes" | uv run arx test web.tests.test_account_player_serializer_pending_apps --keepdb`
Expected: 1 test passes

**Step 5: Commit**

```bash
git -C /c/Users/apost/PycharmProjects/arxii add src/web/api/serializers.py src/web/tests/test_account_player_serializer_pending_apps.py
git -C /c/Users/apost/PycharmProjects/arxii commit -m "$(cat <<'EOF'
feat(web/api): add PendingApplicationSerializer

Serializes a RosterApplication to id, character_name, status,
applied_date for the account payload's pending_applications list.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: Extend `AccountPlayerSerializer` with new fields

**Files:**
- Modify: `src/web/api/serializers.py` (extend existing AccountPlayerSerializer)
- Test: `src/web/tests/test_account_player_serializer_full_payload.py`

**Goal:** Wire `available_characters` and `pending_applications` into the existing `AccountPlayerSerializer`. Filter `available_characters` to `roster.name == RosterType.ACTIVE` only. Build `puppeted_character_ids` once and pass via context.

**Step 1: Write the failing test**

```python
# src/web/tests/test_account_player_serializer_full_payload.py
"""End-to-end payload tests for AccountPlayerSerializer."""

from django.test import TestCase

from evennia_extensions.factories import AccountFactory, CharacterFactory
from world.character_sheets.factories import CharacterSheetFactory
from world.roster.factories import (
    RosterEntryFactory,
    RosterFactory,
    RosterTenureFactory,
)
from world.roster.models import ApplicationStatus, RosterApplication, RosterType
from web.api.serializers import AccountPlayerSerializer


class AccountPlayerSerializerFullPayloadTests(TestCase):
    """The /api/user/ payload should include character + application data."""

    def setUp(self) -> None:
        self.account = AccountFactory()
        self.active_roster = RosterFactory(name=RosterType.ACTIVE)
        self.inactive_roster = RosterFactory(name=RosterType.INACTIVE)

    def _add_active_character(self, key: str = "Bob") -> None:
        character = CharacterFactory(key=key)
        sheet = CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet=sheet, roster=self.active_roster)
        RosterTenureFactory(
            player_data=self.account.player_data, roster_entry=entry
        )

    def _add_inactive_character(self, key: str = "Old Hero") -> None:
        character = CharacterFactory(key=key)
        sheet = CharacterSheetFactory(character=character)
        entry = RosterEntryFactory(character_sheet=sheet, roster=self.inactive_roster)
        RosterTenureFactory(
            player_data=self.account.player_data, roster_entry=entry
        )

    def test_payload_includes_active_character(self) -> None:
        self._add_active_character("Bob")
        data = AccountPlayerSerializer(self.account).data
        names = [c["name"] for c in data["available_characters"]]
        assert "Bob" in names

    def test_payload_excludes_inactive_character(self) -> None:
        self._add_active_character("Bob")
        self._add_inactive_character("Old Hero")
        data = AccountPlayerSerializer(self.account).data
        names = [c["name"] for c in data["available_characters"]]
        assert "Old Hero" not in names
        assert "Bob" in names

    def test_payload_pending_applications(self) -> None:
        target = CharacterFactory(key="Lyra")
        RosterApplication.objects.create(
            player_data=self.account.player_data,
            character=target,
            application_text="please",
            status=ApplicationStatus.PENDING,
        )
        # Approved application should NOT appear:
        approved_target = CharacterFactory(key="Maeve")
        RosterApplication.objects.create(
            player_data=self.account.player_data,
            character=approved_target,
            application_text="please",
            status=ApplicationStatus.APPROVED,
        )
        data = AccountPlayerSerializer(self.account).data
        app_names = [a["character_name"] for a in data["pending_applications"]]
        assert app_names == ["Lyra"]

    def test_payload_no_characters(self) -> None:
        data = AccountPlayerSerializer(self.account).data
        assert data["available_characters"] == []
        assert data["pending_applications"] == []

    def test_existing_fields_unchanged(self) -> None:
        """Regression: existing fields must still be present."""
        data = AccountPlayerSerializer(self.account).data
        for field in [
            "id", "username", "display_name", "last_login", "email",
            "email_verified", "can_create_characters", "is_staff", "avatar_url",
        ]:
            assert field in data, f"missing existing field: {field}"
```

**Step 2: Run test (expect failure)**

Run: `echo "yes" | uv run arx test web.tests.test_account_player_serializer_full_payload --keepdb`
Expected: KeyError on `available_characters` or similar — fields don't exist yet

**Step 3: Write minimal implementation**

Modify `AccountPlayerSerializer` in `src/web/api/serializers.py`:

```python
from world.roster.models import ApplicationStatus, RosterEntry, RosterType


class AccountPlayerSerializer(serializers.ModelSerializer):
    """Serialize account and player display information."""

    display_name = serializers.CharField(
        source="player_data.display_name",
        read_only=True,
    )
    email_verified = serializers.SerializerMethodField()
    can_create_characters = serializers.SerializerMethodField()
    is_staff = serializers.BooleanField(read_only=True)
    avatar_url = serializers.SerializerMethodField()
    available_characters = serializers.SerializerMethodField()
    pending_applications = serializers.SerializerMethodField()

    def get_email_verified(self, obj):
        try:
            email_address = EmailAddress.objects.get(user=obj, primary=True)
            return email_address.verified
        except EmailAddress.DoesNotExist:
            return False

    def get_can_create_characters(self, obj):
        return obj.player_data.can_apply_for_characters()

    def get_avatar_url(self, obj):
        return obj.player_data.avatar_url

    def get_available_characters(self, obj) -> list[dict]:
        puppeted_ids = {char.id for char in obj.get_puppeted_characters()}
        # ACTIVE roster entries owned by this account via current tenures
        entries = (
            RosterEntry.objects
            .filter(
                tenures__player_data=obj.player_data,
                tenures__end_date__isnull=True,
                roster__name=RosterType.ACTIVE,
            )
            .distinct()
            .select_related("roster", "character_sheet", "profile_picture")
        )
        return AvailableCharacterSerializer(
            entries,
            many=True,
            context={"puppeted_character_ids": puppeted_ids},
        ).data

    def get_pending_applications(self, obj) -> list[dict]:
        apps = RosterApplication.objects.filter(
            player_data=obj.player_data,
            status=ApplicationStatus.PENDING,
        ).select_related("character")
        return PendingApplicationSerializer(apps, many=True).data

    class Meta:
        model = AccountDB
        fields = [
            "id",
            "username",
            "display_name",
            "last_login",
            "email",
            "email_verified",
            "can_create_characters",
            "is_staff",
            "avatar_url",
            "available_characters",
            "pending_applications",
        ]
```

**Note for implementer:** The exact filter on `tenures__end_date__isnull=True` may need adjusting based on the `RosterTenure` model — check the model to confirm the "current tenure" predicate. If RosterTenure uses a different "current" indicator (e.g., `is_current`), use that instead. Verify by reading `src/world/roster/models/tenures.py`.

**Step 4: Run test (expect pass)**

Run: `echo "yes" | uv run arx test web.tests.test_account_player_serializer_full_payload --keepdb`
Expected: 5 tests pass

**Step 5: Verify existing tests still pass**

Run: `echo "yes" | uv run arx test web.tests.test_email_verification_blocking --keepdb`
Expected: All existing serializer tests pass

**Step 6: Commit**

```bash
git -C /c/Users/apost/PycharmProjects/arxii add src/web/api/serializers.py src/web/tests/test_account_player_serializer_full_payload.py
git -C /c/Users/apost/PycharmProjects/arxii commit -m "$(cat <<'EOF'
feat(web/api): expose available_characters + pending_applications in account payload

Wires AvailableCharacterSerializer and PendingApplicationSerializer
into AccountPlayerSerializer. Filters available_characters to ACTIVE
roster entries only — Inactive/Frozen/Available characters are not
exposed in this pass. The puppeted_character_ids set is computed once
per request and passed via serializer context.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: Add `WebsocketMessageType.PUPPET_CHANGED`

**Files:**
- Modify: `src/web/webclient/message_types.py`
- Test: extend an existing message_types test if any, or add `src/web/tests/test_message_types.py`

**Goal:** Add a new enum entry so the webclient and broadcaster agree on the message type string.

**Step 1: Write the failing test**

```python
# src/web/tests/test_message_types.py
"""Tests for WebsocketMessageType enum coverage."""

from django.test import TestCase

from web.webclient.message_types import WebsocketMessageType


class WebsocketMessageTypeTests(TestCase):
    def test_puppet_changed_exists(self) -> None:
        assert WebsocketMessageType.PUPPET_CHANGED.value == "puppet_changed"
```

**Step 2: Run test (expect failure)**

Run: `echo "yes" | uv run arx test web.tests.test_message_types --keepdb`
Expected: AttributeError on `PUPPET_CHANGED`

**Step 3: Write minimal implementation**

Edit `src/web/webclient/message_types.py`:

```python
class WebsocketMessageType(str, Enum):
    """Supported websocket message types."""

    TEXT = "text"
    LOGGED_IN = "logged_in"
    VN_MESSAGE = "vn_message"
    MESSAGE_REACTION = "message_reaction"
    COMMANDS = "commands"
    ROOM_STATE = "room_state"
    SCENE = "scene"
    COMMAND_ERROR = "command_error"
    PUPPET_CHANGED = "puppet_changed"  # NEW
```

**Step 4: Run test (expect pass)**

Run: `echo "yes" | uv run arx test web.tests.test_message_types --keepdb`
Expected: 1 test passes

**Step 5: Commit**

```bash
git -C /c/Users/apost/PycharmProjects/arxii add src/web/webclient/message_types.py src/web/tests/test_message_types.py
git -C /c/Users/apost/PycharmProjects/arxii commit -m "$(cat <<'EOF'
feat(web/webclient): add PUPPET_CHANGED message type

Used by Account.puppet_character_in_session and unpuppet_object
overrides to broadcast puppet state changes to all of an account's
sessions, so other tabs can update their portrait-grid indicators.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 7: Broadcast `puppet_changed` from `puppet_character_in_session`

**Files:**
- Modify: `src/typeclasses/accounts.py`
- Test: `src/typeclasses/tests/test_account_puppet_broadcast.py`

**Goal:** When `Account.puppet_character_in_session` succeeds, broadcast a `puppet_changed` event to all of the account's sessions so other tabs can update their state.

**Broadcast payload:**

```python
sess.msg(
    type="puppet_changed",
    args=[{
        "session_id": session.sessid,
        "character_id": character.id,
        "character_name": character.key,
    }],
)
```

`session.sessid` identifies which tab/session changed. `character_id` and `character_name` describe the new puppet (or `None` for unpuppet — handled in Task 8).

**Step 1: Write the failing test**

```python
# src/typeclasses/tests/test_account_puppet_broadcast.py
"""Tests for Account puppet_changed broadcast on @ic swaps."""

from unittest.mock import MagicMock

from evennia.utils.test_resources import EvenniaTest

from evennia_extensions.factories import AccountFactory, CharacterFactory


class PuppetCharacterBroadcastTests(EvenniaTest):
    """puppet_character_in_session should broadcast puppet_changed to all sessions."""

    def setUp(self) -> None:
        super().setUp()
        self.account = AccountFactory()
        self.character = CharacterFactory()
        # Grant the account access to the character via roster setup if needed
        # (use existing factory helper from world.roster.factories)
        from world.roster.factories import (
            RosterEntryFactory,
            RosterFactory,
            RosterTenureFactory,
        )
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.models import RosterType

        sheet = CharacterSheetFactory(character=self.character)
        entry = RosterEntryFactory(
            character_sheet=sheet,
            roster=RosterFactory(name=RosterType.ACTIVE),
        )
        RosterTenureFactory(
            player_data=self.account.player_data,
            roster_entry=entry,
        )

    def test_puppet_swap_broadcasts_to_all_sessions(self) -> None:
        sess1 = MagicMock(sessid=10, puppet=None)
        sess2 = MagicMock(sessid=11, puppet=None)
        self.account.sessions.all = lambda: [sess1, sess2]

        success, _msg = self.account.puppet_character_in_session(self.character, sess1)
        assert success

        # Both sessions should have received a puppet_changed message
        for sess in (sess1, sess2):
            puppet_calls = [
                call for call in sess.msg.call_args_list
                if call.kwargs.get("type") == "puppet_changed"
            ]
            assert len(puppet_calls) >= 1, f"sess {sess.sessid} got no puppet_changed"
            payload = puppet_calls[0].kwargs["args"][0]
            assert payload["session_id"] == 10
            assert payload["character_id"] == self.character.id
            assert payload["character_name"] == self.character.key

    def test_failed_puppet_does_not_broadcast(self) -> None:
        # Simulate already-puppeted-elsewhere — character can't be re-puppeted
        sess1 = MagicMock(sessid=10, puppet=None)
        self.account.sessions.all = lambda: [sess1]
        # Force can_puppet_character to return False
        self.account.can_puppet_character = lambda c: (False, "nope")
        success, _msg = self.account.puppet_character_in_session(self.character, sess1)
        assert not success
        puppet_calls = [
            call for call in sess1.msg.call_args_list
            if call.kwargs.get("type") == "puppet_changed"
        ]
        assert puppet_calls == []
```

**Step 2: Run test (expect failure)**

Run: `echo "yes" | uv run arx test typeclasses.tests.test_account_puppet_broadcast --keepdb`
Expected: AssertionError "got no puppet_changed"

**Step 3: Write minimal implementation**

Edit `src/typeclasses/accounts.py`. Add a helper method and call it after a successful puppet:

```python
def _broadcast_puppet_changed(self, session, character) -> None:
    """Notify all of this account's sessions that a puppet swap occurred.

    Other tabs/sessions use this to update their portrait-grid indicators
    (e.g., "currently puppeted in another session" badge).
    """
    payload = {
        "session_id": session.sessid,
        "character_id": character.id if character else None,
        "character_name": character.key if character else None,
    }
    for sess in self.sessions.all():
        sess.msg(type="puppet_changed", args=[payload])

def puppet_character_in_session(self, character, session):
    """Puppet a character in a specific session."""
    can_puppet, reason = self.can_puppet_character(character)
    if not can_puppet:
        return False, reason

    if session.puppet:
        session.msg(f"Switching from {session.puppet.name} to {character.name}.")
        self.unpuppet_object(session)

    self.puppet_object(session, character)
    self._broadcast_puppet_changed(session, character)
    return True, f"Now controlling {character.name}."
```

**Step 4: Run test (expect pass)**

Run: `echo "yes" | uv run arx test typeclasses.tests.test_account_puppet_broadcast --keepdb`
Expected: 2 tests pass

**Step 5: Commit**

```bash
git -C /c/Users/apost/PycharmProjects/arxii add src/typeclasses/accounts.py src/typeclasses/tests/test_account_puppet_broadcast.py
git -C /c/Users/apost/PycharmProjects/arxii commit -m "$(cat <<'EOF'
feat(typeclasses): broadcast puppet_changed from puppet_character_in_session

After a successful @ic swap, fan out a puppet_changed message to every
session on the account so other tabs/windows can update their
portrait-grid indicators in real time.

Failed swaps (permission denied, character in use elsewhere) do not
broadcast.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 8: Broadcast `puppet_changed` on disconnect-driven unpuppets

**Files:**
- Modify: `src/typeclasses/accounts.py`
- Test: extend `src/typeclasses/tests/test_account_puppet_broadcast.py`

**Goal:** When an Evennia session disconnects (browser tab closes, telnet quits), the puppet on that session is released. Other tabs need to know so their "currently puppeted in another session" indicator clears.

**Approach:** Override `unpuppet_object` on `Account`. Capture the character that was puppeted before delegating to the parent class, then broadcast `puppet_changed` with `character_id=None` for the affected session.

**Step 1: Write the failing test (extend existing file)**

Add to `src/typeclasses/tests/test_account_puppet_broadcast.py`:

```python
class UnpuppetBroadcastTests(EvenniaTest):
    """unpuppet_object should broadcast puppet_changed to all sessions."""

    def setUp(self) -> None:
        super().setUp()
        self.account = AccountFactory()
        self.character = CharacterFactory()
        # ... (same setup as PuppetCharacterBroadcastTests) ...
        from world.roster.factories import (
            RosterEntryFactory,
            RosterFactory,
            RosterTenureFactory,
        )
        from world.character_sheets.factories import CharacterSheetFactory
        from world.roster.models import RosterType

        sheet = CharacterSheetFactory(character=self.character)
        entry = RosterEntryFactory(
            character_sheet=sheet,
            roster=RosterFactory(name=RosterType.ACTIVE),
        )
        RosterTenureFactory(
            player_data=self.account.player_data,
            roster_entry=entry,
        )

    def test_unpuppet_broadcasts_with_null_character(self) -> None:
        sess1 = MagicMock(sessid=10)
        sess1.puppet = self.character
        sess2 = MagicMock(sessid=11, puppet=None)
        self.account.sessions.all = lambda: [sess1, sess2]

        self.account.unpuppet_object(sess1)

        for sess in (sess1, sess2):
            puppet_calls = [
                call for call in sess.msg.call_args_list
                if call.kwargs.get("type") == "puppet_changed"
            ]
            assert len(puppet_calls) >= 1, f"sess {sess.sessid} got no puppet_changed"
            payload = puppet_calls[-1].kwargs["args"][0]
            assert payload["session_id"] == 10
            assert payload["character_id"] is None
            assert payload["character_name"] is None
```

**Step 2: Run test (expect failure)**

Run: `echo "yes" | uv run arx test typeclasses.tests.test_account_puppet_broadcast --keepdb`
Expected: New test fails — no broadcast on unpuppet

**Step 3: Write minimal implementation**

Edit `src/typeclasses/accounts.py` to override `unpuppet_object`:

```python
def unpuppet_object(self, session) -> None:
    """Unpuppet a character from a session and broadcast the change.

    Triggered both by explicit @ic swaps (which call this internally before
    re-puppeting) and by session disconnects (browser tab close, telnet quit).
    Broadcasting on every unpuppet keeps other tabs' portrait-grid state
    consistent without requiring a refresh.
    """
    super().unpuppet_object(session)
    self._broadcast_puppet_changed(session, character=None)
```

**Step 4: Run test (expect pass)**

Run: `echo "yes" | uv run arx test typeclasses.tests.test_account_puppet_broadcast --keepdb`
Expected: 3 tests pass total

**Step 5: Commit**

```bash
git -C /c/Users/apost/PycharmProjects/arxii add src/typeclasses/accounts.py src/typeclasses/tests/test_account_puppet_broadcast.py
git -C /c/Users/apost/PycharmProjects/arxii commit -m "$(cat <<'EOF'
feat(typeclasses): broadcast puppet_changed on session unpuppet

Override unpuppet_object to fan out a puppet_changed event with
character_id=None whenever a session releases its puppet. Triggered by
@ic swap (which unpuppets before re-puppeting) and by disconnect-driven
unpuppets (browser tab close, telnet quit).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 9: Update frontend `AccountData` types

**Files:**
- Modify: `frontend/src/evennia_replacements/types.ts`

**Goal:** Mirror the backend payload shape in TypeScript so existing call sites continue to type-check, and 6b can build on the new fields.

**Step 1: No failing test — type changes only**

(`pnpm typecheck` is the verification.)

**Step 2: Edit the file**

Replace the `AccountData` interface and add the new types:

```typescript
export interface PersonaPayload {
  id: number;
  name: string;
  persona_type: 'primary' | 'established';
  display_name: string;
}

export interface AvailableCharacter {
  id: number;
  name: string;
  portrait_url: string | null;
  character_type: 'PC' | 'GM' | 'STAFF';
  roster_status: string;
  personas: PersonaPayload[];
  last_location: { id: number; name: string } | null;
  currently_puppeted_in_session: boolean;
}

export interface PendingApplication {
  id: number;
  character_name: string;
  status: 'pending';
  applied_date: string;
}

export interface AccountData {
  id: number;
  username: string;
  display_name: string;
  last_login: string | null;
  email: string;
  email_verified: boolean;
  can_create_characters: boolean;
  is_staff: boolean;
  avatar_url?: string;
  available_characters: AvailableCharacter[];
  pending_applications: PendingApplication[];
}
```

**Step 3: Verify**

Run from the `frontend/` directory:
```bash
pnpm typecheck
```
Expected: Type-check passes. If existing call sites consume new fields and fail, that's a 6b problem — for 6a, only ensure no existing code regressed.

**Step 4: Commit**

```bash
git -C /c/Users/apost/PycharmProjects/arxii add frontend/src/evennia_replacements/types.ts
git -C /c/Users/apost/PycharmProjects/arxii commit -m "$(cat <<'EOF'
feat(frontend/types): mirror new AccountData fields from Phase 6a backend

Adds AvailableCharacter, PersonaPayload, PendingApplication interfaces.
Existing code paths unchanged — 6b will consume these in the portrait
grid component.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 10: Add `WS_MESSAGE_TYPE.PUPPET_CHANGED` to frontend

**Files:**
- Modify: `frontend/src/hooks/types.ts`

**Goal:** Mirror the backend `WebsocketMessageType.PUPPET_CHANGED` so 6b's WS handler can match on it.

**Step 1: Edit**

Add `PUPPET_CHANGED: 'puppet_changed',` to the `WS_MESSAGE_TYPE` const:

```typescript
export const WS_MESSAGE_TYPE = {
  TEXT: 'text',
  LOGGED_IN: 'logged_in',
  VN_MESSAGE: 'vn_message',
  MESSAGE_REACTION: 'message_reaction',
  COMMANDS: 'commands',
  ROOM_STATE: 'room_state',
  SCENE: 'scene',
  COMMAND_ERROR: 'command_error',
  ROULETTE_RESULT: 'roulette_result',
  INTERACTION: 'interaction',
  PUPPET_CHANGED: 'puppet_changed',
} as const;
```

**Step 2: Verify**

Run from `frontend/`:
```bash
pnpm typecheck
```
Expected: Pass.

**Step 3: Commit**

```bash
git -C /c/Users/apost/PycharmProjects/arxii add frontend/src/hooks/types.ts
git -C /c/Users/apost/PycharmProjects/arxii commit -m "$(cat <<'EOF'
feat(frontend/hooks): add PUPPET_CHANGED to WS_MESSAGE_TYPE enum

Mirrors backend WebsocketMessageType.PUPPET_CHANGED so 6b's portrait
grid can match on incoming events.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 11: Lint, full regression, and CI-parity sweep

**Goal:** Catch regressions before pushing. Per CLAUDE.md: run all affected test suites, then run a full no-`--keepdb` sweep to match CI.

**Step 1: Lint**

```bash
just lint
```
Expected: No errors. Fix any violations.

**Step 2: Targeted test suites**

```bash
echo "yes" | uv run arx test web typeclasses --keepdb
```
Expected: All tests pass.

**Step 3: Frontend type-check + lint**

From `frontend/`:
```bash
pnpm typecheck
pnpm lint
```
Expected: No errors.

**Step 4: Full no-`--keepdb` regression**

```bash
echo "yes" | uv run arx test
```
Expected: All tests pass on a fresh DB.

**Step 5: If anything fails**

- DB-related migrations issue → check the failing test's setUp; ensure factories pass `nohome=True`/`nolocation=True` where needed
- Serializer N+1 warning → add `select_related` / `Prefetch(to_attr=...)` per project conventions
- Existing test broken by AccountPlayerSerializer changes → update the test to pass through the new fields (don't strip them)

**Step 6: Final commit (if any fixes were needed)**

```bash
git -C /c/Users/apost/PycharmProjects/arxii add -A
git -C /c/Users/apost/PycharmProjects/arxii commit -m "$(cat <<'EOF'
fix: regression sweep cleanup for Phase 6a

Captures any small fixes surfaced during full-suite no-keepdb run.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

If no fixes needed, skip this step.

---

## Definition of Done

- `/api/user/` (`CurrentUserAPIView`) returns:
  - All previously-existing fields unchanged
  - `available_characters: AvailableCharacter[]` — ACTIVE roster characters only, with full payload (portrait, type, status, personas, last_location, in-use flag)
  - `pending_applications: PendingApplication[]` — `RosterApplication` rows with `status=PENDING`
- `Account.puppet_character_in_session` broadcasts `puppet_changed` to all sessions on success
- `Account.unpuppet_object` broadcasts `puppet_changed` (with null character) on session disconnect
- Frontend types mirror the new payload shape; `WS_MESSAGE_TYPE.PUPPET_CHANGED` exists
- All existing tests pass; new tests pass; full no-`--keepdb` regression passes; `pnpm typecheck` and `pnpm lint` clean

## Out of Scope (deferred to 6b / 6c)

- Character portrait grid UI component
- Tab-scoped Redux slice for focused character / selected persona
- Header `CharacterChip` and switcher dropdown
- WS handler for `puppet_changed` in the frontend
- Replacing `gmPersonaId={0}` stubs (requires tab-scoped state)
- `<RoleRoute>` route guard
- Replacing per-page 403 fallbacks (`NotGMPage` etc.)
- NPC typeclass detection — none exists yet, deferred until needed
