import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import or_, text
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.core.tenant import organization_context
from app.models.asset_intelligence import ManagedAsset
from app.models.asset_management import Vendor
from app.models.change_management import ChangeRequest
from app.models.device import Device
from app.models.hierarchy import Property
from app.models.hospitality_operations import HospitalityTechnologyService
from app.models.incidents import OperationalIncident
from app.models.knowledge import KnowledgeArticle, KnowledgeRating, KnowledgeRelationship, KnowledgeRevision, KnowledgeViewHistory
from app.models.problem_management import Problem
from app.models.user import User
from app.services.audit_service import create_audit_log

router=APIRouter(prefix="/knowledge-base",tags=["Knowledge Base"])
reader=require_roles(["platformadmin","admin","technician","viewer"]); editor=require_roles(["admin","technician"]); publisher=require_roles(["admin"])
STATUSES={"draft","in_review","published","archived"}; TYPES={"how_to","troubleshooting","sop","known_issue","recovery_procedure","reference"}
CATEGORIES={"network","pos","pms","wifi","printer","hardware","software","security_system","telephony","server","general_it","other"}
UNSAFE=re.compile(r"<\s*script|on\w+\s*=|javascript\s*:|<\s*(iframe|object|embed)",re.I)
CREDENTIAL=re.compile(r"\b(password|passwd|secret|api[_ -]?key|private[_ -]?key)\s*[:=]\s*\S+",re.I)

def safe(value):
    if value and UNSAFE.search(value): raise HTTPException(422,"Unsafe executable HTML is not allowed")
    if value and CREDENTIAL.search(value): raise HTTPException(422,"Credential-like content is not allowed in knowledge articles")
    return value

class ArticleWrite(BaseModel):
    title:str=Field(min_length=3,max_length=240);summary:str=Field("",max_length=4000);content:str=Field(min_length=3,max_length=50000)
    article_type:str="reference";category:str="other";tags:list[str]=Field(default_factory=list,max_length=30);steps:list[str]=Field(default_factory=list,max_length=100);warnings:str|None=Field(None,max_length=10000);owner_id:str|None=None;review_date:datetime|None=None
    @field_validator("article_type")
    @classmethod
    def type_valid(cls,v):
        if v not in TYPES:raise ValueError("Unsupported article type")
        return v
    @field_validator("category")
    @classmethod
    def category_valid(cls,v):
        if v not in CATEGORIES:raise ValueError("Unsupported category")
        return v
    @field_validator("content","summary","warnings")
    @classmethod
    def content_safe(cls,v):return safe(v)
    @field_validator("steps")
    @classmethod
    def steps_safe(cls,v):return [safe(x.strip()) for x in v if x.strip()]
    @field_validator("tags")
    @classmethod
    def tags_safe(cls,v):return list(dict.fromkeys(x.strip()[:80] for x in v if x.strip()))

class ArticlePatch(BaseModel):
    title:str|None=Field(None,min_length=3,max_length=240);summary:str|None=Field(None,max_length=4000);content:str|None=Field(None,min_length=3,max_length=50000);article_type:str|None=None;category:str|None=None;tags:list[str]|None=None;steps:list[str]|None=None;warnings:str|None=Field(None,max_length=10000);owner_id:str|None=None;review_date:datetime|None=None;change_summary:str|None=Field(None,max_length=1000)
    @field_validator("content","summary","warnings")
    @classmethod
    def content_safe(cls,v):return safe(v)
    @field_validator("steps")
    @classmethod
    def steps_safe(cls,v):return None if v is None else [safe(x.strip()) for x in v if x.strip()]

class ActionWrite(BaseModel):comments:str|None=Field(None,max_length=4000)
class FeedbackWrite(BaseModel):helpful:bool;feedback:str|None=Field(None,max_length=2000)
class LinkWrite(BaseModel):target_type:Literal["asset","device","service","problem","incident","change","vendor"];target_id:UUID

