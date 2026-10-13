"""Pruebas de la documentación OpenAPI (/api/v1/schema/ y /api/v1/docs/)."""
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from tests.utils import make_user


class TestOpenAPI(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.user = make_user("doc@sentryx.local")

    def schema(self):
        self.client.force_authenticate(self.user)
        resp = self.client.get("/api/v1/schema/", {"format": "json"})
        self.assertEqual(resp.status_code, 200)
        import json
        return json.loads(resp.content)

    def test_schema_documents_required_endpoints(self):
        paths = self.schema()["paths"]
        for path in ("/api/v1/auth/token/", "/api/v1/auth/mfa/verify/",
                     "/api/v1/auth/mfa/setup/", "/api/v1/alerts/",
                     "/api/v1/alerts/analyze/", "/api/v1/alerts/report/",
                     "/api/v1/incidents/"):
            self.assertIn(path, paths)

    def test_schema_has_examples_and_jwt(self):
        schema = self.schema()
        self.assertIn("jwtAuth", schema["components"]["securitySchemes"])
        login = schema["paths"]["/api/v1/auth/token/"]["post"]
        self.assertIn("examples", login["requestBody"]["content"]["application/json"])
        report = schema["paths"]["/api/v1/alerts/report/"]["get"]
        self.assertEqual(report["tags"], ["reports"])

    @override_settings(DEBUG=False)
    def test_production_requires_authentication(self):
        self.assertEqual(self.client.get("/api/v1/schema/").status_code, 401)
        self.assertEqual(self.client.get("/api/v1/docs/").status_code, 401)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/v1/docs/").status_code, 200)

    @override_settings(DEBUG=True)
    def test_development_is_public(self):
        self.assertEqual(self.client.get("/api/v1/docs/").status_code, 200)
