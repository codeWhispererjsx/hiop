import unittest
from uuid import uuid4

from fastapi import HTTPException
from pydantic import ValidationError

from app.main import app
from app.models.hierarchy import Organization, Property
from app.schemas.hospitality import OrganizationWrite, PropertyWrite
from app.services.hospitality_service import HospitalityService


class HospitalityFoundationTests(unittest.TestCase):
    def test_routes_and_openapi_models_exist(self):
        paths = app.openapi()["paths"]
        self.assertIn("/api/v1/organizations", paths)
        self.assertIn("/api/v1/properties", paths)
        self.assertIn("/api/v1/properties/{property_id}", paths)

    def test_organization_and_property_validation(self):
        organization = OrganizationWrite(name="North Star Hospitality", code="NSH", country="NG")
        self.assertEqual(organization.code, "NSH")
        property_payload = PropertyWrite(name="Lagos Resort", type="resort", number_of_rooms=120, organization_id=uuid4())
        self.assertEqual(property_payload.type, "resort")
        with self.assertRaises(ValidationError):
            OrganizationWrite(name="x", code="bad code")
        with self.assertRaises(ValidationError):
            PropertyWrite(name="Site", number_of_rooms=-1)

    def test_models_preserve_legacy_hierarchy_and_nullable_context(self):
        self.assertEqual(Property.__tablename__, "properties")
        self.assertIn("organization_id", Property.__table__.columns)
        self.assertEqual(Organization.__tablename__, "organizations")

    def test_service_missing_relationship_is_safe(self):
        class Empty:
            def get(self, *_): return None
        with self.assertRaises(HTTPException) as context:
            HospitalityService(Empty()).organization(uuid4())
        self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
