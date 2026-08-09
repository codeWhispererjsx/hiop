"""Focused, read-only Active Directory computer enrichment for V2C."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from sqlalchemy import select

from app.models.active_directory import ActiveDirectoryConnection
from app.models.discovery_intelligence import DiscoveryEvidence, DiscoveryResult
from app.services.active_directory_secret_service import ActiveDirectorySecretService
from app.services.active_directory_service import ActiveDirectoryConnectionService
from app.services.audit_service import create_audit_log
from app.services.device_enrichment_service import EnrichmentOutcome
from app.services.discovery_intelligence_service import DEPARTMENT_RULES, WEIGHTS, confidence, review_status
from app.services.ldap_client import LdapError, SecureLdapClient


def safe_connection(row):
    return {"id":row.id,"name":row.name,"domain_name":row.domain_name,"server_host":row.server_host,"server_port":row.server_port,"use_ssl":row.use_ssl,"use_start_tls":row.use_start_tls,"base_dn":row.base_dn,"computer_search_base":row.computer_search_base,"bind_username":row.bind_username,"authentication_method":row.authentication_method,"connection_timeout_seconds":row.connection_timeout_seconds,"page_size":row.page_size,"enabled":row.enabled,"verify_tls":row.verify_tls,"ca_certificate_reference":row.ca_certificate_reference,"secret_configured":bool(row.encrypted_bind_secret),"last_tested_at":row.last_tested_at,"last_test_status":row.last_test_status,"last_test_message":row.last_test_message,"created_at":row.created_at,"updated_at":row.updated_at}


class ActiveDirectoryConfigurationService:
    """Stores only connection metadata and an encrypted bind secret; no directory sync is enabled."""
    def __init__(self,db):self.db=db
    def create(self,payload,actor):
        if self.db.scalar(select(ActiveDirectoryConnection.id).where(ActiveDirectoryConnection.name==payload.name)):raise ValueError("An Active Directory connection with this name already exists.")
        data=payload.model_dump(exclude={"bind_secret","user_search_base","group_search_base"});secret=ActiveDirectorySecretService.encrypt_secret(payload.bind_secret) if payload.bind_secret else None
        row=ActiveDirectoryConnection(**data,user_search_base=None,group_search_base=None,encrypted_bind_secret=secret,created_by=actor.id,updated_by=actor.id)
        ActiveDirectoryConnectionService(self.db)._validate_connection_policy(row)
        self.db.add(row);self.db.flush();create_audit_log(self.db,actor.username,"AD_CONNECTION_CREATED","ActiveDirectoryConnection",str(row.id),f"Created read-only Active Directory computer connection '{row.name}'.");self.db.commit();self.db.refresh(row);return row
    def update(self,row,payload,actor):
        data=payload.model_dump(exclude_unset=True,exclude={"user_search_base","group_search_base"})
        for key,value in data.items():setattr(row,key,value)
        ActiveDirectoryConnectionService(self.db)._validate_connection_policy(row);row.updated_by=actor.id
        create_audit_log(self.db,actor.username,"AD_CONNECTION_UPDATED","ActiveDirectoryConnection",str(row.id),f"Updated read-only Active Directory computer connection '{row.name}'.");self.db.commit();self.db.refresh(row);return row
    def rotate_secret(self,row,secret,actor):
        row.encrypted_bind_secret=ActiveDirectorySecretService.encrypt_secret(secret);row.updated_by=actor.id
        create_audit_log(self.db,actor.username,"AD_SECRET_ROTATED","ActiveDirectoryConnection",str(row.id),f"Rotated the bind secret for '{row.name}'.");self.db.commit();self.db.refresh(row);return row


def _short_name(value):return str(value or "").strip().rstrip(".").split(".",1)[0].rstrip("$").lower()
def _leaf_ou(dn):return next((part.strip()[3:] for part in str(dn or "").split(",") if part.strip().upper().startswith("OU=")),None)
def _department(ou,description):
    text=f" {ou or ''} {description or ''} ".lower()
    for code,label in DEPARTMENT_RULES.items():
        if label.lower() in text or f" {code.lower()} " in text:return label
    return None


class ActiveDirectoryEnrichmentProvider:
    name="Active Directory"
    def __init__(self,db,client_factory=SecureLdapClient):self.db=db;self.client_factory=client_factory
    def enrich(self,device):
        candidates=[value for value in (device.fqdn,device.primary_hostname) if value]
        if not candidates:return EnrichmentOutcome("unavailable",warnings=["A hostname or FQDN is required for Active Directory correlation."],error_category="identity_missing")
        short=_short_name(candidates[0]);connections=self.db.scalars(select(ActiveDirectoryConnection).where(ActiveDirectoryConnection.enabled.is_(True)).order_by(ActiveDirectoryConnection.use_ssl.desc(),ActiveDirectoryConnection.name)).all()
        if not connections:return EnrichmentOutcome("unavailable",warnings=["No enabled Active Directory connection is configured."],error_category="connection_missing")
        failures=[]
        for connection in connections:
            client=None
            try:
                service=ActiveDirectoryConnectionService(self.db,client_factory=self.client_factory);client=service._bound_client(connection)
                search=client.search_computers(connection.computer_search_base or connection.base_dn,search_term=short,limit=10)
                exact=[]
                for item in search.items:
                    names={_short_name(item.get("dns_hostname")),_short_name(item.get("sam_account_name"))}
                    if short in names:exact.append(item)
                if not exact:continue
                if len(exact)>1:return EnrichmentOutcome("unavailable",warnings=["More than one exact Active Directory computer match was returned."],error_category="ambiguous_match")
                item=exact[0];dns=item.get("dns_hostname");dn=item.get("distinguished_name");ou=_leaf_ou(dn);domain=str(dns).split(".",1)[1] if dns and "." in str(dns) else connection.domain_name
                attrs={"computer_name":_short_name(item.get("sam_account_name") or dns).upper(),"distinguished_name":dn,"fqdn":str(dns).lower() if dns else None,"domain":str(domain).upper() if domain else None,"organizational_unit":ou,"description":item.get("description"),"operating_system":item.get("operating_system"),"operating_system_version":item.get("operating_system_version"),"enabled":item.get("enabled"),"last_logon_at":item.get("last_logon_at"),"suggested_department":_department(ou,item.get("description"))}
                evidence=[{"evidence_type":"ad_match","source":"active_directory","value":attrs["computer_name"],"verified":True},{"evidence_type":"active_directory","source":"active_directory","value":dn or attrs["computer_name"],"verified":True}]
                for key,evidence_type in (("description","description"),("organizational_unit","organizational_unit"),("operating_system","operating_system"),("domain","domain")):
                    if attrs.get(key) not in (None,""):evidence.append({"evidence_type":evidence_type,"source":"active_directory","value":attrs[key],"verified":True})
                if device.description and attrs.get("description") and str(device.description).strip().casefold()==str(attrs["description"]).strip().casefold():evidence.append({"evidence_type":"ad_description_agreement","source":"active_directory_agreement","value":attrs["description"],"verified":True})
                if device.department and attrs.get("suggested_department") and str(device.department).casefold()==str(attrs["suggested_department"]).casefold():evidence.append({"evidence_type":"ad_department_agreement","source":"active_directory_agreement","value":attrs["suggested_department"],"verified":True})
                if device.fqdn and attrs.get("domain") and str(device.fqdn).lower().endswith("."+str(attrs["domain"]).lower()):evidence.append({"evidence_type":"ad_domain_match","source":"active_directory_agreement","value":attrs["domain"],"verified":True})
                missing=[label for key,label in (("description","Description"),("organizational_unit","OU"),("operating_system","Operating system"),("domain","Domain")) if not attrs.get(key)]
                warnings=[f"{label} unavailable." for label in missing]
                if attrs.get("enabled") is False:warnings.append("The Active Directory computer account is disabled.")
                return EnrichmentOutcome("enriched" if not missing else "partially_enriched",attrs,evidence,warnings)
            except LdapError as error:failures.append(error)
            finally:
                if client:client.close()
        if failures:
            error=failures[-1];return EnrichmentOutcome("unavailable",warnings=[error.safe_message],error_category=error.category)
        return EnrichmentOutcome("unavailable",warnings=["Computer object not found."],error_category="computer_not_found")


class ActiveDirectoryDeviceEnrichmentService:
    def __init__(self,db,provider=None):self.db=db;self.provider=provider or ActiveDirectoryEnrichmentProvider(db)
    def enrich(self,result,actor):
        result.ad_enrichment_status="attempted";self.db.flush();outcome=self.provider.enrich(result);attrs=outcome.attributes;result.ad_enrichment_status=outcome.status;result.ad_last_error=outcome.error_category;result.ad_last_enriched_at=datetime.now(timezone.utc)
        mapping=(("computer_name","ad_computer_name"),("distinguished_name","ad_distinguished_name"),("domain","ad_domain"),("organizational_unit","ad_organizational_unit"),("description","ad_description"),("operating_system","ad_operating_system"),("operating_system_version","ad_operating_system_version"),("enabled","ad_enabled"),("last_logon_at","ad_last_logon_at"),("suggested_department","suggested_department"))
        for source,target in mapping:
            if source in attrs and attrs[source] not in (None,""):setattr(result,target,attrs[source])
        if attrs.get("fqdn") and not result.fqdn:result.fqdn=attrs["fqdn"]
        if attrs.get("operating_system") and not result.operating_system:result.operating_system=attrs["operating_system"]
        if attrs.get("description") and not result.description:result.description=attrs["description"];result.description_source="Active Directory"
        for raw in outcome.evidence:
            norm=str(raw["value"]).strip().lower()[:500];exists=self.db.scalar(select(DiscoveryEvidence).where(DiscoveryEvidence.result_id==result.id,DiscoveryEvidence.evidence_type==raw["evidence_type"],DiscoveryEvidence.source==raw["source"],DiscoveryEvidence.normalized_value==norm))
            if not exists:self.db.add(DiscoveryEvidence(result_id=result.id,evidence_type=raw["evidence_type"],source=raw["source"],value=json.dumps(raw["value"],default=str),normalized_value=norm,weight=WEIGHTS.get(raw["evidence_type"],0),verified=raw.get("verified",False)))
        self.db.flush();types=[row[0] for row in self.db.execute(select(DiscoveryEvidence.evidence_type).where(DiscoveryEvidence.result_id==result.id).distinct()).all()];score=confidence(types);result.confidence_score=score["score"];result.confidence_explanation=json.dumps(score["contributions"])
        if result.review_status!="manually_verified":result.review_status=review_status(result.confidence_score)
        if hasattr(result,"canonical_result_id"):
            from app.services.device_correlation_service import DeviceCorrelationService
            result=DeviceCorrelationService(self.db).correlate(result,"active_directory_enrichment")
        create_audit_log(self.db,actor.username,"ENRICH_DISCOVERY_AD","DiscoveryResult",str(result.id),f"Read-only Active Directory enrichment completed with status {outcome.status}.");self.db.commit();self.db.refresh(result)
        return {"status":outcome.status,"provider":self.provider.name,"device":result,"found":sorted(key for key,value in attrs.items() if value not in (None,"",[],{})),"warnings":outcome.warnings,"evidence_added":len(outcome.evidence),"confidence_score":result.confidence_score}
