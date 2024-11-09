# Eventually we should have a proper RESTful credentials
# services. But as an expendient for now I have just implemented
# simple service wrapper which stores credentials, encrypted,
# in the main database.

import os
from typing import Optional

from sqlmodel import SQLModel, Field
from sqlmodel import Session, select

from .services import db_connect, config

class CredentialSecret(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: str
    user_id: Optional[str] = None
    credential_id: str
    secret: bytes  # Encrypted secret

from cryptography.fernet import Fernet
import os

class EncryptionHelper:
    def __init__(self) -> None:
        self.key = config.get_global('CREDENTIALS_MASTER_KEY')
        if not self.key:
            raise ValueError("CREDENTIALS_MASTER_KEY environment variable not set.")
        self.fernet = Fernet(self.key.encode())

    @staticmethod
    def generate_key():
        return Fernet.generate_key()

    def encrypt(self, data: bytes) -> bytes:
        return self.fernet.encrypt(data)

    def decrypt(self, data: bytes) -> bytes:
        return self.fernet.decrypt(data)


class SecretsService:
    """
        The Secrets services stores credential secrets for us. The Credential model
        stores creds created by Users and made either private or shared within their
        Tenant. But "sharing" a Credential means allowing some other User in the Tenant
        to look up its value. In order to actually retrieve the Secrets for the
        Credential you have to know the original tenant and user.
    """
    SERVICE_NAME = "credentials"

    def __init__(self):
        self.engine = db_connect(SecretsService.SERVICE_NAME)
        SQLModel.metadata.create_all(self.engine)
        self.encrypter = EncryptionHelper()

    def reconnect(self):
        self.engine.dispose()
        self.engine = db_connect(SecretsService.SERVICE_NAME)

    def set_credential(
            self, 
            tenant_id: str, 
            user_id: str, 
            credential_id: str, 
            secret: str
        ) -> CredentialSecret:
        return self._set_credential(tenant_id, user_id, credential_id, secret.encode())
    
    def _set_credential(
            self, 
            tenant_id: str, 
            user_id: Optional[str], 
            credential_id: str, 
            secret: bytes
        ) -> CredentialSecret:
        encrypted_secret = self.encrypter.encrypt(secret)
        with Session(self.engine) as session:
            # Don't allow dupes. We should have an index for this
            for existing in session.exec(select(CredentialSecret).where(
                CredentialSecret.tenant_id == tenant_id,
                CredentialSecret.user_id == user_id,
                CredentialSecret.credential_id == credential_id
            )):
                session.delete(existing)

            cred_secret = CredentialSecret(
                tenant_id=tenant_id, 
                user_id=user_id, 
                credential_id=credential_id, 
                secret=encrypted_secret
            )
            session.add(cred_secret)
            session.commit()
            session.refresh(cred_secret)
            return cred_secret

    def get_credential(
            self, 
            tenant_id: str, 
            user_id: str, 
            credential_id: str
        ) -> Optional[str]:
        bval: bytes = self._get_credential(tenant_id, user_id, credential_id)
        return bval.decode() if bval else None

    def _get_credential(
            self, 
            tenant_id: str, 
            user_id: str, 
            credential_id: str
        ) -> bytes:
        """ The key is that to retrieve a cred secret you must know the credential ID
            AND the tenant and user IDs.
        """
        with Session(self.engine) as session:
            query = select(CredentialSecret).where(
                CredentialSecret.tenant_id == tenant_id,
                CredentialSecret.user_id == user_id,
                CredentialSecret.credential_id == credential_id)
            credential = session.exec(query).first()
            if credential:
                return self.encrypter.decrypt(credential.secret)
            return None

    def delete_credential(
            self, 
            tenant_id: str, 
            user_id: str, 
            credential_id: str
        ):
        with Session(self.engine) as session:
            query = select(CredentialSecret).where(
                CredentialSecret.tenant_id == tenant_id,
                CredentialSecret.user_id == user_id,
                CredentialSecret.credential_id == credential_id)
            cred_secret = session.exec(query).first()
            if cred_secret:
                session.delete(cred_secret)
                session.commit()

    def delete_credentials(
            self,
            tenant_id: str,
            user_id: str,
            credential_ids: list[str],
    ):
        with Session(self.engine) as session:
            query = select(CredentialSecret).where(
                CredentialSecret.tenant_id == tenant_id,
                CredentialSecret.user_id == user_id,
                CredentialSecret.credential_id.in_(credential_ids)
            )
            cred_secrets = session.exec(query).all()
            for cred_secret in cred_secrets:
                session.delete(cred_secret)
            session.commit()

    def list_credentials(
            self,
            tenant_id: str,
            user_id: str,
            prefix: str|None=None,
            include_values: bool=False,
    ):
        """ Returns a list of credential ID's matching the prefix owned by the user. If
            include_value is True then returns a list of (key,value) tuples. """
        with Session(self.engine) as session:
            if prefix is None:
                query = select(CredentialSecret).where(
                    CredentialSecret.tenant_id == tenant_id,
                    CredentialSecret.user_id == user_id)
            else:
                query = select(CredentialSecret).where(
                    CredentialSecret.tenant_id == tenant_id,
                    CredentialSecret.user_id == user_id,
                    CredentialSecret.credential_id.like(f"{prefix}%")
                )
            creds = session.exec(query).all()
            if include_values:
                return [(c.credential_id, self.encrypter.decrypt(c.secret).decode()) for c in creds]
            else:
                return [c.credential_id for c in creds]

def reset_secrets_connection():
    global secrets_service
    secrets_service.reconnect()

if __name__ == "__main__": 
    # Example usage
    print("Generated key: ", EncryptionHelper.generate_key().decode())
else:
    secrets_service = SecretsService()
