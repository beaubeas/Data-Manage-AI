import pytest
from supercog.shared.credentials import SecretsService, EncryptionHelper, CredentialSecret
from sqlmodel import SQLModel
import os

# Setup for tests
@pytest.fixture(scope="module", autouse=True)
def setup_test_env():
    #test_key = EncryptionHelper.generate_key().decode()
    #os.environ['CREDENTIALS_MASTER_KEY'] = test_key
    creds_service = SecretsService()
    yield creds_service
    
@pytest.fixture
def sample_credential():
    return {
        "tenant_id": "test_tenant",
        "user_id": "test_user",
        "credential_id": "slackcreds1:bot-token",
        "secret": "test_secret"
    }

def test_set_credential(setup_test_env, sample_credential):
    creds_service = setup_test_env
    creds_service.set_credential(**sample_credential)
    retrieved_secret = creds_service.get_credential(
        sample_credential['tenant_id'], 
        sample_credential['user_id'], 
        sample_credential['credential_id'])
    assert retrieved_secret == sample_credential['secret'], "The retrieved secret does not match the original"

    bad_secret = creds_service.get_credential(
        sample_credential['tenant_id'], 
        "user_unknown", 
        sample_credential['credential_id'])
    assert bad_secret is None, "Can't retrieve secret without user_id"


def test_get_credential_nonexistent(setup_test_env):
    creds_service = setup_test_env
    assert creds_service.get_credential("nonexistent", "nonexistent", "nonexistent") is None, "Expected None for nonexistent credential"

def test_delete_credential(setup_test_env, sample_credential):
    creds_service = setup_test_env
    cred = creds_service.set_credential(**sample_credential)
    creds_service.delete_credential(cred.tenant_id, cred.user_id, cred.credential_id)
    stored_cred =  creds_service.get_credential(cred.tenant_id, cred.user_id, cred.credential_id)
    assert stored_cred is None, "Credential was not deleted successfully"
