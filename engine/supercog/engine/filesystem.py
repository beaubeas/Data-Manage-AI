import os
import builtins
import sys
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime
from unittest.mock import patch

from supercog.shared.services import config

SYSTEM_ROOT_PATH = config.get_global("SYSTEM_ROOT_PATH", False) or "/var/lib/supercog/data"
print("using system root: ", SYSTEM_ROOT_PATH)
orig_open = builtins.open
orig_os_open = os.open
orig_listdir = os.listdir
orig_exists = os.path.exists
orig_makedirs = os.makedirs

WHITELIST_PATHS = [
    "/usr/lib/os-release",
    "/System/Library/CoreServices",
]

site_packages = [s for s in sys.path if "site-packages" in s]
if site_packages:
    site_packages = site_packages[0]
    WHITELIST_PATHS.append(site_packages)

# Supercog provides a filesystem to all running Agents.
# The filesystem uses this structure:
#
# /var/lib/supercog/
#      data/
#          tenant_id/
#              shared/
#              user_id/
#                 files...
#                 uploads/
#                   files...
#                 shared/...
#
# The security intention is that agents can only see files inside of
# their *running user's* directory. They can also see files in "../shared" meaning
# the shared folder inside the tenant.
#
# Security is enforced by patching the system `open` call to enfore the
# permissions, and to treat the user's directory as the root. 

def setup_filesystem():
    if not os.path.exists(SYSTEM_ROOT_PATH):
        try:
            print(f"--------> initializing system root to: {SYSTEM_ROOT_PATH}")
            os.makedirs(SYSTEM_ROOT_PATH)
        except PermissionError:
            raise RuntimeError(
                f"Unable to create system root path: {SYSTEM_ROOT_PATH}. "
                "Please ensure the path is writable by the application."
            )
    os.chdir(SYSTEM_ROOT_PATH)

def access_allowed(file_path, user_dir):
    p = Path(file_path)
    pres = str(p.resolve())
    if pres.startswith(user_dir) or file_path.startswith("/etc/"):
        return True
    for whitep in WHITELIST_PATHS:
        if pres.startswith(whitep):
            return True
    return False

def get_open_function(user_dir):
    def restricted_open(file, mode='r', *args, **kwargs):
        if isinstance(file, bytes):
            file = file.decode("utf-8")
        print("Builtins open: ", file)
        if access_allowed(file, user_dir):
            return orig_open(file, mode, *args, **kwargs)  # Use the real open function here
        else:
            raise PermissionError(f"Access to the file '{file}' is denied")
    return restricted_open

def get_os_open_function(user_dir):
    def restricted_os_open(file, flags, mode=0o777, *args, **kwargs):
        if access_allowed(file, user_dir):
            return orig_os_open(file, flags, mode, *args, **kwargs)  # Use the real open function here
        else:
            raise PermissionError(f"Access to the file '{file}' is denied")
    return restricted_os_open

def get_listdir_function(user_dir):
    def internal_listdir(dir):
        return orig_listdir(os.path.join(user_dir, dir))
    return internal_listdir

def get_makedirs_function(user_dir):
    def internal_makedirs(dir):
        return orig_makedirs(os.path.join(user_dir, dir))
    return internal_makedirs


def get_exists_function(user_dir):
    def internal_exists(dir):
        return orig_exists(os.path.join(user_dir, dir))
    return internal_exists

def get_user_directory(tenant_id, user_id) -> str:
    path = os.path.join(SYSTEM_ROOT_PATH, tenant_id, user_id)
    if not os.path.exists(path):
        os.makedirs(path)
    return path

def get_tenant_directory(tenant_id) -> str:
    path = os.path.abspath(os.path.join(SYSTEM_ROOT_PATH, tenant_id))
    if not os.path.exists(path):
        os.makedirs(path)
    return path

@contextmanager
def get_agent_filesystem(tenant_id, user_id):
    # Ensure the tenant directory exists
    tenant_dir = os.path.join(SYSTEM_ROOT_PATH, tenant_id)
    if not os.path.exists(tenant_dir):
        os.makedirs(tenant_dir)
    
    # Ensure the user directory exists
    user_dir = str(Path(os.path.join(tenant_dir, user_id)).resolve())
    if not os.path.exists(user_dir):
        os.makedirs(user_dir)
    
    # Ensure the user's uploads directory exists
    uploads_dir = os.path.join(user_dir, "uploads")
    if not os.path.exists(uploads_dir):
        os.makedirs(uploads_dir)
    
    # Ensure the user's shared directory exists
    common_shared = os.path.join(tenant_dir, "shared")
    # Ensure the tenant's shared directory exists
    if not os.path.exists(common_shared):
        os.makedirs(common_shared)

    shared_dir = os.path.join(user_dir, "shared")
    if not os.path.exists(shared_dir):
        os.symlink(common_shared, shared_dir)
       
    # Change to the user's directory
    os.chdir(user_dir)

    with patch("builtins.open", get_open_function(user_dir)):
        with patch.multiple(
            "os", 
            open=get_os_open_function(user_dir), listdir=get_listdir_function(user_dir)
        ):
            with patch("os.path.exists", get_exists_function(user_dir)):
                yield

@contextmanager
def unrestricted_filesystem():
    with patch("builtins.open", orig_open), \
         patch("os.open", orig_os_open), \
         patch("os.listdir", orig_listdir), \
         patch("os.makedirs", orig_makedirs), \
         patch("os.path.exists", orig_exists):
        yield
        
def list_modified_files(from_time: datetime, tenant_id, user_id):
    user_dir = get_user_directory(tenant_id, user_id)
    recent_files = []
    comp_time = from_time.timestamp()
    for dirpath, dirnames, files in os.walk(user_dir):
        for file in files:
            file_path = os.path.join(dirpath, file)
            # Get the last modification time and compare
            if os.path.getmtime(file_path) > comp_time:
                recent_files.append(file_path)
    return recent_files

def delete_user_file(tenant_id, user_id, file_name, folder:str="") -> bool:
    user_dir = get_user_directory(tenant_id, user_id)
    file_path = os.path.join(user_dir, folder, file_name)
    if os.path.exists(file_path):
        os.remove(file_path)
        return True
    else:
        return False
