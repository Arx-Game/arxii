from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import textwrap

from django.test import SimpleTestCase


class TestUseFiltersetLint(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        repo_root = Path(__file__).resolve().parents[3]
        script_path = repo_root / "tools" / "lint_use_filterset.py"
        spec = importlib.util.spec_from_file_location("lint_use_filterset", script_path)
        if spec is None or spec.loader is None:
            self.fail("Unable to load lint_use_filterset module")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        self.lint_module = module

    def _check(self, code: str, filename: str = "views.py") -> list[tuple[int, int]]:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / filename
            path.write_text(textwrap.dedent(code), encoding="utf-8")
            return self.lint_module.check_file(path)

    def test_flags_query_params_get_in_viewset(self) -> None:
        code = """\
            class MyViewSet(ModelViewSet):
                def list(self, request):
                    status = request.query_params.get("status")
            """
        errors = self._check(code)
        self.assertEqual(len(errors), 1)

    def test_flags_query_params_bracket_in_viewset(self) -> None:
        code = """\
            class MyViewSet(ViewSet):
                def list(self, request):
                    status = request.query_params["status"]
            """
        errors = self._check(code)
        self.assertEqual(len(errors), 1)

    def test_flags_request_get_in_view(self) -> None:
        code = """\
            class MyView(APIView):
                def get(self, request):
                    page = request.GET.get("page")
            """
        errors = self._check(code)
        self.assertEqual(len(errors), 1)

    def test_flags_request_get_bracket_in_view(self) -> None:
        code = """\
            class MyView(APIView):
                def get(self, request):
                    page = request.GET["page"]
            """
        errors = self._check(code)
        self.assertEqual(len(errors), 1)

    def test_flags_self_request_query_params(self) -> None:
        code = """\
            class MyViewSet(ModelViewSet):
                def list(self, request):
                    status = self.request.query_params.get("status")
            """
        errors = self._check(code)
        self.assertEqual(len(errors), 1)

    def test_allows_query_params_outside_view(self) -> None:
        code = """\
            class MyService:
                def do_thing(self, request):
                    status = request.query_params.get("status")
            """
        errors = self._check(code)
        self.assertEqual(errors, [])

    def test_suppression_token(self) -> None:
        code = """\
            class MyViewSet(ModelViewSet):
                def list(self, request):
                    status = request.query_params.get("status")  # noqa: USE_FILTERSET
            """
        errors = self._check(code)
        self.assertEqual(errors, [])

    def test_skips_test_files(self) -> None:
        code = """\
            class MyViewSet(ModelViewSet):
                def list(self, request):
                    status = request.query_params.get("status")
            """
        errors = self._check(code, filename="test_views.py")
        self.assertEqual(errors, [])
