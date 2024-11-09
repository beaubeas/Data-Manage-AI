from sqlmodel import Session, select, or_
from sqlalchemy import func

from .jwt_auth import User
from .db import DocIndex

from supercog.shared.models import PERSONAL_INDEX_NAME

def get_ragie_partition(tenant_id, index_id):
    return f"{tenant_id}__{index_id}"

def get_user_personal_index(user: User, session: Session) -> DocIndex|None:
    # get DocIndex
    index = session.exec(
        select(DocIndex).where(
            DocIndex.tenant_id == user.tenant_id,
            DocIndex.user_id == user.user_id,
            DocIndex.id == user.personal_index_id()
        )
    ).first()

    return index     

def lookup_index(index_name: str, user: User, session: Session) -> DocIndex|None:
    if 'index_name' == PERSONAL_INDEX_NAME:
        return get_user_personal_index(user, session)
    
    index = session.exec(
        select(DocIndex).where(
            DocIndex.tenant_id == user.tenant_id,
            DocIndex.user_id == user.user_id,
            DocIndex.name.ilike(f"{index_name}%")
        )
    ).first()
    return index

def get_available_indexes(
          session: Session, 
          user: User, 
          include_private: bool = False,
          include_shared: bool = False) -> list[DocIndex]:
    # Scope to the tenant, and then either user owned or shared
    if include_private and include_shared:
        query = select(DocIndex).where(
            DocIndex.tenant_id == user.tenant_id,
            or_(
                DocIndex.user_id == user.user_id,
                DocIndex.scope == "shared"
            )
        )
    elif include_private:
        query = select(DocIndex).where(
            DocIndex.tenant_id == user.tenant_id,
            DocIndex.user_id == user.user_id
        )
    elif include_shared:
        query = select(DocIndex).where(
            DocIndex.tenant_id == user.tenant_id,
            DocIndex.scope == "shared"
        )
    return list(session.exec(query).all()
    )
