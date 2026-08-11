import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_

from app.models.hierarchy import Property
from app.models.multi_property import AdministrativeScope, Country, PropertyGroup, PropertyHierarchyMembership, Region
from app.models.property_access import UserPropertyAccess


SCOPE_TYPES={"organization","business_unit","region","country","property_group","property_cluster","property","department"}


def active_scopes(db,user):
    now=datetime.now(timezone.utc)
    return db.query(AdministrativeScope).filter(AdministrativeScope.user_id==str(user.id),AdministrativeScope.enabled.is_(True),AdministrativeScope.starts_at<=now,or_(AdministrativeScope.expires_at.is_(None),AdministrativeScope.expires_at>now)).all()


def property_ids_for_scope(db,scope_type:str,scope_id:UUID|None):
    if scope_type=="organization": return {r[0] for r in db.query(Property.id).filter(Property.organization_id==scope_id)}
    if scope_type=="region": return {r[0] for r in db.query(PropertyHierarchyMembership.property_id).join(PropertyGroup,PropertyHierarchyMembership.property_group_id==PropertyGroup.id).join(Country,PropertyGroup.country_id==Country.id).filter(Country.region_id==scope_id)}
    if scope_type=="country": return {r[0] for r in db.query(PropertyHierarchyMembership.property_id).join(PropertyGroup,PropertyHierarchyMembership.property_group_id==PropertyGroup.id).filter(PropertyGroup.country_id==scope_id)}
    if scope_type=="property_group": return {r[0] for r in db.query(PropertyHierarchyMembership.property_id).filter(PropertyHierarchyMembership.property_group_id==scope_id)}
    if scope_type=="property_cluster": return {r[0] for r in db.query(PropertyHierarchyMembership.property_id).filter(PropertyHierarchyMembership.property_cluster_id==scope_id)}
    if scope_type=="property": return {scope_id} if scope_id else set()
    return set()


def allowed_property_ids(db,user):
    if user.role=="platformadmin": return {r[0] for r in db.query(Property.id)}
    allowed={r[0] for r in db.query(UserPropertyAccess.property_id).filter(UserPropertyAccess.user_id==str(user.id),UserPropertyAccess.enabled.is_(True),or_(UserPropertyAccess.expires_at.is_(None),UserPropertyAccess.expires_at>datetime.now(timezone.utc)))};scopes=active_scopes(db,user)
    for scope in scopes: allowed.update(property_ids_for_scope(db,scope.scope_type,scope.scope_id))
    if user.role=="admin" and not allowed and not scopes:return {r[0] for r in db.query(Property.id)}
    return allowed


def require_property(db,user,property_id):
    if property_id not in allowed_property_ids(db,user): raise PermissionError("Property is outside the active administrative scope")
    return property_id


def require_scope(db,user,scope_type,scope_id):
    if user.role=="platformadmin":return
    scopes=active_scopes(db,user);grant_count=db.query(UserPropertyAccess.id).filter(UserPropertyAccess.user_id==str(user.id),UserPropertyAccess.enabled.is_(True)).count()
    if user.role=="admin" and not scopes and not grant_count:return
    if any(scope.scope_type==scope_type and scope.scope_id==scope_id for scope in scopes):return
    target=property_ids_for_scope(db,scope_type,scope_id)
    if not target or not target.issubset(allowed_property_ids(db,user)):raise PermissionError("Administrative target is outside the active scope")


def merge_permissions(permission_sets, overrides):
    granted={permission for values in permission_sets for permission in values};denied=set()
    for values in overrides:
        granted.update(key for key,value in values.items() if value is True);denied.update(key for key,value in values.items() if value is False)
    return sorted(granted-denied)


def effective_permissions(db,user,property_id=None):
    permission_sets=[];overrides=[]
    for scope in active_scopes(db,user):
        if property_id and property_id not in property_ids_for_scope(db,scope.scope_type,scope.scope_id): continue
        permission_sets.append(json.loads(scope.permission_set or "[]"));overrides.append(json.loads(scope.overrides or "{}"))
    return merge_permissions(permission_sets,overrides)
