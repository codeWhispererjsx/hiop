from uuid import uuid4

from app.api.v1.multi_property import AUDIENCES, pdf_bytes
from app.models.multi_property import AdministrativeScope, Policy, PolicyAssignment, PolicyCompliance, PropertyHierarchyMembership, Region
from app.services.multi_property_service import SCOPE_TYPES, merge_permissions, property_ids_for_scope


def test_enterprise_scope_taxonomy_is_complete():
    assert {"organization","region","country","property_group","property_cluster","property","department"} <= SCOPE_TYPES


def test_explicit_permission_denial_overrides_inheritance():
    assert merge_permissions([["read","report"],["administer"]],[{"report":False},{"export":True}]) == ["administer","export","read"]


def test_property_scope_resolves_to_exact_property():
    property_id=uuid4()
    assert property_ids_for_scope(None,"property",property_id)=={property_id}


def test_core_models_have_auditable_enterprise_tables():
    assert [x.__tablename__ for x in (Region,PropertyHierarchyMembership,AdministrativeScope,Policy,PolicyAssignment,PolicyCompliance)] == ["enterprise_regions","property_hierarchy_memberships","administrative_scopes","corporate_policies","policy_assignments","policy_compliance"]


def test_all_executive_audiences_are_supported():
    assert AUDIENCES == ("ceo","cio","regional_director","corporate_it","regional_it","property_it","engineering")


def test_corporate_pdf_renderer_produces_a_real_pdf():
    result=pdf_bytes(["HIOP Corporate Operations","Property Health"])
    assert result.startswith(b"%PDF-1.4") and result.endswith(b"%%EOF")


def test_scope_expiration_and_override_columns_exist():
    assert {"expires_at","permission_set","overrides","delegated_by"} <= set(AdministrativeScope.__table__.columns.keys())
