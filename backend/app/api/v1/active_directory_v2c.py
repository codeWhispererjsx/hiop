"""Minimal V2C administration API for read-only AD computer intelligence."""
from fastapi import APIRouter,Depends,HTTPException,Query
from sqlalchemy.orm import Session

from app.core.security import get_db,require_roles
from app.models.active_directory import ActiveDirectoryConnection
from app.schemas.active_directory import ActiveDirectoryConnectionCreate,ActiveDirectoryConnectionUpdate,ActiveDirectorySecretUpdate
from app.services.active_directory_enrichment_service import ActiveDirectoryConfigurationService,safe_connection
from app.services.active_directory_secret_service import ActiveDirectorySecretError
from app.services.active_directory_service import ActiveDirectoryConnectionService
from app.services.ldap_client import LdapError

router=APIRouter(prefix="/discovery-intelligence/active-directory",tags=["Active Directory computer intelligence"]);admin=require_roles(["admin","superadmin"])

def get_connection(db,id):
    row=db.get(ActiveDirectoryConnection,id)
    if not row:raise HTTPException(404,"Active Directory connection not found")
    return row

@router.get("/connections")
def connections(page:int=Query(1,ge=1),page_size:int=Query(25,ge=1,le=100),db:Session=Depends(get_db),_=Depends(admin)):
    query=db.query(ActiveDirectoryConnection).order_by(ActiveDirectoryConnection.name);return {"items":[safe_connection(row) for row in query.offset((page-1)*page_size).limit(page_size).all()],"total":query.count(),"page":page,"page_size":page_size,"pages":max(1,(query.count()+page_size-1)//page_size)}

@router.get("/connections/{id}")
def connection(id:str,db:Session=Depends(get_db),_=Depends(admin)):return safe_connection(get_connection(db,id))

@router.post("/connections",status_code=201)
def create_connection(body:ActiveDirectoryConnectionCreate,db:Session=Depends(get_db),user=Depends(admin)):
    try:return safe_connection(ActiveDirectoryConfigurationService(db).create(body,user))
    except ValueError as error:raise HTTPException(409,str(error)) from error
    except (ActiveDirectorySecretError,LdapError) as error:raise HTTPException(422,getattr(error,"safe_message",str(error))) from error

@router.patch("/connections/{id}")
def update_connection(id:str,body:ActiveDirectoryConnectionUpdate,db:Session=Depends(get_db),user=Depends(admin)):
    try:return safe_connection(ActiveDirectoryConfigurationService(db).update(get_connection(db,id),body,user))
    except LdapError as error:raise HTTPException(422,error.safe_message) from error

@router.post("/connections/{id}/secret")
def update_secret(id:str,body:ActiveDirectorySecretUpdate,db:Session=Depends(get_db),user=Depends(admin)):
    try:return safe_connection(ActiveDirectoryConfigurationService(db).rotate_secret(get_connection(db,id),body.bind_secret,user))
    except ActiveDirectorySecretError as error:raise HTTPException(422,"The bind secret could not be stored securely.") from error

@router.post("/connections/{id}/test")
def test_connection(id:str,db:Session=Depends(get_db),user=Depends(admin)):
    get_connection(db,id);return ActiveDirectoryConnectionService(db).test_connection(id,user)
