import csv, io, json
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.audit_log import AuditLog
from app.models.incidents import OperationalIncident
from app.models.problem_management import *
from app.services.audit_service import create_audit_log
from uuid import UUID

router=APIRouter(prefix="/problems",tags=["Enterprise Problem Management"])
reader=require_roles(["admin","superadmin","technician","viewer"]); contributor=require_roles(["admin","superadmin","technician"]); admin=require_roles(["admin","superadmin"])
TRANSITIONS={"new":"under_investigation","under_investigation":"root_cause_identified","root_cause_identified":"known_error","known_error":"change_required","change_required":"resolved","resolved":"closed"}

class ProblemWrite(BaseModel):
    property_id:UUID|None=None; department_id:UUID|None=None; technology_service_id:UUID|None=None; category_id:UUID|None=None
    title:str=Field(min_length=3,max_length=240); description:str=Field(min_length=3,max_length=50000); summary:str|None=Field(None,max_length=10000)
    priority:str=Field("normal",pattern=r"^(low|normal|high|urgent)$"); severity:str=Field("medium",pattern=r"^(low|medium|high|critical)$"); impact:str=Field("medium",pattern=r"^(low|medium|high|critical)$")
    business_impact:str|None=Field(None,max_length=20000); technical_impact:str|None=Field(None,max_length=20000); source:str=Field("manual",max_length=40); owner_id:str|None=None; assigned_team:str|None=Field(None,max_length=160); review_date:datetime|None=None
class ProblemPatch(BaseModel):
    title:str|None=Field(None,min_length=3,max_length=240); description:str|None=Field(None,min_length=3,max_length=50000); summary:str|None=Field(None,max_length=10000); priority:str|None=None; severity:str|None=None; impact:str|None=None; business_impact:str|None=None; technical_impact:str|None=None; owner_id:str|None=None; assigned_team:str|None=None; review_date:datetime|None=None; change_summary:str=Field("Problem updated",max_length=500)
class TransitionWrite(BaseModel): target_status:str; reason:str=Field(min_length=3,max_length=5000)
class RCAWrite(BaseModel): methodology:str=Field("five_whys",pattern=r"^(five_whys|fishbone|combined|timeline)$"); timeline:list[dict]=Field(default_factory=list); technical_findings:str|None=None; business_findings:str|None=None; validation:str|None=None
class WhyWrite(BaseModel): sequence:int=Field(ge=1,le=5); question:str=Field(min_length=2,max_length=1000); answer:str=Field(min_length=2,max_length=10000); evidence:str|None=Field(None,max_length=10000)
class FishboneWrite(BaseModel): category:str=Field(pattern=r"^(human|infrastructure|environment|process|vendor|technology)$"); cause:str=Field(min_length=2,max_length=10000); evidence:str|None=None
class CauseWrite(BaseModel): category:str=Field(max_length=40); statement:str=Field(min_length=3,max_length=20000); evidence:str=Field(min_length=3,max_length=20000); validated:bool=False
class KnownErrorWrite(BaseModel): problem_id:UUID; description:str=Field(min_length=3,max_length=30000); symptoms:str=Field(min_length=3,max_length=30000); affected_services:list[str]=Field(default_factory=list); affected_devices:list[str]=Field(default_factory=list); affected_properties:list[str]=Field(default_factory=list); root_cause:str=Field(min_length=3,max_length=30000); temporary_workaround:str|None=None; permanent_resolution:str|None=None; related_change_id:UUID|None=None; related_knowledge_id:UUID|None=None
class WorkaroundWrite(BaseModel): workaround_type:str=Field("temporary",pattern=r"^(temporary|permanent)$"); instructions:str=Field(min_length=3,max_length=30000); verification:str=Field(min_length=3,max_length=20000); effectiveness_rating:int=Field(ge=0,le=5); risk_level:str=Field("medium",pattern=r"^(low|medium|high|critical)$"); required_permissions:list[str]=Field(default_factory=list); validation_checklist:list[str]=Field(default_factory=list); linked_runbooks:list[str]=Field(default_factory=list); linked_sops:list[str]=Field(default_factory=list)
class PlanWrite(BaseModel): plan_type:str=Field(pattern=r"^(corrective|preventive)$"); title:str=Field(min_length=3,max_length=220); objective:str=Field(min_length=3,max_length=20000); owner_id:str|None=None; due_at:datetime|None=None
class TaskWrite(BaseModel): plan_type:str=Field(pattern=r"^(corrective|preventive)$"); plan_id:UUID; title:str=Field(min_length=3,max_length=220); description:str|None=None; assigned_to:str|None=None; due_at:datetime|None=None
class VerificationWrite(BaseModel): result:str=Field(pattern=r"^(passed|failed|inconclusive)$"); evidence:str=Field(min_length=3,max_length=20000)
class ReviewWrite(BaseModel): lessons_learned:str; business_summary:str; technical_summary:str; timeline:list[dict]=Field(default_factory=list); stakeholders:list[str]=Field(default_factory=list); action_items:list[dict]=Field(default_factory=list)
class RelationshipWrite(BaseModel): target_type:str=Field(pattern=r"^(incident|change|configuration_item|asset|knowledge_article|runbook|sop|vendor|contract|maintenance|service|automation_workflow)$"); target_id:UUID; relationship_type:str=Field("related",max_length=40); notes:str|None=None
class CorrelationWrite(BaseModel): threshold:int=Field(3,ge=2,le=100); lookback_days:int=Field(30,ge=1,le=365); property_id:UUID|None=None
class BulkTransitionWrite(BaseModel): problem_ids:list[UUID]=Field(min_length=1,max_length=100); target_status:str; reason:str=Field(min_length=3,max_length=1000)