TARGETS={"asset":ManagedAsset,"device":Device,"service":HospitalityTechnologyService,"problem":Problem,"incident":OperationalIncident,"change":ChangeRequest,"vendor":Vendor}
def validate_target(db,kind,target_id,org):
    model=TARGETS[kind];q=db.query(model).filter(model.id==target_id)
    if hasattr(model,"organization_id"):q=q.filter(model.organization_id==org)
    elif model is Device:q=q.join(Property,Device.property_id==Property.id).filter(Property.organization_id==org)
    row=q.first()
    if not row:raise HTTPException(422,f"{kind.title()} does not belong to this organization")
    return row
def require_article(db,id,org):
    row=db.query(KnowledgeArticle).filter_by(id=id,organization_id=org).first()
    if not row:raise HTTPException(404,"Knowledge article not found")
    return row
def can_see(row,user):return row.status=="published" or user.role in {"admin","platformadmin"} or (user.role=="technician" and row.author_id==user.id)
def audit(db,row,user,action,detail):create_audit_log(db,user.username,f"KNOWLEDGE_{action.upper()}","KnowledgeArticle",str(row.id),f"Organization {row.organization_id}: {detail}")
def revision(db,row,user,summary):
    checksum=hashlib.sha256(f"{row.title}\n{row.summary or ''}\n{row.body}".encode()).hexdigest()
    db.add(KnowledgeRevision(article_id=row.id,version=row.version,title=row.title,summary=row.summary,body=row.body,change_summary=summary,checksum_sha256=checksum,created_by=user.id))
def related(db,row):return db.query(KnowledgeRelationship).filter_by(source_type="article",source_id=row.id,organization_id=row.organization_id).all()
def present(db,row,detail=False):
    ratings=db.query(KnowledgeRating).filter_by(article_id=row.id).all();rels=related(db,row)
    result={"id":row.id,"article_id":row.article_number,"title":row.title,"summary":row.summary,"content":row.body,"type":row.article_type,"category":row.category,"status":row.status,"author_id":row.author_id,"owner_id":row.owner_id,"version":row.version,"tags":json.loads(row.tags_text or "[]"),"steps":json.loads(row.steps_text or "[]"),"warnings":row.warnings,"published_at":row.published_at,"review_date":row.next_review_at,"review_due":bool(row.next_review_at and row.next_review_at<datetime.now(timezone.utc)),"views":row.view_count,"last_viewed":row.last_viewed_at,"helpful":sum(x.rating==1 for x in ratings),"not_helpful":sum(x.rating==0 for x in ratings),"created_at":row.created_at,"updated_at":row.updated_at,"related_counts":{kind:sum(x.target_type==kind for x in rels) for kind in TARGETS}}
    if detail:
        result["relationships"]=[{"id":x.id,"type":x.target_type,"target_id":x.target_id} for x in rels]
        result["versions"]=[{"id":x.id,"version":x.version,"title":x.title,"summary":x.summary,"content":x.body,"change_summary":x.change_summary,"created_by":x.created_by,"created_at":x.created_at} for x in db.query(KnowledgeRevision).filter_by(article_id=row.id).order_by(KnowledgeRevision.version.desc()).all()]
    return result

@router.get("/summary")
def summary(db:Session=Depends(get_db),user=Depends(reader),org=Depends(organization_context)):
    rows=db.query(KnowledgeArticle).filter_by(organization_id=org).all();visible=[x for x in rows if can_see(x,user)];now=datetime.now(timezone.utc)
    return {"total":len(visible),**{s:sum(x.status==s for x in visible) for s in STATUSES},"review_due":sum(bool(x.next_review_at and x.next_review_at<now and x.status=="published") for x in visible),"recently_updated":sum((now-x.updated_at).days<=30 for x in visible),"most_viewed":max((x.view_count for x in visible),default=0)}

