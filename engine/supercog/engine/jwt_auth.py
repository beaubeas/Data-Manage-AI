from typing import Optional
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel
import os
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import base64

from supercog.shared.services import config
from supercog.shared.models import DocIndexBase

from .triggerable import TRIGGER_PASSKEY

security = HTTPBearer()

class User(BaseModel):
    user_id: str
    tenant_id: str
    email: Optional[str] = None
    name: Optional[str] = None  
    timezone: Optional[str] = None

    def personal_index_id(self):
        return DocIndexBase.calc_user_personal_index_id(self.user_id, self.tenant_id)
    
def get_public_key():
    public_key_pem = config.get_global("DASH_PUBLIC_KEY")
    if not public_key_pem:
        raise ValueError("DASH_PUBLIC_KEY environment variable not set")
    
    public_key_bytes = base64.b64decode(public_key_pem)
    public_key = serialization.load_pem_public_key(
        public_key_bytes,
        backend=default_backend()
    )
    return public_key

dash_public_key = get_public_key()

def requires_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, dash_public_key, algorithms=['ES256'])
        u = User(
            user_id=payload['sub'], 
            tenant_id=payload['tenant_id'],
            email=payload.get('email'),
            name=payload.get('name'),
            timezone=payload.get('timezone'),
        )
        print("JWT USER: ", u)
        return u
    
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

def requires_jwt_or_triggersvc(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    if token == TRIGGER_PASSKEY:
        # special case to allow Trigger service to authenticate
        return User(user_id="trigger", tenant_id="trigger")
    else:
        return requires_jwt(credentials)