def number(db,prefix,model,column): return f"{prefix}-{datetime.now(timezone.utc):%Y%m%d}-{db.query(model).count()+1:05d}"
def audit(db,user,action,entity,row,message): create_audit_log(db,user.username,action,entity,str(row.id),message); db.commit(); db.refresh(row); return row
def problem(db,id):
    row=db.get(Problem,id)
    if not row: raise HTTPException(404,"Problem not found")
    return row
def revision(db,row,user,summary):
    db.add(ProblemRevision(problem_id=row.id,version=row.version,snapshot=json.dumps({c.name:str(getattr(row,c.name)) for c in row.__table__.columns},sort_keys=True),change_summary=summary,created_by=str(user.id)))

@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(Problem); open_q=q.filter(~Problem.status.in_(("resolved","closed"))); cutoff=datetime.now(timezone.utc)-timedelta(days=30)
    return {"open_problems":open_q.count(),"high_priority":open_q.filter(Problem.priority.in_(("high","urgent"))).count(),"known_errors":db.query(KnownError).filter(KnownError.status=="published").count(),"rca_in_progress":db.query(RootCauseAnalysis).filter(RootCauseAnalysis.status.in_(("draft","in_review"))).count(),"capa_overdue":db.query(ActionTask).filter(ActionTask.status!="completed",ActionTask.due_at<datetime.now(timezone.utc)).count(),"recurring_incidents":db.query(ProblemCorrelationSuggestion).filter_by(status="suggested").count(),"aging":open_q.filter(Problem.created_at<cutoff).count(),"recent":q.order_by(desc(Problem.updated_at)).limit(8).all()}