@router.get("")
def list_articles(search:str|None=None,status:str|None=None,article_type:str|None=None,category:str|None=None,tag:str|None=None,author_id:str|None=None,owner_id:str|None=None,db:Session=Depends(get_db),user=Depends(reader),org=Depends(organization_context)):
    q=db.query(KnowledgeArticle).filter_by(organization_id=org)
    if user.role not in {"admin","platformadmin"}:q=q.filter(or_(KnowledgeArticle.status=="published",KnowledgeArticle.author_id==user.id) if user.role=="technician" else KnowledgeArticle.status=="published")
    if search:
        term=f"%{search}%";q=q.filter(or_(KnowledgeArticle.article_number.ilike(term),KnowledgeArticle.title.ilike(term),KnowledgeArticle.summary.ilike(term),KnowledgeArticle.body.ilike(term),KnowledgeArticle.tags_text.ilike(term),KnowledgeArticle.category.ilike(term)))
    if status:q=q.filter_by(status=status)
    if article_type:q=q.filter_by(article_type=article_type)
    if category:q=q.filter_by(category=category)
    if tag:q=q.filter(KnowledgeArticle.tags_text.ilike(f'%"{tag}"%'))
    if author_id:q=q.filter_by(author_id=author_id)
    if owner_id:q=q.filter_by(owner_id=owner_id)
    return [present(db,x) for x in q.order_by(KnowledgeArticle.updated_at.desc()).all()]

@router.post("",status_code=201)
def create(payload:ArticleWrite,db:Session=Depends(get_db),user=Depends(editor),org=Depends(organization_context)):
    if payload.owner_id and not db.query(User).filter_by(id=payload.owner_id,organization_id=org).first():raise HTTPException(422,"Owner does not belong to this organization")
    prop=db.query(Property).filter_by(organization_id=org,is_active=True).first();number=db.execute(text("SELECT nextval('v4h_article_number_seq')")).scalar_one()
    row=KnowledgeArticle(organization_id=org,property_id=prop.id if prop else None,article_number=f"KB-{number:05d}",title=payload.title,slug=f"{re.sub('[^a-z0-9]+','-',payload.title.lower()).strip('-')}-{uuid4().hex[:8]}",summary=payload.summary,body=payload.content,article_type=payload.article_type,category=payload.category,tags_text=json.dumps(payload.tags),steps_text=json.dumps(payload.steps),warnings=payload.warnings,author_id=user.id,owner_id=payload.owner_id,status="draft",approval_state="not_submitted",next_review_at=payload.review_date,visibility="organization")
    db.add(row);db.flush();revision(db,row,user,"Initial version");audit(db,row,user,"ARTICLE_CREATED",f"Created {row.article_number}");db.commit();db.refresh(row);return present(db,row,True)

@router.get("/articles/{article_id}")
def get(article_id:UUID,db:Session=Depends(get_db),user=Depends(reader),org=Depends(organization_context)):
    row=require_article(db,article_id,org)
    if not can_see(row,user):raise HTTPException(403,"Draft or review knowledge is restricted")
    row.view_count+=1;row.last_viewed_at=datetime.now(timezone.utc);db.add(KnowledgeViewHistory(article_id=row.id,user_id=user.id));db.commit();db.refresh(row);return present(db,row,True)

@router.patch("/articles/{article_id}")
def update(article_id:UUID,payload:ArticlePatch,db:Session=Depends(get_db),user=Depends(editor),org=Depends(organization_context)):
    row=require_article(db,article_id,org)
    if user.role=="technician" and row.author_id!=user.id:raise HTTPException(403,"Technicians may edit only their own drafts")
    if row.status not in {"draft","in_review"}:raise HTTPException(422,"Published or archived articles must be restored to draft before editing")
    values=payload.model_dump(exclude_unset=True);summary=values.pop("change_summary",None) or "Article edited";mapping={"content":"body","type":"article_type","review_date":"next_review_at","tags":"tags_text","steps":"steps_text"}
    for key,value in values.items():setattr(row,mapping.get(key,key),json.dumps(value) if key in {"tags","steps"} else value)
    row.version+=1;row.updated_at=datetime.now(timezone.utc);revision(db,row,user,summary);audit(db,row,user,"ARTICLE_EDITED",summary);audit(db,row,user,"VERSION_CREATED",f"Created version {row.version}");db.commit();return present(db,row,True)

