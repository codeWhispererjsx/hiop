import csv, io, json
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_
from sqlalchemy.orm import Session

from app.core.security import get_db, require_roles
from app.models.asset_management import *
from app.services.audit_service import create_audit_log

router=APIRouter(prefix="/asset-management",tags=["Enterprise Asset, Vendor & Procurement"])
reader=require_roles(["admin","superadmin","technician","viewer"]); contributor=require_roles(["admin","superadmin","technician"]); admin=require_roles(["admin","superadmin"])
STAGES=("planned","requested","approved","purchased","received","installed","assigned","operational","maintenance","loaned","transferred","retired","disposed","archived")
NEXT={stage:STAGES[i+1] for i,stage in enumerate(STAGES[:-1])}

class AssetWrite(BaseModel):
    property_id:UUID|None=None; category_id:UUID|None=None; subcategory_id:UUID|None=None; ownership_id:UUID|None=None; ci_id:UUID|None=None; legacy_device_id:UUID|None=None; asset_tag:str|None=None; barcode:str|None=None; qr_code:str|None=None; serial_number:str|None=None; manufacturer:str|None=None; model:str|None=None; description:str|None=None; purchase_date:date|None=None; purchase_cost:Decimal=Field(0,ge=0); residual_value:Decimal=Field(0,ge=0); depreciation_method:str=Field("straight_line",pattern=r"^(straight_line|declining_balance|none)$"); useful_life_months:int=Field(60,ge=1,le=600); warranty_start:date|None=None; warranty_end:date|None=None; end_of_life:date|None=None; owner_id:str|None=None; assigned_user_id:str|None=None; department_id:UUID|None=None; building_id:UUID|None=None; floor_id:UUID|None=None; room_id:UUID|None=None; rack_id:UUID|None=None
class TransitionWrite(BaseModel): target_stage:str; reason:str=Field(min_length=3,max_length=1000)
class BulkTransitionWrite(BaseModel): asset_ids:list[UUID]=Field(min_length=1,max_length=100); target_stage:str; reason:str=Field(min_length=3,max_length=1000)
class AssignmentAssetWrite(BaseModel): user_id:str|None=None; department_id:UUID|None=None; notes:str|None=None
class TransferWrite(BaseModel): to_property_id:UUID; reason:str=Field(min_length=3)
class DisposalWrite(BaseModel): method:str=Field(min_length=2,max_length=60); reason:str=Field(min_length=3); proceeds:Decimal=Field(0,ge=0); data_destruction_evidence:str|None=None
class VendorWrite(BaseModel): legal_name:str=Field(min_length=2,max_length=220); trading_name:str|None=None; category_id:UUID|None=None; preferred:bool=False; tax_id:str|None=None; service_regions:list[str]=Field(default_factory=list)
class ReviewWrite(BaseModel): rating:int=Field(ge=1,le=5); findings:str=Field(min_length=3); recommendation:str|None=None; delivery_score:int=Field(ge=0,le=100); quality_score:int=Field(ge=0,le=100); support_score:int=Field(ge=0,le=100); compliance_score:int=Field(ge=0,le=100)
class RequestWrite(BaseModel): property_id:UUID|None=None; department_id:UUID|None=None; budget_id:UUID|None=None; title:str=Field(min_length=3,max_length=220); justification:str=Field(min_length=3); requested_amount:Decimal=Field(gt=0); currency:str=Field("USD",min_length=3,max_length=3)
class DecisionWrite(BaseModel): decision:str=Field(pattern=r"^(approve|reject)$"); notes:str=Field(min_length=3,max_length=3000)
class OrderWrite(BaseModel): purchase_request_id:UUID; vendor_id:UUID; items:list[dict]=Field(min_length=1,max_length=200)
class ReceiveWrite(BaseModel): purchase_order_item_id:UUID; quantity:int=Field(gt=0); condition:str=Field("accepted",pattern=r"^(accepted|damaged|rejected)$"); serial_numbers:list[str]=Field(default_factory=list); notes:str|None=None
class ContractWrite(BaseModel): title:str=Field(min_length=3); contract_type_id:UUID|None=None; vendor_id:UUID; property_id:UUID|None=None; start_date:date; end_date:date; value:Decimal=Field(ge=0); currency:str="USD"; auto_renew:bool=False; notice_days:int=Field(90,ge=1,le=730); terms:str|None=None
class RenewalWrite(BaseModel): proposed_end_date:date; proposed_value:Decimal=Field(ge=0)
class WarrantyWrite(BaseModel): asset_id:UUID; vendor_id:UUID|None=None; provider:str; coverage:str; start_date:date; end_date:date
class ClaimWrite(BaseModel): description:str; amount:Decimal=Field(0,ge=0)
class LicenseWrite(BaseModel): product_id:UUID; vendor_id:UUID|None=None; property_id:UUID|None=None; license_key:str|None=None; license_type:str; seats_purchased:int=Field(gt=0); purchase_cost:Decimal=Field(0,ge=0); renewal_date:date|None=None; subscription:bool=False
class ProductWrite(BaseModel): name:str=Field(min_length=2); publisher:str=Field(min_length=2); version:str|None=None; category:str|None=None
class AssignmentWrite(BaseModel): asset_id:UUID|None=None; user_id:str|None=None
class InventoryItemWrite(BaseModel): sku:str; name:str; item_type:str=Field(pattern=r"^(spare_part|consumable)$"); unit:str="each"; minimum_stock:int=Field(0,ge=0); reorder_level:int=Field(0,ge=0); unit_cost:Decimal=Field(0,ge=0); vendor_id:UUID|None=None
class InventoryLocationWrite(BaseModel): property_id:UUID|None=None; name:str; code:str; address:str|None=None
class StockWrite(BaseModel): item_id:UUID; location_id:UUID; movement_type:str=Field(pattern=r"^(receive|issue|adjust|transfer_in|transfer_out)$"); quantity:int=Field(ne=0); reference_type:str|None=None; reference_id:UUID|None=None; notes:str|None=None
class RelationshipWrite(BaseModel): target_type:str=Field(pattern=r"^(asset|vendor|contract|configuration_item|incident|problem|change|knowledge_article|maintenance|procurement|software_license|warranty)$"); target_id:UUID; relationship_type:str="related"; notes:str|None=None

