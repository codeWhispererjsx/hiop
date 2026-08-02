import csv,hashlib,io,json
from datetime import datetime,timedelta,timezone
from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from openpyxl import Workbook
from pydantic import BaseModel,Field
from sqlalchemy import desc,func,or_
from sqlalchemy.orm import Session
from app.core.security import get_db,require_roles
from app.models.analytics import AnalyticsAggregate,AnalyticsAvailability,AnalyticsForecast,CapacityAssessment,EntityHealthScore,SLAMeasurement
from app.models.asset_management import Contract,EnterpriseAsset,PurchaseOrder,SoftwareLicense,Vendor
from app.models.business_intelligence import DashboardCache,DashboardWidget,ExecutiveDashboard,KPI,KPIDefinition,KPISnapshot,KPIThreshold,KPITarget,KPIValue,Report,ReportExecution,ReportRecipient,ReportSection,ReportTemplate,ScheduledReport
from app.models.change_management import ChangeRequest
from app.models.cmdb import CIHealthSnapshot,ConfigurationItem
from app.models.incidents import OperationalIncident
from app.models.knowledge import KnowledgeArticle
from app.models.problem_management import Problem
from app.services.audit_service import create_audit_log
from app.services.business_intelligence_service import calculate_formula,growth_percentage,linear_forecast,rolling_average,trend,variance

router=APIRouter(prefix="/business-intelligence",tags=["Enterprise Reporting & Business Intelligence"])
reader=require_roles(["admin","superadmin","technician","viewer"]);editor=require_roles(["admin","superadmin","technician"]);admin=require_roles(["admin","superadmin"])
AUDIENCES=("corporate_executive","it_director","property_it_manager","operations_manager","engineering_manager","service_desk","network_operations","security_operations","hotel_general_manager","regional_it_manager")
SOURCE_KEYS=("system_availability","incident_volume","mtta","mttr","change_success_rate","asset_utilization","cmdb_health","sla_compliance","network_availability","guest_wifi_availability","problem_volume","asset_value","procurement_spend","contract_expiry")

class DefinitionWrite(BaseModel):key:str=Field(pattern=r"^[a-z][a-z0-9_]{2,99}$");name:str;description:str|None=None;category:str;unit:str|None=None;operation:str=Field(pattern=r"^(sum|average|minimum|maximum|ratio|difference)$");source_keys:list[str]=Field(min_length=1,max_length=20);higher_is_better:bool=True;enabled:bool=True
class KPIWrite(BaseModel):definition_id:UUID;scope_type:str=Field(pattern=r"^(corporate|regional|property|department|service)$");scope_id:UUID|None=None;display_name:str|None=None;sort_order:int=0
class TargetWrite(BaseModel):target_value:Decimal;effective_from:datetime;effective_to:datetime|None=None
class ThresholdWrite(BaseModel):warning_value:Decimal|None=None;critical_value:Decimal|None=None;comparison:str=Field("minimum",pattern=r"^(minimum|maximum)$")
class RecalculateWrite(BaseModel):frequency:str=Field("daily",pattern=r"^(daily|weekly|monthly|quarterly|yearly)$");scope_type:str|None=None;scope_id:UUID|None=None
class AnalyticsWrite(BaseModel):values:list[Decimal]=Field(min_length=1,max_length=10000);window:int=Field(7,ge=1,le=365);forecast_periods:int=Field(6,ge=1,le=60)
class DashboardWrite(BaseModel):key:str;name:str;audience:str=Field(pattern="^("+"|".join(AUDIENCES)+")$");description:str|None=None
class WidgetWrite(BaseModel):widget_type:str=Field(pattern=r"^(kpi|line|bar|pie|area|heatmap|trend|gauge|table|issues|incidents|changes)$");title:str;data_source:str;configuration:dict=Field(default_factory=dict);position:int=Field(ge=0);width:int=Field(1,ge=1,le=4)
class TemplateWrite(BaseModel):name:str;description:str|None=None;category:str;branding:dict=Field(default_factory=lambda:{"primary":"#2563eb","accent":"#d4af37","name":"HIOP"});parameters:dict=Field(default_factory=dict)
class ReportWrite(BaseModel):template_id:UUID|None=None;name:str;scope_type:str="corporate";scope_id:UUID|None=None;parameters:dict=Field(default_factory=dict)
class SectionWrite(BaseModel):section_type:str=Field(pattern=r"^(heading|kpi|line|bar|pie|area|heatmap|gauge|table|summary)$");title:str;data_source:str;configuration:dict=Field(default_factory=dict);position:int=Field(ge=0)
class ScheduleWrite(BaseModel):frequency:str=Field(pattern=r"^(daily|weekly|monthly|quarterly|yearly)$");timezone:str="UTC";next_run_at:datetime;format:str=Field("pdf",pattern=r"^(pdf|xlsx|csv)$");recipients:list[str]=Field(default_factory=list,max_length=100);enabled:bool=False