@router.get("")
def list_problems(status:str|None=None,priority:str|None=None,search:str|None=None,page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(Problem); q=q.filter(Problem.status==status) if status else q; q=q.filter(Problem.priority==priority) if priority else q
    if search:q=q.filter(or_(Problem.problem_number.ilike(f"%{search}%"),Problem.title.ilike(f"%{search}%"),Problem.summary.ilike(f"%{search}%")))
    return {"items":q.order_by(desc(Problem.updated_at)).offset((page-1)*page_size).limit(page_size).all(),"total":q.count(),"page":page,"page_size":page_size}
@router.post("",status_code=201)
def create_problem(body:ProblemWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    row=Problem(**body.model_dump(),problem_number=number(db,"PRB",Problem,Problem.problem_number),created_by=str(user.id)); db.add(row); db.flush(); revision(db,row,user,"Problem created"); return audit(db,user,"CREATE","problem",row,"Created enterprise problem record")
@router.get("/{problem_id}")
def get_problem(problem_id:UUID,db:Session=Depends(get_db),_=Depends(reader)): return problem(db,problem_id)
@router.patch("/{problem_id}")
def update_problem(problem_id:UUID,body:ProblemPatch,db:Session=Depends(get_db),user=Depends(contributor)):
    row=problem(db,problem_id); data=body.model_dump(exclude_unset=True); summary=data.pop("change_summary","Problem updated")
    if row.status=="closed": raise HTTPException(409,"Closed problems are immutable")
    row.version+=1; [setattr(row,k,v) for k,v in data.items()]; row.updated_at=datetime.now(timezone.utc); revision(db,row,user,summary); return audit(db,user,"UPDATE","problem",row,summary)
@router.post("/{problem_id}/transition")
def transition(problem_id:UUID,body:TransitionWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    row=problem(db,problem_id); expected=TRANSITIONS.get(row.status)
    if body.target_status!=expected: raise HTTPException(409,f"Next permitted status is {expected or 'none'}")
    if body.target_status=="root_cause_identified" and not db.query(RootCause).join(RootCauseAnalysis).filter(RootCauseAnalysis.problem_id==row.id,RootCause.validated.is_(True)).count(): raise HTTPException(409,"A validated root cause is required")
    if body.target_status=="known_error" and not db.query(KnownError).filter_by(problem_id=row.id).count(): raise HTTPException(409,"A known error record is required")
    if body.target_status=="closed" and not db.query(ProblemReview).filter_by(problem_id=row.id,status="approved").count(): raise HTTPException(409,"An approved problem review is required")
    row.status=body.target_status; row.updated_at=datetime.now(timezone.utc); row.version+=1; row.closed_at=datetime.now(timezone.utc) if row.status=="closed" else None; revision(db,row,user,body.reason); return audit(db,user,"TRANSITION","problem",row,body.reason)

@router.post("/bulk-transitions")
def bulk_transition(body:BulkTransitionWrite,db:Session=Depends(get_db),user=Depends(admin)):
    results=[]
    for problem_id in body.problem_ids:
        try:
            row=transition(problem_id,TransitionWrite(target_status=body.target_status,reason=body.reason),db,user)
            results.append({"id":str(row.id),"status":"updated"})
        except HTTPException as exc:
            db.rollback(); results.append({"id":str(problem_id),"status":"rejected","reason":exc.detail})
    return {"items":results,"updated":sum(item["status"]=="updated" for item in results),"rejected":sum(item["status"]=="rejected" for item in results)}

@router.get("/{problem_id}/rca")
def get_rca(problem_id:UUID,db:Session=Depends(get_db),_=Depends(reader)):
    problem(db,problem_id); r=db.query(RootCauseAnalysis).filter_by(problem_id=problem_id).first(); return {"analysis":r,"causes":db.query(RootCause).filter_by(rca_id=r.id).all() if r else [],"factors":db.query(ContributingFactor).filter_by(rca_id=r.id).all() if r else [],"five_whys":db.query(FiveWhys).filter_by(rca_id=r.id).order_by(FiveWhys.sequence).all() if r else [],"fishbone":db.query(FishboneAnalysis).filter_by(rca_id=r.id).all() if r else []}
@router.put("/{problem_id}/rca")
def save_rca(problem_id:UUID,body:RCAWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    problem(db,problem_id); r=db.query(RootCauseAnalysis).filter_by(problem_id=problem_id).first() or RootCauseAnalysis(problem_id=problem_id,created_by=str(user.id)); db.add(r); [setattr(r,k,json.dumps(v) if k=="timeline" else v) for k,v in body.model_dump().items()]; r.updated_at=datetime.now(timezone.utc); return audit(db,user,"UPDATE","root_cause_analysis",r,"Saved structured RCA")
@router.post("/{problem_id}/rca/causes",status_code=201)
def add_cause(problem_id:UUID,body:CauseWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    r=save_rca(problem_id,RCAWrite(),db,user) if not db.query(RootCauseAnalysis).filter_by(problem_id=problem_id).first() else db.query(RootCauseAnalysis).filter_by(problem_id=problem_id).first(); row=RootCause(rca_id=r.id,**body.model_dump()); db.add(row); return audit(db,user,"CREATE","root_cause",row,"Recorded evidence-backed root cause")
@router.post("/{problem_id}/rca/five-whys",status_code=201)
def add_why(problem_id:UUID,body:WhyWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    r=db.query(RootCauseAnalysis).filter_by(problem_id=problem_id).first();
    if not r: raise HTTPException(409,"Create the RCA workspace first")
    old=db.query(FiveWhys).filter_by(rca_id=r.id,sequence=body.sequence).first(); row=old or FiveWhys(rca_id=r.id,**body.model_dump()); db.add(row)
    if old:[setattr(old,k,v) for k,v in body.model_dump().items()]
    return audit(db,user,"UPDATE","five_whys",row,"Updated deterministic Five Whys entry")
@router.post("/{problem_id}/rca/fishbone",status_code=201)
def add_fishbone(problem_id:UUID,body:FishboneWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    r=db.query(RootCauseAnalysis).filter_by(problem_id=problem_id).first();
    if not r: raise HTTPException(409,"Create the RCA workspace first")
    row=FishboneAnalysis(rca_id=r.id,**body.model_dump()); db.add(row); return audit(db,user,"CREATE","fishbone_analysis",row,"Added reviewed fishbone factor")

@router.get("/known-errors/library")
def known_errors(search:str|None=None,status:str|None=None,db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(KnownError); q=q.filter(KnownError.status==status) if status else q
    if search:q=q.filter(or_(KnownError.error_id.ilike(f"%{search}%"),KnownError.description.ilike(f"%{search}%"),KnownError.symptoms.ilike(f"%{search}%")))
    return {"items":q.order_by(desc(KnownError.updated_at)).limit(100).all(),"total":q.count()}
@router.post("/known-errors",status_code=201)
def create_known_error(body:KnownErrorWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    problem(db,body.problem_id); data=body.model_dump(); [data.__setitem__(k,json.dumps(data[k])) for k in ("affected_services","affected_devices","affected_properties")]; row=KnownError(**data,error_id=number(db,"KE",KnownError,KnownError.error_id),created_by=str(user.id)); db.add(row); db.flush(); db.add(KnownErrorRevision(known_error_id=row.id,version=1,snapshot=json.dumps(data,default=str),created_by=str(user.id))); return audit(db,user,"CREATE","known_error",row,"Created known error")
@router.post("/known-errors/{error_id}/{action}")
def known_error_action(error_id:UUID,action:str,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(KnownError,error_id)
    if not row:raise HTTPException(404,"Known error not found")
    allowed={"approve":("approved",None),"publish":("published","published_at"),"retire":("retired","retired_at")}
    if action not in allowed:raise HTTPException(400,"Unsupported lifecycle action")
    expected={"approve":"draft","publish":"approved","retire":"published"}[action]
    if row.status!=expected:raise HTTPException(409,f"Known error must be {expected} before {action}")
    row.status,stamp=allowed[action]
    if stamp:setattr(row,stamp,datetime.now(timezone.utc))
    return audit(db,user,action.upper(),"known_error",row,f"Known error {action}")
@router.post("/known-errors/{error_id}/workarounds",status_code=201)
def add_workaround(error_id:UUID,body:WorkaroundWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    if not db.get(KnownError,error_id):raise HTTPException(404,"Known error not found")
    data=body.model_dump(); [data.__setitem__(k,json.dumps(data[k])) for k in ("required_permissions","validation_checklist","linked_runbooks","linked_sops")]; row=KnownErrorWorkaround(known_error_id=error_id,**data); db.add(row); return audit(db,user,"CREATE","known_error_workaround",row,"Added reviewed workaround")
@router.get("/workarounds/library")
def workaround_library(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(KnownErrorWorkaround).order_by(desc(KnownErrorWorkaround.created_at)).limit(100).all()}

@router.post("/{problem_id}/capa/plans",status_code=201)
def create_plan(problem_id:UUID,body:PlanWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    problem(db,problem_id); cls=CorrectiveActionPlan if body.plan_type=="corrective" else PreventiveActionPlan; data=body.model_dump(exclude={"plan_type"}); row=cls(problem_id=problem_id,**data); db.add(row); return audit(db,user,"CREATE",f"{body.plan_type}_action_plan",row,"Created CAPA plan")
@router.get("/{problem_id}/capa")
def capa(problem_id:UUID,db:Session=Depends(get_db),_=Depends(reader)): return {"corrective":db.query(CorrectiveActionPlan).filter_by(problem_id=problem_id).all(),"preventive":db.query(PreventiveActionPlan).filter_by(problem_id=problem_id).all(),"tasks":db.query(ActionTask).filter(ActionTask.plan_id.in_([r.id for r in db.query(CorrectiveActionPlan).filter_by(problem_id=problem_id).all()]+[r.id for r in db.query(PreventiveActionPlan).filter_by(problem_id=problem_id).all()])).all()}
@router.post("/capa/tasks",status_code=201)
def create_task(body:TaskWrite,db:Session=Depends(get_db),user=Depends(contributor)): row=ActionTask(**body.model_dump()); db.add(row); return audit(db,user,"CREATE","problem_action_task",row,"Created CAPA task")
@router.post("/capa/tasks/{task_id}/verify")
def verify_task(task_id:UUID,body:VerificationWrite,db:Session=Depends(get_db),user=Depends(admin)):
    task=db.get(ActionTask,task_id)
    if not task:raise HTTPException(404,"CAPA task not found")
    row=ActionVerification(task_id=task_id,verified_by=str(user.id),**body.model_dump()); db.add(row); task.status="completed" if body.result=="passed" else "verification_failed"; task.completed_at=datetime.now(timezone.utc) if body.result=="passed" else None; return audit(db,user,"VERIFY","problem_action",row,"Verified CAPA task")

@router.post("/{problem_id}/reviews",status_code=201)
def create_review(problem_id:UUID,body:ReviewWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    problem(db,problem_id); data=body.model_dump(); [data.__setitem__(k,json.dumps(data[k])) for k in ("timeline","stakeholders","action_items")]; row=ProblemReview(problem_id=problem_id,created_by=str(user.id),**data); db.add(row); return audit(db,user,"CREATE","problem_review",row,"Created post-resolution review")
@router.post("/reviews/{review_id}/approve")
def approve_review(review_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=db.get(ProblemReview,review_id)
    if not row:raise HTTPException(404,"Review not found")
    row.status="approved"; row.approved_by=str(user.id); row.signed_off_at=datetime.now(timezone.utc); return audit(db,user,"APPROVE","problem_review",row,"Approved and signed off problem review")
@router.post("/{problem_id}/relationships",status_code=201)
def add_relationship(problem_id:UUID,body:RelationshipWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    problem(db,problem_id); row=ProblemRelationship(problem_id=problem_id,created_by=str(user.id),**body.model_dump()); db.add(row); return audit(db,user,"CREATE","problem_relationship",row,"Linked problem relationship")
@router.get("/{problem_id}/relationships/graph")
def relationship_graph(problem_id:UUID,db:Session=Depends(get_db),_=Depends(reader)):
    row=problem(db,problem_id); edges=db.query(ProblemRelationship).filter_by(problem_id=problem_id).all(); return {"nodes":[{"id":str(row.id),"type":"problem","label":row.problem_number}]+[{"id":str(e.target_id),"type":e.target_type,"label":e.target_type.replace("_"," ")} for e in edges],"edges":[{"source":str(row.id),"target":str(e.target_id),"type":e.relationship_type} for e in edges]}

@router.post("/correlations/detect")
def detect(body:CorrelationWrite,db:Session=Depends(get_db),user=Depends(admin)):
    cutoff=datetime.now(timezone.utc)-timedelta(days=body.lookback_days); q=db.query(OperationalIncident).filter(OperationalIncident.created_at>=cutoff)
    if body.property_id:q=q.filter(OperationalIncident.property_id==body.property_id)
    groups={}
    for incident in q.limit(5000):
        key=incident.correlation_key or f"{incident.property_id}:{incident.technology_service_id}:{incident.incident_type}"
        groups.setdefault(key,[]).append(incident)
    created=0
    for key,rows in groups.items():
        if len(rows)<body.threshold or db.query(ProblemCorrelationSuggestion).filter_by(correlation_key=key,status="suggested").first():continue
        db.add(ProblemCorrelationSuggestion(property_id=rows[0].property_id,correlation_key=key,source_type="incident",source_ids=json.dumps([str(r.id) for r in rows]),occurrence_count=len(rows),threshold=body.threshold,rationale=f"{len(rows)} incidents share a deterministic correlation key within {body.lookback_days} days.")); created+=1
    create_audit_log(db,user.username,"DETECT","problem_correlation",None,f"Created {created} review suggestions"); db.commit(); return {"suggestions_created":created,"groups_evaluated":len(groups),"automatic_problems_created":0}
@router.get("/correlations/suggestions")
def suggestions(db:Session=Depends(get_db),_=Depends(reader)): return {"items":db.query(ProblemCorrelationSuggestion).order_by(desc(ProblemCorrelationSuggestion.detected_at)).limit(100).all()}

@router.get("/reports/summary")
def reports(db:Session=Depends(get_db),_=Depends(reader)):
    total=db.query(Problem).count(); resolved=db.query(Problem).filter(Problem.status.in_(("resolved","closed"))).count(); return {"total":total,"open":total-resolved,"resolved":resolved,"resolution_rate":round(resolved*100/max(1,total),2),"known_errors":db.query(KnownError).count(),"published_known_errors":db.query(KnownError).filter_by(status="published").count(),"capa_total":db.query(ActionTask).count(),"capa_completed":db.query(ActionTask).filter_by(status="completed").count(),"root_cause_categories":dict(db.query(RootCause.category,func.count(RootCause.id)).group_by(RootCause.category).all())}
@router.get("/reports/export")
def export(format:str=Query(pattern=r"^(csv|xlsx|pdf)$"),db:Session=Depends(get_db),_=Depends(reader)):
    rows=db.query(Problem).order_by(Problem.created_at).limit(10000).all(); headers=["problem_number","title","status","priority","severity","impact","created_at","closed_at"]
    if format=="csv":
        stream=io.StringIO(); writer=csv.writer(stream); writer.writerow(headers); [writer.writerow([getattr(r,h) for h in headers]) for r in rows]; return Response(stream.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=problem-report.csv"})
    if format=="xlsx":
        wb=Workbook(); ws=wb.active; ws.title="Problems"; ws.append(headers); [ws.append([str(getattr(r,h) or "") for h in headers]) for r in rows]; out=io.BytesIO(); wb.save(out); return Response(out.getvalue(),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=problem-report.xlsx"})
    lines=["HIOP Enterprise Problem Management",*[' | '.join(str(getattr(r,h) or '') for h in headers) for r in rows[:45]]]
    escaped=[line.replace("\\","\\\\").replace("(","\\(").replace(")","\\)")[:110] for line in lines]
    content="BT /F1 9 Tf 40 790 Td 12 TL "+" Tj T* ".join(f"({line})" for line in escaped)+" Tj ET"
    objects=["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>","<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",f"<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream","<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    pdf=bytearray(b"%PDF-1.4\n"); offsets=[]
    for index,obj in enumerate(objects,1): offsets.append(len(pdf)); pdf.extend(f"{index} 0 obj\n{obj}\nendobj\n".encode())
    xref=len(pdf); pdf.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode()); [pdf.extend(f"{offset:010d} 00000 n \n".encode()) for offset in offsets]; pdf.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode())
    return Response(bytes(pdf),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=problem-report.pdf"})
@router.get("/search/all")
def search(q:str=Query(min_length=2,max_length=200),db:Session=Depends(get_db),_=Depends(reader)): return {"problems":db.query(Problem).filter(or_(Problem.title.ilike(f"%{q}%"),Problem.description.ilike(f"%{q}%"))).limit(50).all(),"known_errors":db.query(KnownError).filter(or_(KnownError.description.ilike(f"%{q}%"),KnownError.symptoms.ilike(f"%{q}%"))).limit(50).all()}