def number(db,prefix,model):return f"{prefix}-{datetime.now(timezone.utc):%Y%m%d}-{db.query(model).count()+1:05d}"
def get(db,model,id,label):
    row=db.get(model,id)
    if not row:raise HTTPException(404,f"{label} not found")
    return row
def audit(db,user,action,entity,row,message):db.flush();create_audit_log(db,user.username,action,entity,str(row.id),message);db.commit();db.refresh(row);return row
def depreciation(asset:EnterpriseAsset,on_date:date|None=None):
    cost=Decimal(asset.purchase_cost or 0); residual=Decimal(asset.residual_value or 0); target=on_date or date.today()
    if not asset.purchase_date or asset.depreciation_method=="none":return {"depreciation":Decimal("0.00"),"current_value":cost}
    months=max(0,(target.year-asset.purchase_date.year)*12+target.month-asset.purchase_date.month-(target.day<asset.purchase_date.day)); months=min(months,asset.useful_life_months)
    if asset.depreciation_method=="straight_line":value=cost-(cost-residual)*Decimal(months)/Decimal(asset.useful_life_months)
    else:value=max(residual,cost*(Decimal("0.8")**(Decimal(months)/Decimal(12))))
    value=max(residual,value).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP);return {"depreciation":(cost-value).quantize(Decimal("0.01")),"current_value":value}

@router.get("/dashboard")
def dashboard(db:Session=Depends(get_db),_=Depends(reader)):
    today=date.today(); soon=today+timedelta(days=90); assets=db.query(EnterpriseAsset); return {"assets":assets.count(),"operational":assets.filter_by(lifecycle_stage="operational").count(),"asset_value":str(db.query(func.coalesce(func.sum(EnterpriseAsset.current_value),0)).scalar()),"warranties_expiring":db.query(Warranty).filter(Warranty.end_date.between(today,soon)).count(),"contracts_expiring":db.query(Contract).filter(Contract.end_date.between(today,soon)).count(),"licenses_noncompliant":db.query(LicenseCompliance).filter(LicenseCompliance.status!="compliant").count(),"open_requests":db.query(PurchaseRequest).filter(PurchaseRequest.status.in_(("draft","submitted","approved"))).count(),"low_stock":db.query(StockBalance).join(InventoryItem).filter(StockBalance.quantity<=InventoryItem.reorder_level).count(),"recent":assets.order_by(desc(EnterpriseAsset.updated_at)).limit(8).all()}
