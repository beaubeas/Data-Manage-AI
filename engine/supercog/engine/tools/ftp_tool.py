import os
from supercog.engine.tool_factory import ToolFactory, ToolCategory
from ftplib import FTP
from typing import Any, Callable, Optional
from pydantic import Field

class FTPTool(ToolFactory):
    ftp: Optional[FTP] = Field(default=None, exclude=True)

    def __init__(self):
        super().__init__(
            id="ftp_connector",
            system_name="FTP",
            logo_url="https://logo.clearbit.com/ftp-mac.com",
            auth_config={},
            category=ToolCategory.CATEGORY_FILES,
            help="""
Enhanced FTP tool with extended capabilities for reading, writing,
and managing FTP files and directories.
"""
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.connect,
            self.disconnect,
            self.get_ftp_file,
            self.put_ftp_file,
            self.ls,
            self.mkdir,
            self.rmdir,
            self.delete_file,
            self.rename_file,
            self.change_permissions
        ])

    def connect(self, host: str, username: str = 'anonymous', password: str = 'anonymous@') -> dict:
        """Connect to an FTP server."""
        self.ftp = FTP(host)
        self.ftp.login(username, password)
        return {"status": "success", "message": f"Connected to {host}"}

    def disconnect(self) -> dict:
        """Disconnect from the FTP server."""
        if self.ftp:
            self.ftp.quit()
            self.ftp = None
        return {"status": "success", "message": "Disconnected from FTP server"}

    def get_ftp_file(self, remote_path: str, local_path: str) -> dict:
        """Download a file from the FTP server."""
        if not self.ftp:
            return {"status": "error", "message": "Not connected to FTP server"}
        with open(local_path, 'wb') as fp:
            self.ftp.retrbinary(f'RETR {remote_path}', fp.write)
        return {"status": "success", "message": f"Downloaded {remote_path} to {local_path}"}

    def put_ftp_file(self, local_path: str, remote_path: str) -> dict:
        """Upload a file to the FTP server."""
        if not self.ftp:
            return {"status": "error", "message": "Not connected to FTP server"}
        with open(local_path, 'rb') as fp:
            self.ftp.storbinary(f'STOR {remote_path}', fp)
        return {"status": "success", "message": f"Uploaded {local_path} to {remote_path}"}

    def ls(self, directory: str = '.') -> dict:
        """List files and directories in the specified directory."""
        if not self.ftp:
            return {"status": "error", "message": "Not connected to FTP server"}
        files = []
        self.ftp.cwd(directory)
        self.ftp.retrlines('LIST', files.append)

        file_dict = {}
        for file in files:
            parts = file.split(maxsplit=8)
            if len(parts) == 9:
                file_info = {
                    'permissions': parts[0],
                    'num': parts[1],
                    'owner': parts[2],
                    'group': parts[3],
                    'size': parts[4],
                    'date': ' '.join(parts[5:8]),
                    'name': parts[8]
                }
                file_dict[parts[8]] = file_info

        return {"status": "success", "directory": directory, "files": file_dict}

    def mkdir(self, directory: str) -> dict:
        """Create a new directory on the FTP server."""
        if not self.ftp:
            return {"status": "error", "message": "Not connected to FTP server"}
        self.ftp.mkd(directory)
        return {"status": "success", "message": f"Created directory {directory}"}

    def rmdir(self, directory: str) -> dict:
        """Remove a directory from the FTP server."""
        if not self.ftp:
            return {"status": "error", "message": "Not connected to FTP server"}
        self.ftp.rmd(directory)
        return {"status": "success", "message": f"Removed directory {directory}"}

    def delete_file(self, file_path: str) -> dict:
        """Delete a file from the FTP server."""
        if not self.ftp:
            return {"status": "error", "message": "Not connected to FTP server"}
        self.ftp.delete(file_path)
        return {"status": "success", "message": f"Deleted file {file_path}"}

    def rename_file(self, old_name: str, new_name: str) -> dict:
        """Rename a file on the FTP server."""
        if not self.ftp:
            return {"status": "error", "message": "Not connected to FTP server"}
        self.ftp.rename(old_name, new_name)
        return {"status": "success", "message": f"Renamed {old_name} to {new_name}"}

    def change_permissions(self, file_path: str, permissions: str) -> dict:
        """Change permissions of a file on the FTP server."""
        if not self.ftp:
            return {"status": "error", "message": "Not connected to FTP server"}
        self.ftp.sendcmd(f'SITE CHMOD {permissions} {file_path}')
        return {"status": "success", "message": f"Changed permissions of {file_path} to {permissions}"}