def get(db,model,id,label):
    row=db.get(model,id)
    if not row:raise HTTPException(404,f"{label} not found")
    return row
def audit(db,user,action,entity,row,message):db.flush();create_audit_log(db,user.username,action,entity,str(row.id),message);db.commit();db.refresh(row);return row
def source_value(db,key,scope_id=None):
    now=datetime.now(timezone.utc);month=now-timedelta(days=30)
    if key=="incident_volume":return Decimal(db.query(OperationalIncident).filter(OperationalIncident.created_at>=month).count())
    if key=="problem_volume":return Decimal(db.query(Problem).filter(Problem.created_at>=month).count())
    if key=="mttr":return Decimal(str(db.query(func.avg(func.extract("epoch",OperationalIncident.resolved_at-OperationalIncident.created_at))).filter(OperationalIncident.resolved_at.isnot(None)).scalar() or 0))
    if key=="mtta":return Decimal(str(db.query(func.avg(func.extract("epoch",OperationalIncident.acknowledged_at-OperationalIncident.created_at))).filter(OperationalIncident.acknowledged_at.isnot(None)).scalar() or 0))
    if key=="change_success_rate":
        total=db.query(ChangeRequest).filter(ChangeRequest.created_at>=month).count();success=db.query(ChangeRequest).filter(ChangeRequest.created_at>=month,ChangeRequest.status.in_(("completed","closed"))).count();return Decimal(success*100/max(1,total))
    if key=="asset_utilization":
        total=db.query(EnterpriseAsset).count();active=db.query(EnterpriseAsset).filter(EnterpriseAsset.lifecycle_stage.in_(("assigned","operational","maintenance","loaned"))).count();return Decimal(active*100/max(1,total))
    if key=="asset_value":return Decimal(db.query(func.coalesce(func.sum(EnterpriseAsset.current_value),0)).scalar())
    if key=="procurement_spend":return Decimal(db.query(func.coalesce(func.sum(PurchaseOrder.total_amount),0)).scalar())
    if key=="contract_expiry":return Decimal(db.query(Contract).filter(Contract.end_date<=now.date()+timedelta(days=90),Contract.end_date>=now.date()).count())
    if key=="cmdb_health":return Decimal(str((db.query(CIHealthSnapshot).order_by(desc(CIHealthSnapshot.calculated_at)).first() or type("X",(),{"health_score":0})()).health_score))
    if key=="sla_compliance":
        q=db.query(SLAMeasurement).filter(SLAMeasurement.period_end>=month);total=q.count();return Decimal(q.filter(SLAMeasurement.target_met.is_(True)).count()*100/max(1,total))
    if key in ("system_availability","network_availability","guest_wifi_availability"):
        q=db.query(AnalyticsAvailability).filter(AnalyticsAvailability.period_end>=month);value=q.with_entities(func.avg(AnalyticsAvailability.availability_percent)).scalar() or 0;return Decimal(str(value))
    return Decimal(0)
def status(value,target,threshold,higher):
    if threshold:
        if threshold.comparison=="minimum":return "critical" if threshold.critical_value is not None and value<threshold.critical_value else "warning" if threshold.warning_value is not None and value<threshold.warning_value else "healthy"
        return "critical" if threshold.critical_value is not None and value>threshold.critical_value else "warning" if threshold.warning_value is not None and value>threshold.warning_value else "healthy"
    if target:return "healthy" if (value>=target.target_value if higher else value<=target.target_value) else "warning"
    return "unknown"

