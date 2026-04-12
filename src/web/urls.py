"""Project URL configuration."""

from django.urls import include, path, re_path

from web.views import FrontendAppView

urlpatterns = [
    path("api/", include("web.api.urls")),
    path("api/roster/", include("world.roster.urls")),
    path("api/character-creation/", include("world.character_creation.urls")),
    path("api/traits/", include("world.traits.urls")),
    path("api/magic/", include("world.magic.urls")),
    path("api/goals/", include("world.goals.urls")),
    path("api/conditions/", include("world.conditions.urls")),
    path("api/distinctions/", include("world.distinctions.urls")),
    path("api/skills/", include("world.skills.urls")),
    path("api/classes/", include("world.classes.urls")),
    path("api/items/", include("world.items.urls")),
    path("api/codex/", include("world.codex.urls")),
    path("api/character-sheets/", include("world.character_sheets.urls")),
    path("api/achievements/", include("world.achievements.urls")),
    path("api/journals/", include("world.journals.urls", namespace="journals")),
    path("api/clock/", include("world.game_clock.urls")),
    path("api/events/", include("world.events.urls")),
    path("api/combat/", include("world.combat.urls")),
    path("api/fatigue/", include("world.fatigue.urls")),
    path("api/areas/", include("world.areas.urls")),
    path("api/player-submissions/", include("world.player_submissions.urls")),
    path("api/staff-inbox/", include("world.staff_inbox.urls")),
    path("api/gm/", include("world.gm.urls")),
    path("", include("world.scenes.urls")),
    path("", include("world.stories.urls")),
    path("webclient/", include("web.webclient.urls")),
    path("admin/", include("web.admin.urls")),
    path("accounts/", include("allauth.urls")),
    # React frontend catch-all - must be last
    re_path(
        r"^(?!(?:admin(?:/|$)|api(?:/|$)|accounts(?:/|$)|webclient(?:/|$))).*$",
        FrontendAppView.as_view(),
        name="frontend-home",
    ),
]