@router.get("/assets")
def assets(search:str|None=None,status:str|None=None,property_id:UUID|None=None,sort:str="updated_at",page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(EnterpriseAsset);q=q.filter_by(status=status) if status else q;q=q.filter_by(property_id=property_id) if property_id else q
    if search:q=q.filter(or_(EnterpriseAsset.asset_number.ilike(f"%{search}%"),EnterpriseAsset.asset_tag.ilike(f"%{search}%"),EnterpriseAsset.serial_number.ilike(f"%{search}%"),EnterpriseAsset.model.ilike(f"%{search}%")))
    order={"asset_number":EnterpriseAsset.asset_number,"purchase_cost":EnterpriseAsset.purchase_cost,"current_value":EnterpriseAsset.current_value}.get(sort,EnterpriseAsset.updated_at);return {"items":q.order_by(desc(order)).offset((page-1)*page_size).limit(page_size).all(),"total":q.count(),"page":page,"page_size":page_size}
@router.post("/assets",status_code=201)
def create_asset(body:AssetWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    row=EnterpriseAsset(**body.model_dump(),asset_number=number(db,"AST",EnterpriseAsset),current_value=body.purchase_cost,created_by=str(user.id));db.add(row);db.flush();db.add(AssetLifecycle(asset_id=row.id,current_stage="planned",reason="Enterprise asset created",actor_id=str(user.id)));return audit(db,user,"CREATE","enterprise_asset",row,"Created enterprise asset")
@router.get("/assets/{asset_id}")
def asset(asset_id:UUID,db:Session=Depends(get_db),_=Depends(reader)):return get(db,EnterpriseAsset,asset_id,"Asset")
@router.post("/assets/{asset_id}/transition")
def transition(asset_id:UUID,body:TransitionWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    row=get(db,EnterpriseAsset,asset_id,"Asset"); expected=NEXT.get(row.lifecycle_stage)
    if body.target_stage!=expected:raise HTTPException(409,f"Next permitted stage is {expected or 'none'}")
    if body.target_stage=="purchased" and row.purchase_cost<=0:raise HTTPException(409,"Purchase cost is required")
    if body.target_stage=="disposed" and not db.query(AssetDisposal).filter_by(asset_id=row.id).first():raise HTTPException(409,"An approved disposal record is required")
    db.add(AssetLifecycle(asset_id=row.id,previous_stage=row.lifecycle_stage,current_stage=body.target_stage,reason=body.reason,actor_id=str(user.id)));row.lifecycle_stage=body.target_stage;row.status=body.target_stage;row.version+=1;row.updated_at=datetime.now(timezone.utc);return audit(db,user,"TRANSITION","enterprise_asset",row,body.reason)
@router.post("/assets/bulk-transitions")
def bulk_transition(body:BulkTransitionWrite,db:Session=Depends(get_db),user=Depends(admin)):
    results=[]
    for asset_id in body.asset_ids:
        try:row=transition(asset_id,TransitionWrite(target_stage=body.target_stage,reason=body.reason),db,user);results.append({"id":str(row.id),"status":"updated"})
        except HTTPException as exc:db.rollback();results.append({"id":str(asset_id),"status":"rejected","reason":exc.detail})
    return {"items":results,"updated":sum(x["status"]=="updated" for x in results)}
@router.post("/assets/{asset_id}/assignments",status_code=201)
def assign_asset(asset_id:UUID,body:AssignmentAssetWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    row=get(db,EnterpriseAsset,asset_id,"Asset");assignment=AssetAssignment(asset_id=asset_id,**body.model_dump(),assigned_by=str(user.id));db.add(assignment);row.assigned_user_id=body.user_id;row.department_id=body.department_id;return audit(db,user,"ASSIGN","enterprise_asset",assignment,"Recorded asset assignment")
@router.post("/assets/{asset_id}/transfers",status_code=201)
def transfer_asset(asset_id:UUID,body:TransferWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    asset=get(db,EnterpriseAsset,asset_id,"Asset");row=AssetTransfer(asset_id=asset_id,from_property_id=asset.property_id,**body.model_dump(),requested_by=str(user.id));db.add(row);return audit(db,user,"CREATE","asset_transfer",row,"Requested inter-property transfer")
@router.post("/assets/transfers/{transfer_id}/approve")
def approve_transfer(transfer_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=get(db,AssetTransfer,transfer_id,"Transfer");asset=get(db,EnterpriseAsset,row.asset_id,"Asset");row.status="approved";row.approved_by=str(user.id);row.transferred_at=datetime.now(timezone.utc);asset.property_id=row.to_property_id;db.add(AssetLocationHistory(asset_id=asset.id,property_id=row.to_property_id,reason=row.reason));return audit(db,user,"APPROVE","asset_transfer",row,"Approved asset transfer")
@router.post("/assets/{asset_id}/disposal",status_code=201)
def disposal(asset_id:UUID,body:DisposalWrite,db:Session=Depends(get_db),user=Depends(admin)):
    get(db,EnterpriseAsset,asset_id,"Asset");row=AssetDisposal(asset_id=asset_id,**body.model_dump(),approved_by=str(user.id),disposed_at=datetime.now(timezone.utc));db.add(row);return audit(db,user,"APPROVE","asset_disposal",row,"Approved controlled asset disposal")
@router.get("/assets/{asset_id}/timeline")
def timeline(asset_id:UUID,db:Session=Depends(get_db),_=Depends(reader)):get(db,EnterpriseAsset,asset_id,"Asset");return {"lifecycle":db.query(AssetLifecycle).filter_by(asset_id=asset_id).order_by(AssetLifecycle.occurred_at).all(),"locations":db.query(AssetLocationHistory).filter_by(asset_id=asset_id).order_by(AssetLocationHistory.effective_at).all(),"assignments":db.query(AssetAssignment).filter_by(asset_id=asset_id).order_by(AssetAssignment.assigned_at).all(),"costs":db.query(AssetCost).filter_by(asset_id=asset_id).all()}
@router.post("/assets/recalculate-depreciation")
def recalculate(db:Session=Depends(get_db),user=Depends(admin)):
    changed=0
    for row in db.query(EnterpriseAsset).filter(~EnterpriseAsset.lifecycle_stage.in_(("disposed","archived"))).limit(10000):values=depreciation(row);row.depreciation_value=values["depreciation"];row.current_value=values["current_value"];changed+=1
    create_audit_log(db,user.username,"RECALCULATE","asset_finance",None,f"Recalculated {changed} assets");db.commit();return {"updated":changed}
@router.get("/assets/{asset_id}/financials")
def financials(asset_id:UUID,db:Session=Depends(get_db),_=Depends(reader)):
    row=get(db,EnterpriseAsset,asset_id,"Asset");calc=depreciation(row);costs=dict(db.query(AssetCost.cost_type,func.coalesce(func.sum(AssetCost.amount),0)).filter_by(asset_id=asset_id).group_by(AssetCost.cost_type).all());tco=Decimal(row.purchase_cost or 0)+sum((Decimal(v) for v in costs.values()),Decimal(0));return {**calc,"purchase_cost":row.purchase_cost,"residual_value":row.residual_value,"maintenance_cost":costs.get("maintenance",0),"repair_cost":costs.get("repair",0),"replacement_cost":costs.get("replacement",0),"tco":tco}

@router.get("/vendors")
def vendors(search:str|None=None,page:int=1,page_size:int=Query(25,le=100),db:Session=Depends(get_db),_=Depends(reader)):
    q=db.query(Vendor);q=q.filter(or_(Vendor.legal_name.ilike(f"%{search}%"),Vendor.vendor_number.ilike(f"%{search}%"))) if search else q;return {"items":q.order_by(Vendor.legal_name).offset((page-1)*page_size).limit(page_size).all(),"total":q.count()}
@router.post("/vendors",status_code=201)
def create_vendor(body:VendorWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    data=body.model_dump();data["service_regions"]=json.dumps(data["service_regions"]);row=Vendor(**data,vendor_number=number(db,"VND",Vendor),created_by=str(user.id));db.add(row);return audit(db,user,"CREATE","vendor",row,"Created vendor for approval")
@router.get("/vendors/{vendor_id}")
def vendor(vendor_id:UUID,db:Session=Depends(get_db),_=Depends(reader)):return {"vendor":get(db,Vendor,vendor_id,"Vendor"),"contacts":db.query(VendorContact).filter_by(vendor_id=vendor_id).all(),"locations":db.query(VendorLocation).filter_by(vendor_id=vendor_id).all(),"certifications":db.query(VendorCertification).filter_by(vendor_id=vendor_id).all(),"reviews":db.query(VendorReview).filter_by(vendor_id=vendor_id).order_by(desc(VendorReview.reviewed_at)).all(),"performance":db.query(VendorPerformance).filter_by(vendor_id=vendor_id).order_by(desc(VendorPerformance.period_end)).all()}
@router.post("/vendors/{vendor_id}/approve")
def approve_vendor(vendor_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):row=get(db,Vendor,vendor_id,"Vendor");row.approved=True;row.status="approved";return audit(db,user,"APPROVE","vendor",row,"Added vendor to approved list")
@router.post("/vendors/{vendor_id}/reviews")
def review_vendor(vendor_id:UUID,body:ReviewWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    vendor=get(db,Vendor,vendor_id,"Vendor");review=VendorReview(vendor_id=vendor_id,rating=body.rating,findings=body.findings,recommendation=body.recommendation,reviewed_by=str(user.id));scores=[body.delivery_score,body.quality_score,body.support_score,body.compliance_score];perf=VendorPerformance(vendor_id=vendor_id,period_start=date.today().replace(day=1),period_end=date.today(),delivery_score=scores[0],quality_score=scores[1],support_score=scores[2],compliance_score=scores[3],overall_score=sum(scores)/4);db.add_all([review,perf]);db.flush();vendor.rating=Decimal(body.rating);return audit(db,user,"REVIEW","vendor",review,"Recorded deterministic vendor scorecard")

@router.get("/procurement/requests")
def requests(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(PurchaseRequest).order_by(desc(PurchaseRequest.created_at)).limit(100).all()}
@router.post("/procurement/requests",status_code=201)
def create_request(body:RequestWrite,db:Session=Depends(get_db),user=Depends(contributor)):row=PurchaseRequest(**body.model_dump(),request_number=number(db,"PR",PurchaseRequest),requested_by=str(user.id));db.add(row);return audit(db,user,"CREATE","purchase_request",row,"Created purchase request")
@router.post("/procurement/requests/{request_id}/submit")
def submit_request(request_id:UUID,db:Session=Depends(get_db),user=Depends(contributor)):
    row=get(db,PurchaseRequest,request_id,"Purchase request")
    if row.status!="draft":raise HTTPException(409,"Only draft requests can be submitted")
    if row.budget_id:
        budget=get(db,ProcurementBudget,row.budget_id,"Budget");available=budget.allocated-budget.committed-budget.spent
        if available<row.requested_amount:raise HTTPException(409,"Insufficient approved budget")
    row.status="submitted";db.add(ProcurementApproval(purchase_request_id=row.id,sequence=1));return audit(db,user,"SUBMIT","purchase_request",row,"Submitted for explicit approval")
@router.post("/procurement/requests/{request_id}/decision")
def decide_request(request_id:UUID,body:DecisionWrite,db:Session=Depends(get_db),user=Depends(admin)):
    row=get(db,PurchaseRequest,request_id,"Purchase request");approval=db.query(ProcurementApproval).filter_by(purchase_request_id=row.id,status="pending").order_by(ProcurementApproval.sequence).first()
    if row.status!="submitted" or not approval:raise HTTPException(409,"Request is not awaiting approval")
    approval.status="approved" if body.decision=="approve" else "rejected";approval.approver_id=str(user.id);approval.decision_notes=body.notes;approval.decided_at=datetime.now(timezone.utc);row.status=approval.status
    if row.status=="approved" and row.budget_id:get(db,ProcurementBudget,row.budget_id,"Budget").committed+=row.requested_amount
    return audit(db,user,body.decision.upper(),"purchase_request",row,body.notes)
@router.get("/procurement/orders")
def orders(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(PurchaseOrder).order_by(desc(PurchaseOrder.issued_at)).limit(100).all()}
@router.post("/procurement/orders",status_code=201)
def create_order(body:OrderWrite,db:Session=Depends(get_db),user=Depends(admin)):
    req=get(db,PurchaseRequest,body.purchase_request_id,"Purchase request");vendor=get(db,Vendor,body.vendor_id,"Vendor")
    if req.status!="approved" or not vendor.approved:raise HTTPException(409,"An approved request and approved vendor are required")
    total=sum((Decimal(str(item["unit_cost"]))*int(item["quantity"]) for item in body.items),Decimal(0))
    if total>req.requested_amount:raise HTTPException(409,"Order exceeds approved request amount")
    row=PurchaseOrder(order_number=number(db,"PO",PurchaseOrder),purchase_request_id=req.id,vendor_id=vendor.id,property_id=req.property_id,total_amount=total,currency=req.currency,issued_by=str(user.id));db.add(row);db.flush();[db.add(PurchaseOrderItem(purchase_order_id=row.id,description=item["description"],quantity=int(item["quantity"]),unit_cost=Decimal(str(item["unit_cost"])),asset_category_id=item.get("asset_category_id"))) for item in body.items];req.status="ordered";return audit(db,user,"ISSUE","purchase_order",row,"Issued approved purchase order")
@router.post("/procurement/receive",status_code=201)
def receive(body:ReceiveWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    item=get(db,PurchaseOrderItem,body.purchase_order_item_id,"Purchase order item")
    if item.received_quantity+body.quantity>item.quantity:raise HTTPException(409,"Receiving quantity exceeds outstanding quantity")
    row=ReceivingRecord(**body.model_dump(exclude={"serial_numbers"}),serial_numbers=json.dumps(body.serial_numbers),received_by=str(user.id));db.add(row);item.received_quantity+=body.quantity;order=get(db,PurchaseOrder,item.purchase_order_id,"Purchase order");all_items=db.query(PurchaseOrderItem).filter_by(purchase_order_id=order.id).all();order.status="received" if all(x.received_quantity>=x.quantity for x in all_items) else "partially_received";return audit(db,user,"RECEIVE","purchase_order",row,"Recorded human-verified receiving")

@router.get("/contracts")
def contracts(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(Contract).order_by(Contract.end_date).limit(100).all()}
@router.post("/contracts",status_code=201)
def create_contract(body:ContractWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    if body.end_date<=body.start_date:raise HTTPException(422,"Contract end must follow start")
    get(db,Vendor,body.vendor_id,"Vendor");row=Contract(**body.model_dump(),contract_number=number(db,"CTR",Contract),created_by=str(user.id));db.add(row);return audit(db,user,"CREATE","contract",row,"Created contract draft")
@router.post("/contracts/{contract_id}/activate")
def activate_contract(contract_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):row=get(db,Contract,contract_id,"Contract");row.status="active";return audit(db,user,"ACTIVATE","contract",row,"Activated reviewed contract")
@router.post("/contracts/{contract_id}/renewals")
def renewal(contract_id:UUID,body:RenewalWrite,db:Session=Depends(get_db),user=Depends(contributor)):contract=get(db,Contract,contract_id,"Contract");row=ContractRenewal(contract_id=contract.id,**body.model_dump());db.add(row);return audit(db,user,"CREATE","contract_renewal",row,"Created renewal proposal")
@router.post("/contracts/renewals/{renewal_id}/approve")
def approve_renewal(renewal_id:UUID,db:Session=Depends(get_db),user=Depends(admin)):
    row=get(db,ContractRenewal,renewal_id,"Renewal");contract=get(db,Contract,row.contract_id,"Contract");row.status="approved";row.approved_by=str(user.id);row.decided_at=datetime.now(timezone.utc);contract.end_date=row.proposed_end_date;contract.value=row.proposed_value;contract.version+=1;return audit(db,user,"APPROVE","contract_renewal",row,"Approved contract renewal")

@router.get("/warranties")
def warranties(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(Warranty).order_by(Warranty.end_date).limit(100).all(),"claims":db.query(WarrantyClaim).order_by(desc(WarrantyClaim.submitted_at)).limit(100).all()}
@router.post("/warranties",status_code=201)
def create_warranty(body:WarrantyWrite,db:Session=Depends(get_db),user=Depends(contributor)):get(db,EnterpriseAsset,body.asset_id,"Asset");row=Warranty(**body.model_dump());db.add(row);return audit(db,user,"CREATE","warranty",row,"Created asset warranty")
@router.post("/warranties/{warranty_id}/claims",status_code=201)
def claim(warranty_id:UUID,body:ClaimWrite,db:Session=Depends(get_db),user=Depends(contributor)):get(db,Warranty,warranty_id,"Warranty");row=WarrantyClaim(warranty_id=warranty_id,claim_number=number(db,"WCL",WarrantyClaim),**body.model_dump(),submitted_by=str(user.id));db.add(row);return audit(db,user,"CREATE","warranty_claim",row,"Submitted warranty claim")

@router.get("/licenses")
def licenses(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(SoftwareLicense).order_by(SoftwareLicense.renewal_date).limit(100).all(),"products":db.query(SoftwareProduct).order_by(SoftwareProduct.name).all()}
@router.post("/licenses/products",status_code=201)
def create_product(body:ProductWrite,db:Session=Depends(get_db),user=Depends(contributor)):row=SoftwareProduct(**body.model_dump());db.add(row);return audit(db,user,"CREATE","software_product",row,"Created software product")
@router.post("/licenses",status_code=201)
def create_license(body:LicenseWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    data=body.model_dump(exclude={"license_key"});data["license_key_ciphertext"]="stored-by-secret-provider" if body.license_key else None;row=SoftwareLicense(**data,license_number=number(db,"LIC",SoftwareLicense));db.add(row);return audit(db,user,"CREATE","software_license",row,"Created software license without returning its key")
@router.post("/licenses/{license_id}/assignments",status_code=201)
def assign_license(license_id:UUID,body:AssignmentWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    lic=get(db,SoftwareLicense,license_id,"License")
    if lic.seats_allocated>=lic.seats_purchased:raise HTTPException(409,"No license seats available")
    if not body.asset_id and not body.user_id:raise HTTPException(422,"Asset or user assignment is required")
    row=LicenseAssignment(license_id=license_id,**body.model_dump());db.add(row);lic.seats_allocated+=1;return audit(db,user,"ASSIGN","software_license",row,"Assigned licensed seat")
@router.post("/licenses/compliance/check")
def compliance(db:Session=Depends(get_db),user=Depends(admin)):
    checked=0
    for lic in db.query(SoftwareLicense).limit(10000):variance=lic.seats_purchased-lic.seats_allocated;status="compliant" if variance>=0 else "over_allocated";db.add(LicenseCompliance(license_id=lic.id,status=status,purchased=lic.seats_purchased,allocated=lic.seats_allocated,variance=variance,findings="Deterministic purchased-versus-allocated seat comparison."));checked+=1
    create_audit_log(db,user.username,"CHECK","license_compliance",None,f"Checked {checked} licenses");db.commit();return {"checked":checked}

@router.get("/inventory")
def inventory(db:Session=Depends(get_db),_=Depends(reader)):return {"items":db.query(InventoryItem).order_by(InventoryItem.name).all(),"balances":db.query(StockBalance).all(),"locations":db.query(InventoryLocation).all()}
@router.post("/inventory/items",status_code=201)
def create_inventory_item(body:InventoryItemWrite,db:Session=Depends(get_db),user=Depends(contributor)):row=InventoryItem(**body.model_dump());db.add(row);return audit(db,user,"CREATE","inventory_item",row,"Created inventory item")
@router.post("/inventory/locations",status_code=201)
def create_inventory_location(body:InventoryLocationWrite,db:Session=Depends(get_db),user=Depends(admin)):row=InventoryLocation(**body.model_dump());db.add(row);return audit(db,user,"CREATE","inventory_location",row,"Created inventory location")
@router.post("/inventory/movements",status_code=201)
def stock(body:StockWrite,db:Session=Depends(get_db),user=Depends(contributor)):
    item=get(db,InventoryItem,body.item_id,"Inventory item");get(db,InventoryLocation,body.location_id,"Inventory location");balance=db.query(StockBalance).filter_by(item_id=item.id,location_id=body.location_id).first() or StockBalance(item_id=item.id,location_id=body.location_id,quantity=0);db.add(balance);change=abs(body.quantity) if body.movement_type in ("receive","transfer_in") else -abs(body.quantity) if body.movement_type in ("issue","transfer_out") else body.quantity
    if balance.quantity+change<0:raise HTTPException(409,"Stock movement would produce a negative balance")
    balance.quantity+=change;row=StockMovement(**body.model_dump(exclude={"quantity"}),quantity=change,actor_id=str(user.id));db.add(row);return audit(db,user,"MOVE","inventory_stock",row,"Recorded stock movement")
@router.post("/assets/{asset_id}/relationships",status_code=201)
def relationship(asset_id:UUID,body:RelationshipWrite,db:Session=Depends(get_db),user=Depends(contributor)):get(db,EnterpriseAsset,asset_id,"Asset");row=AssetRelationship(asset_id=asset_id,**body.model_dump(),created_by=str(user.id));db.add(row);return audit(db,user,"CREATE","asset_relationship",row,"Linked enterprise asset relationship")
@router.get("/assets/{asset_id}/relationships")
def relationships(asset_id:UUID,db:Session=Depends(get_db),_=Depends(reader)):row=get(db,EnterpriseAsset,asset_id,"Asset");edges=db.query(AssetRelationship).filter_by(asset_id=asset_id).all();return {"nodes":[{"id":str(row.id),"type":"asset","label":row.asset_number}]+[{"id":str(e.target_id),"type":e.target_type,"label":e.target_type} for e in edges],"edges":[{"source":str(row.id),"target":str(e.target_id),"type":e.relationship_type} for e in edges]}

@router.get("/reports/summary")
def report(db:Session=Depends(get_db),_=Depends(reader)):
    total=db.query(EnterpriseAsset).count();purchase=Decimal(db.query(func.coalesce(func.sum(EnterpriseAsset.purchase_cost),0)).scalar());current=Decimal(db.query(func.coalesce(func.sum(EnterpriseAsset.current_value),0)).scalar());return {"assets":total,"purchase_cost":purchase,"current_value":current,"depreciation":purchase-current,"contracts":db.query(Contract).count(),"vendors":db.query(Vendor).count(),"procurement_spend":db.query(func.coalesce(func.sum(PurchaseOrder.total_amount),0)).scalar(),"licenses":db.query(SoftwareLicense).count(),"inventory_units":db.query(func.coalesce(func.sum(StockBalance.quantity),0)).scalar()}
@router.get("/reports/export")
def export(format:str=Query(pattern=r"^(csv|xlsx|pdf)$"),db:Session=Depends(get_db),_=Depends(reader)):
    rows=db.query(EnterpriseAsset).order_by(EnterpriseAsset.asset_number).limit(10000).all();headers=["asset_number","asset_tag","manufacturer","model","status","lifecycle_stage","purchase_cost","current_value","warranty_end"]
    if format=="csv":s=io.StringIO();w=csv.writer(s);w.writerow(headers);[w.writerow([getattr(r,h) for h in headers]) for r in rows];return Response(s.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=enterprise-assets.csv"})
    if format=="xlsx":wb=Workbook();ws=wb.active;ws.title="Enterprise Assets";ws.append(headers);[ws.append([str(getattr(r,h) or "") for h in headers]) for r in rows];out=io.BytesIO();wb.save(out);return Response(out.getvalue(),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":"attachment; filename=enterprise-assets.xlsx"})
    lines=["HIOP Enterprise Asset Summary",*[' | '.join(str(getattr(r,h) or '') for h in headers)[:110] for r in rows[:45]]];escaped=[x.replace("\\","\\\\").replace("(","\\(").replace(")","\\)") for x in lines];content="BT /F1 9 Tf 40 790 Td 12 TL "+" Tj T* ".join(f"({x})" for x in escaped)+" Tj ET";objs=["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>","<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",f"<< /Length {len(content.encode())} >>\nstream\n{content}\nendstream","<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"];pdf=bytearray(b"%PDF-1.4\n");offsets=[]
    for i,obj in enumerate(objs,1):offsets.append(len(pdf));pdf.extend(f"{i} 0 obj\n{obj}\nendobj\n".encode())
    xref=len(pdf);pdf.extend(f"xref\n0 6\n0000000000 65535 f \n".encode());[pdf.extend(f"{o:010d} 00000 n \n".encode()) for o in offsets];pdf.extend(f"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode());return Response(bytes(pdf),media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=enterprise-assets.pdf"})
