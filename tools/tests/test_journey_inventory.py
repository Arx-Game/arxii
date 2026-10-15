"""The inventory's source-text parsers read routes, routers and test mentions (#3657).

U-keep: parsers with branches over source text; no journey reaches tooling over text.
"""

from __future__ import annotations

from journey_inventory import (
    Surface,
    api_routes,
    frontend_routes,
    is_test_file,
    render,
    tests_mentioning as mentioning,
)


def test_frontend_routes_are_read_in_order_without_duplicates() -> None:
    text = """
      <Route path="/gm/dashboard" element={<A />} />
      <Route path="/tables" element={<B />} />
      <Route path="/gm/dashboard" element={<A />} />
    """
    assert frontend_routes(text) == ["/gm/dashboard", "/tables"]


def test_api_routes_read_router_registrations_and_path_views_but_not_includes() -> None:
    text = """
    router.register("tables", GMTableViewSet, basename="gm-table")
    router.register(r"prompts", GMPromptViewSet)
    urlpatterns = [
        path("", include(router.urls)),
        path("dashboard/", GMDashboardView.as_view(), name="gm-dashboard"),
        path("attention/", GMAttentionView.as_view(), name="gm-attention"),
    ]
    """
    rows = api_routes(text, "world.gm.urls")
    assert [(r.key, r.detail) for r in rows] == [
        ("tables/", "GMTableViewSet"),
        ("prompts/", "GMPromptViewSet"),
        ("dashboard/", "GMDashboardView"),
        ("attention/", "GMAttentionView"),
    ]
    assert all(r.where == "world.gm.urls" for r in rows)


def test_mentioning_matches_any_token_and_sorts() -> None:
    corpus = {
        "world/gm/tests/test_b.py": 'resp = self.client.get("/api/gm/attention/")',
        "world/gm/tests/test_a.py": "from world.gm.views import GMAttentionView",
        "world/gm/tests/test_c.py": "nothing here",
    }
    assert mentioning(("GMAttentionView", "/api/gm/attention"), corpus) == (
        "world/gm/tests/test_a.py",
        "world/gm/tests/test_b.py",
    )
    assert mentioning(("", "zzz"), corpus) == ()


def test_is_test_file_knows_both_test_homes() -> None:
    assert is_test_file("/world/gm/tests/test_x.py")
    assert is_test_file("/integration_tests/pipeline/test_y.py")
    assert not is_test_file("/world/gm/views.py")
    assert not is_test_file("/world/gm/tests/helpers.txt")


def test_render_counts_the_surfaces_no_test_names() -> None:
    actions = [
        Surface(
            "action",
            "look",
            "actions.definitions.perception.LookAction",
            "perception / single",
            ("a/tests/test_look.py",),
        ),
        Surface("action", "feed", "actions.definitions.appetites.FeedAction", "social / single"),
    ]
    text = render(actions, [], [], [])
    assert "| Actions (`actions.registry`) | 2 | 1 |" in text
    feed_row = "| `feed` | `actions.definitions.appetites.FeedAction` | social / single | none |"
    assert feed_row in text
    assert "`a/tests/test_look.py`" in text
