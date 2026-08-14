from datetime import date,datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel,Field,field_validator

class ProcurementItemCreate(BaseModel):
    description:str=Field(min_length=1,max_length=500);device_type:str=Field(default="Other",max_length=80);quantity_requested:int=Field(gt=0,le=10000);unit_cost:Decimal=Field(default=0,ge=0,max_digits=18,decimal_places=2)
class ProcurementCreate(BaseModel):
    title:str=Field(min_length=2,max_length=220);description:str|None=Field(default=None,max_length=4000);reference_number:str|None=Field(default=None,max_length=80);department_id:UUID|None=None;vendor_id:UUID|None=None;currency:str="NGN";expected_delivery_date:date|None=None;notes:str|None=Field(default=None,max_length=4000);items:list[ProcurementItemCreate]=Field(min_length=1,max_length=100)
    @field_validator("currency")
    @classmethod
    def currency_code(cls,value):
        value=value.upper()
        if value not in {"NGN","USD","EUR","GBP"}:raise ValueError("Unsupported currency")
        return value
class ProcurementUpdate(BaseModel):
    title:str|None=Field(default=None,min_length=2,max_length=220);description:str|None=Field(default=None,max_length=4000);reference_number:str|None=Field(default=None,max_length=80);department_id:UUID|None=None;vendor_id:UUID|None=None;currency:str|None=None;expected_delivery_date:date|None=None;notes:str|None=Field(default=None,max_length=4000)
    @field_validator("currency")
    @classmethod
    def currency_code(cls,value):
        if value is not None and value.upper() not in {"NGN","USD","EUR","GBP"}:raise ValueError("Unsupported currency")
        return value.upper() if value else value
class ProcurementAction(BaseModel):notes:str|None=Field(default=None,max_length=2000)
class ProcurementOrder(ProcurementAction):reference_number:str|None=Field(default=None,max_length=80);expected_delivery_date:date|None=None
class ProcurementReceipt(BaseModel):item_id:UUID;quantity:int=Field(gt=0,le=10000);notes:str|None=Field(default=None,max_length=2000)
class ProcurementAssetLinkCreate(BaseModel):asset_id:UUID;item_id:UUID|None=None