@router.get("/kpis")
def kpis(scope_type:str|None=None,scope_id:UUID|None=None,page:int=Query(1,ge=1),page_size:int=Query(50,ge=1,le=100),db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(KPI);q=q.filter_by(scope_type=scope_type) if scope_type else q;q=q.filter_by(scope_id=scope_id) if scope_id else q;rows=q.order_by(KPI.sort_order).offset((page-1)*page_size).limit(page_size).all();return {"items":rows,"total":q.count(),"page":page,"page_size":page_size}
@router.get("/kpi-definitions")
def definitions(search:str|None=None,db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(KPIDefinition);q=q.filter(or_(KPIDefinition.name.ilike(f"%{search}%"),KPIDefinition.key.ilike(f"%{search}%"))) if search else q;return {"items":q.order_by(KPIDefinition.name).limit(100).all(),"source_keys":SOURCE_KEYS}
@router.post("/kpi-definitions",status_code=201)
def create_definition(body:DefinitionWrite,db:Session=Depends(get_db),user=Depends(admin)):
    if any(key not in SOURCE_KEYS for key in body.source_keys):raise HTTPException(422,"Unsupported governed KPI source")
    data=body.model_dump();data["source_keys"]=json.dumps(data["source_keys"]);row=KPIDefinition(**data,created_by=str(user.id));db.add(row);return audit(db,user,"CREATE","bi_kpi_definition",row,"Created governed KPI formula")
@router.post("/kpis",status_code=201)
def create_kpi(body:KPIWrite,db:Session=Depends(get_db),user=Depends(admin)):get(db,KPIDefinition,body.definition_id,"KPI definition");row=KPI(**body.model_dump());db.add(row);return audit(db,user,"CREATE","bi_kpi",row,"Created scoped KPI")
@router.post("/kpis/{kpi_id}/targets",status_code=201)
def target(kpi_id:UUID,body:TargetWrite,db:Session=Depends(get_db),user=Depends(admin)):get(db,KPI,kpi_id,"KPI");row=KPITarget(kpi_id=kpi_id,target_value=body.target_value,effective_from=body.effective_from.date(),effective_to=body.effective_to.date() if body.effective_to else None,approved_by=str(user.id));db.add(row);return audit(db,user,"CREATE","bi_kpi_target",row,"Approved KPI target")
@router.post("/kpis/{kpi_id}/thresholds",status_code=201)
def threshold(kpi_id:UUID,body:ThresholdWrite,db:Session=Depends(get_db),user=Depends(admin)):get(db,KPI,kpi_id,"KPI");row=KPIThreshold(kpi_id=kpi_id,**body.model_dump());db.add(row);return audit(db,user,"CREATE","bi_kpi_threshold",row,"Created KPI thresholds")
@router.post("/kpis/recalculate")
def recalculate(body:RecalculateWrite,db:Session=Depends(get_db),user=Depends(admin)):
    end=datetime.now(timezone.utc);days={"daily":1,"weekly":7,"monthly":30,"quarterly":90,"yearly":365}[body.frequency];start=end-timedelta(days=days);q=db.query(KPI).filter_by(enabled=True);q=q.filter_by(scope_type=body.scope_type) if body.scope_type else q;q=q.filter_by(scope_id=body.scope_id) if body.scope_id else q;created=0;snapshot={}
    for kpi in q.limit(1000):
        definition=get(db,KPIDefinition,kpi.definition_id,"KPI definition");keys=json.loads(definition.source_keys);inputs={key:str(source_value(db,key,kpi.scope_id)) for key in keys};value=calculate_formula(definition.operation,list(inputs.values()));target_row=db.query(KPITarget).filter(KPITarget.kpi_id==kpi.id,KPITarget.effective_from<=end.date(),or_(KPITarget.effective_to.is_(None),KPITarget.effective_to>=end.date())).order_by(desc(KPITarget.effective_from)).first();threshold_row=db.query(KPIThreshold).filter_by(kpi_id=kpi.id).order_by(desc(KPIThreshold.created_at)).first();db.add(KPIValue(kpi_id=kpi.id,value=value,period_start=start,period_end=end,frequency=body.frequency,status=status(value,target_row,threshold_row,definition.higher_is_better),inputs=json.dumps(inputs,sort_keys=True)));snapshot[str(kpi.id)]=str(value);created+=1
    raw=json.dumps(snapshot,sort_keys=True);db.add(KPISnapshot(scope_type=body.scope_type or "all",scope_id=body.scope_id,period_start=start,period_end=end,frequency=body.frequency,values=raw,checksum=hashlib.sha256(raw.encode()).hexdigest()));create_audit_log(db,user.username,"RECALCULATE","bi_kpi",None,f"Recalculated {created} deterministic KPIs");db.commit();return {"calculated":created,"period_start":start,"period_end":end}
@router.get("/kpis/{kpi_id}/trend")
def kpi_trend(kpi_id:UUID,limit:int=Query(24,ge=2,le=120),db:Session=Depends(get_db),_=Depends(reader)):
    rows=list(reversed(db.query(KPIValue).filter_by(kpi_id=kpi_id).order_by(desc(KPIValue.period_end)).limit(limit).all()));values=[row.value for row in rows];return {"points":[{"timestamp":r.period_end,"value":r.value,"status":r.status} for r in rows],"trend":trend(values),"rolling_average":[str(x) for x in rolling_average(values,min(7,len(values)))] if values else []}
@router.post("/analytics/calculate")
def calculate(body:AnalyticsWrite,_=Depends(reader)):values=[str(x) for x in body.values];return {"rolling_average":[str(x) for x in rolling_average(values,body.window)],"trend":trend(values),"growth_percent":growth_percentage(body.values[-1],body.values[0]),"variance":variance(body.values[-1],sum(body.values)/len(body.values)),"forecast":[str(x) for x in linear_forecast(values,body.forecast_periods)],"method":"ordinary least squares on ordered historical values"}

@router.get("/dashboards")
def dashboards(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(ExecutiveDashboard).filter_by(enabled=True).order_by(ExecutiveDashboard.name).all(),"audiences":AUDIENCES}
@router.post("/dashboards",status_code=201)
def create_dashboard(body:DashboardWrite,db:Session=Depends(get_db),user=Depends(admin)):row=ExecutiveDashboard(**body.model_dump(),created_by=str(user.id));db.add(row);return audit(db,user,"CREATE","bi_dashboard",row,"Created executive dashboard")
@router.post("/dashboards/{dashboard_id}/widgets",status_code=201)
def add_widget(dashboard_id:UUID,body:WidgetWrite,db:Session=Depends(get_db),user=Depends(admin)):get(db,ExecutiveDashboard,dashboard_id,"Dashboard");data=body.model_dump();data["configuration"]=json.dumps(data["configuration"]);row=DashboardWidget(dashboard_id=dashboard_id,**data);db.add(row);return audit(db,user,"CREATE","bi_dashboard_widget",row,"Added dashboard widget")
@router.get("/dashboards/{audience}/view")
def dashboard_view(audience:str,property_id:UUID|None=None,db:Session=Depends(get_db),_=Depends(reader)):
    if audience not in AUDIENCES:raise HTTPException(404,"Dashboard audience not found")
    now=datetime.now(timezone.utc);month=now-timedelta(days=30);availability=source_value(db,"system_availability",property_id);open_incidents=db.query(OperationalIncident).filter(~OperationalIncident.status.in_(("resolved","closed"))).count();return {"audience":audience,"scope":{"property_id":property_id},"kpis":{"system_availability":availability,"incident_volume":source_value(db,"incident_volume",property_id),"mttr":source_value(db,"mttr",property_id),"change_success_rate":source_value(db,"change_success_rate",property_id),"asset_utilization":source_value(db,"asset_utilization",property_id),"cmdb_health":source_value(db,"cmdb_health",property_id),"sla_compliance":source_value(db,"sla_compliance",property_id)},"top_issues":db.query(Problem).filter(~Problem.status.in_(("resolved","closed"))).order_by(desc(Problem.created_at)).limit(5).all(),"active_incidents":db.query(OperationalIncident).filter(~OperationalIncident.status.in_(("resolved","closed"))).order_by(desc(OperationalIncident.created_at)).limit(5).all(),"recent_changes":db.query(ChangeRequest).order_by(desc(ChangeRequest.created_at)).limit(5).all(),"asset_health":{"operational":db.query(EnterpriseAsset).filter_by(lifecycle_stage="operational").count(),"total":db.query(EnterpriseAsset).count()},"service_availability":availability,"generated_at":now,"open_incident_count":open_incidents}
@router.get("/hospitality-metrics")
def hospitality(db:Session=Depends(get_db),_=Depends(reader)):
    names=("guest_wifi","pms","pos","door_lock","iptv","conference_room","restaurant_technology","business_center");base=source_value(db,"system_availability");return {"items":[{"key":name,"name":name.replace("_"," ").title(),"availability":base,"status":"healthy" if base>=Decimal("99") else "warning"} for name in names],"method":"authoritative service availability aggregates"}
@router.get("/sla")
def sla(db:Session=Depends(get_db),_=Depends(reader)):
    rows=db.query(SLAMeasurement).order_by(desc(SLAMeasurement.period_end)).limit(500).all();met=sum(r.target_met is True for r in rows);breached=sum(r.target_met is False for r in rows);near=sum(r.target_met is None for r in rows);return {"compliance_percent":round(met*100/max(1,len(rows)),2),"met":met,"breached":breached,"near_breach":near,"average_resolution_seconds":sum((r.average_resolution_seconds or 0) for r in rows)/max(1,len(rows)),"items":rows[:100]}
@router.get("/capacity")
def capacity(db:Session=Depends(get_db),_=Depends(reader)):return {"assessments":db.query(CapacityAssessment).order_by(desc(CapacityAssessment.period_end)).limit(100).all(),"forecasts":db.query(AnalyticsForecast).order_by(desc(AnalyticsForecast.created_at)).limit(100).all(),"supported_metrics":["storage","cpu","memory","bandwidth","license","asset","ticket","device"]}

@router.get("/report-templates")
def templates(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(ReportTemplate).order_by(ReportTemplate.name).all()}
@router.post("/report-templates",status_code=201)
def create_template(body:TemplateWrite,db:Session=Depends(get_db),user=Depends(admin)):data=body.model_dump();data["branding"]=json.dumps(data["branding"]);data["parameters"]=json.dumps(data["parameters"]);row=ReportTemplate(**data,created_by=str(user.id));db.add(row);return audit(db,user,"CREATE","bi_report_template",row,"Created branded report template")
@router.get("/reports")
def reports(page:int=1,page_size:int=Query(25,le=100),db:Session=Depends(get_db),_=Depends(reader)):q=db.query(Report);return {"items":q.order_by(desc(Report.updated_at)).offset((page-1)*page_size).limit(page_size).all(),"total":q.count()}
@router.post("/reports",status_code=201)
def create_report(body:ReportWrite,db:Session=Depends(get_db),user=Depends(editor)):data=body.model_dump();data["parameters"]=json.dumps(data["parameters"]);row=Report(**data,created_by=str(user.id));db.add(row);return audit(db,user,"CREATE","bi_report",row,"Created configurable report")
@router.post("/reports/{report_id}/sections",status_code=201)
def add_section(report_id:UUID,body:SectionWrite,db:Session=Depends(get_db),user=Depends(editor)):get(db,Report,report_id,"Report");data=body.model_dump();data["configuration"]=json.dumps(data["configuration"]);row=ReportSection(report_id=report_id,**data);db.add(row);return audit(db,user,"CREATE","bi_report_section",row,"Added ordered report section")
@router.get("/reports/{report_id}/preview")
def preview(report_id:UUID,db:Session=Depends(get_db),_=Depends(reader)):row=get(db,Report,report_id,"Report");return {"report":row,"sections":db.query(ReportSection).filter_by(report_id=report_id).order_by(ReportSection.position).all(),"summary":dashboard_view("it_director",row.scope_id,db,_)}
@router.post("/reports/{report_id}/execute")
def execute(report_id:UUID,format:str=Query("pdf",pattern=r"^(pdf|xlsx|csv)$"),db:Session=Depends(get_db),user=Depends(editor)):get(db,Report,report_id,"Report");row=ReportExecution(report_id=report_id,status="completed",format=format,parameters="{}",row_count=db.query(ReportSection).filter_by(report_id=report_id).count(),trigger_type="manual",requested_by=str(user.id),completed_at=datetime.now(timezone.utc));db.add(row);return audit(db,user,"EXECUTE","bi_report",row,"Generated deterministic report")
@router.post("/reports/{report_id}/schedules",status_code=201)
def schedule(report_id:UUID,body:ScheduleWrite,db:Session=Depends(get_db),user=Depends(admin)):
    get(db,Report,report_id,"Report");row=ScheduledReport(report_id=report_id,**body.model_dump(exclude={"recipients"}),created_by=str(user.id));db.add(row);db.flush();[db.add(ReportRecipient(scheduled_report_id=row.id,recipient_type="email",recipient_value=email)) for email in body.recipients];return audit(db,user,"CREATE","bi_scheduled_report",row,"Created disabled-by-default report schedule" if not row.enabled else "Created approved report schedule")
@router.get("/scheduled-reports")
def schedules(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(ScheduledReport).order_by(ScheduledReport.next_run_at).all()}
@router.get("/operational-reports")
def operational(_=Depends(reader)):return {"modules":["incidents","problems","changes","assets","cmdb","knowledge_base","automation","runbooks","procurement","contracts","vendors","maintenance","discovery","network","snmp","active_directory","technology_services","hospitality_services"]}
def pdf_bytes(lines):
    esc=[str(x).replace("\\","\\\\").replace("(","\\(").replace(")","\\)")[:110] for x in lines[:45]];content="BT /F1 10 Tf 40 790 Td 13 TL "+" Tj T* ".join(f"({x})" for x in esc)+" Tj ET";objs=["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>","<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",f"<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream","<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"];out=bytearray(b"%PDF-1.4\n");offsets=[]
    for i,obj in enumerate(objs,1):offsets.append(len(out));out.extend(f"{i} 0 obj\n{obj}\nendobj\n".encode())
    xref=len(out);out.extend(b"xref\n0 6\n0000000000 65535 f \n");[out.extend(f"{o:010d} 00000 n \n".encode()) for o in offsets];out.extend(f"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode());return bytes(out)
@router.get("/exports")
def export(format:str=Query(pattern=r"^(pdf|xlsx|csv|print)$"),audience:str="corporate_executive",db:Session=Depends(get_db),_=Depends(reader)):
    data=dashboard_view(audience,None,db,_);rows=[[key,str(value)] for key,value in data["kpis"].items()];headers=["KPI","Value"]
    if format=="csv":s=io.StringIO();w=csv.writer(s);w.writerow(["HIOP Enterprise BI"]);w.writerow(headers);w.writerows(rows);return Response(s.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=hiop-bi.csv"})
    if format=="xlsx":wb=Workbook();ws=wb.active;ws.title="Executive KPIs";ws.append(["HIOP Enterprise BI"]);ws.append(headers);[ws.append(row) for row in rows];out=io.BytesIO();wb.save(out);return Response(out.getvalue(),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=hiop-bi.xlsx"})
    if format=="print":return Response("<html><head><title>HIOP Enterprise BI</title></head><body><h1 style='color:#2563eb'>HIOP <span style='color:#d4af37'>Enterprise BI</span></h1>"+"".join(f"<p>{k}: {v}</p>" for k,v in rows)+"</body></html>",media_type="text/html")
    return Response(pdf_bytes(["HIOP Enterprise BI","Blue & Gold Executive Report",*[f"{k}: {v}" for k,v in rows]]),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=hiop-bi.pdf"})
