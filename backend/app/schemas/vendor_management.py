from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator

VENDOR_TYPES={"manufacturer","supplier","service_provider","contractor","other"}

class VendorBase(BaseModel):
    name:str=Field(min_length=2,max_length=220)
    vendor_code:str|None=Field(default=None,max_length=40)
    vendor_type:str="other"
    description:str|None=Field(default=None,max_length=3000)
    website:str|None=Field(default=None,max_length=500)
    primary_email:EmailStr|None=None
    primary_phone:str|None=Field(default=None,max_length=80)
    address:str|None=Field(default=None,max_length=2000)
    country:str|None=Field(default=None,max_length=100)
    notes:str|None=Field(default=None,max_length=5000)
    support_agreement_reference:str|None=Field(default=None,max_length=120)
    renewal_date:date|None=None
    products_services:list[str]=Field(default_factory=list,max_length=30)
    @field_validator("vendor_type")
    @classmethod
    def type_valid(cls,value):
        value=value.lower()
        if value not in VENDOR_TYPES:raise ValueError("Unsupported vendor type")
        return value
    @field_validator("vendor_code")
    @classmethod
    def clean_code(cls,value):return value.strip().upper() if value and value.strip() else None
    @field_validator("products_services")
    @classmethod
    def clean_services(cls,value):return list(dict.fromkeys(x.strip() for x in value if x.strip()))

class VendorCreate(VendorBase):pass
class VendorUpdate(BaseModel):
    name:str|None=Field(default=None,min_length=2,max_length=220)
    vendor_code:str|None=Field(default=None,max_length=40)
    vendor_type:str|None=None
    description:str|None=Field(default=None,max_length=3000)
    website:str|None=Field(default=None,max_length=500)
    primary_email:EmailStr|None=None
    primary_phone:str|None=Field(default=None,max_length=80)
    address:str|None=Field(default=None,max_length=2000)
    country:str|None=Field(default=None,max_length=100)
    notes:str|None=Field(default=None,max_length=5000)
    support_agreement_reference:str|None=Field(default=None,max_length=120)
    renewal_date:date|None=None
    products_services:list[str]|None=Field(default=None,max_length=30)
    @field_validator("vendor_type")
    @classmethod
    def type_valid(cls,value):
        if value is None:return value
        value=value.lower()
        if value not in VENDOR_TYPES:raise ValueError("Unsupported vendor type")
        return value
    @field_validator("vendor_code")
    @classmethod
    def clean_code(cls,value):return value.strip().upper() if value and value.strip() else None

class VendorContactCreate(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    role:str=Field(default="Support",max_length=100)
    email:EmailStr|None=None
    phone:str|None=Field(default=None,max_length=80)
    department:str|None=Field(default=None,max_length=120)
    primary:bool=False
    notes:str|None=Field(default=None,max_length=2000)
class VendorContactUpdate(VendorContactCreate):pass
class VendorRelationship(BaseModel):vendor_id:UUID