@router.post("/articles/{article_id}/actions/{action}")
def action(article_id:UUID,action:str,payload:ActionWrite,db:Session=Depends(get_db),user=Depends(editor),org=Depends(organization_context)):
    row=require_article(db,article_id,org);now=datetime.now(timezone.utc)
    if action=="submit":
        if row.status!="draft":raise HTTPException(422,"Only drafts can be submitted")
        row.status="in_review";row.approval_state="pending"
    elif action=="publish":
        if user.role!="admin":raise HTTPException(403,"Only administrators can publish")
        if row.status!="in_review":raise HTTPException(422,"Only reviewed articles can be published")
        row.status="published";row.approval_state="approved";row.published_at=now
    elif action=="archive":
        if user.role!="admin":raise HTTPException(403,"Only administrators can archive")
        if row.status!="published":raise HTTPException(422,"Only published articles can be archived")
        row.status="archived";row.archived_at=now
    elif action=="restore":
        if user.role!="admin":raise HTTPException(403,"Only administrators can restore")
        if row.status!="archived":raise HTTPException(422,"Only archived articles can be restored")
        row.status="draft";row.archived_at=None;row.approval_state="not_submitted"
    else:raise HTTPException(404,"Unsupported knowledge action")
    audit(db,row,user,action,payload.comments or f"Article {action}");db.commit();return present(db,row,True)

@router.get("/articles/{article_id}/versions")
def versions(article_id:UUID,db:Session=Depends(get_db),user=Depends(reader),org=Depends(organization_context)):
    row=require_article(db,article_id,org)
    if user.role not in {"admin","platformadmin"} and row.author_id!=user.id:raise HTTPException(403,"Version history is restricted")
    return present(db,row,True)["versions"]

@router.post("/articles/{article_id}/feedback")
def feedback(article_id:UUID,payload:FeedbackWrite,db:Session=Depends(get_db),user=Depends(reader),org=Depends(organization_context)):
    row=require_article(db,article_id,org)
    if row.status!="published":raise HTTPException(422,"Feedback is available for published articles")
    rating=db.query(KnowledgeRating).filter_by(article_id=row.id,user_id=user.id).first()
    if not rating:rating=KnowledgeRating(article_id=row.id,user_id=user.id,rating=1 if payload.helpful else 0,feedback=payload.feedback);db.add(rating)
    else:rating.rating=1 if payload.helpful else 0;rating.feedback=payload.feedback;rating.updated_at=datetime.now(timezone.utc)
    db.commit();return {"helpful":payload.helpful}

@router.post("/articles/{article_id}/relationships",status_code=201)
def link(article_id:UUID,payload:LinkWrite,db:Session=Depends(get_db),user=Depends(editor),org=Depends(organization_context)):
    row=require_article(db,article_id,org);validate_target(db,payload.target_type,payload.target_id,org)
    existing=db.query(KnowledgeRelationship).filter_by(source_type="article",source_id=row.id,target_type=payload.target_type,target_id=payload.target_id,relationship_type="related").first()
    if not existing:db.add(KnowledgeRelationship(organization_id=org,property_id=row.property_id,source_type="article",source_id=row.id,target_type=payload.target_type,target_id=payload.target_id,relationship_type="related",created_by=user.id,validation_status="valid"));audit(db,row,user,"RELATIONSHIP_LINKED",f"Linked {payload.target_type} {payload.target_id}")
    db.commit();return present(db,row,True)

@router.get("/links/{target_type}/{target_id}")
def linked(target_type:Literal["asset","device","service","problem","incident","change","vendor"],target_id:UUID,db:Session=Depends(get_db),user=Depends(reader),org=Depends(organization_context)):
    validate_target(db,target_type,target_id,org);ids=db.query(KnowledgeRelationship.source_id).filter_by(organization_id=org,source_type="article",target_type=target_type,target_id=target_id)
    rows=db.query(KnowledgeArticle).filter(KnowledgeArticle.organization_id==org,KnowledgeArticle.id.in_(ids)).all();return [present(db,x) for x in rows if can_see(x,user)]
