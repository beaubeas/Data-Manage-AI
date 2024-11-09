from datetime import datetime
import pytz

import reflex as rx

from .agents_common_state import AgentsCommonState

class FilespageState(AgentsCommonState):
    #############################################
    ######## Files page state #############
    #############################################
    file_uploading: bool = False
    files_status: str = ""
    files: list[dict[str,str]] = []
    selected_files: list[str] = []
    is_file_selected: dict[str, bool] = {}
    all_files_selected: bool = False
    debug_info: str = ""
    
    def format_file_size(self, size: int) -> str:
        size_in_bytes: float = float(size)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
            if size_in_bytes < 1024.0:
                return f"{size_in_bytes:3.1f} {unit}"
            size_in_bytes /= 1024.0
        return f"{size_in_bytes:3.1f} HUGE"
    
    def add_debug_info(self, info: str):
        pass
        #self.debug_info += info + "\n"

    def clear_debug_info(self):
        self.debug_info = ""
        
    def print_is_file_selected_debug(self):
        debug_str = "Contents of is_file_selected:\n"
        for file_name, is_selected in self.is_file_selected.items():
            debug_str += f"  {file_name}: {is_selected}\n"
        self.add_debug_info(debug_str)

    def files_page_load(self):
        self.clear_debug_info()
        self.add_debug_info("Loading files...")
        if len(self.folders) == 0:
            self.load_folders()
        self.files_status = "Refreshing file list..."
        yield
        # Call agentsvc.list_files outside the loop
        file_list = self._agentsvc.list_files(self, self.user.tenant_id, self.user.id)
        self.add_debug_info(f"Retrieved {len(file_list)} files from agentsvc")

        self.files = []
        for f in file_list:
            is_selected =  f["name"] in self.selected_files
            try:
                last_mod = datetime.strptime(f["last_modified"], "%Y-%m-%dT%H:%M:%SZ")
            except:
                last_mod = datetime.strptime(f["last_modified"], '%Y-%m-%dT%H:%M:%S.%fZ')

            file_info = {
                "is_selected": is_selected,
                "name": f["name"],
                "size": self.format_file_size(f["size"]),
                "url": f["url"],
                "last_modified": last_mod.replace(tzinfo=pytz.utc)
            }
            self.files.append(file_info)
            if is_selected :
                self.add_debug_info(f"Selected file: {file_info['name']}, {file_info['is_selected']}")

        self.is_file_selected = {file['name']: file['name'] in self.selected_files for file in self.files}
        self.print_is_file_selected_debug()
        self.add_debug_info(f"Total files processed: {len(self.files)}")
        self.service_status = self._agentsvc.status_message
        self.files_status = ""
        self.file_uploading = False

    async def handle_upload(self, files: list[rx.UploadFile]) -> rx.event.EventSpec:
        """Handle the upload of file(s).

        Args:
            files: The uploaded files.
        """
        self.file_uploading = True
        self.files_status = f"Uploading files..."
        yield

        for file in files:
            await self._agentsvc.upload_file(
                self.user.tenant_id,
                self.user.id,
                "",
                file
            )
        self.file_uploading = False 
        yield rx.clear_selected_files("upload1")
        yield FilespageState.files_page_load

    async def delete_file(self, file: str):
        """Delete a file."""
        self.files_status = f"Deleting '{file}'..."
        yield
        self._agentsvc.delete_file(
            self.user.tenant_id,
            self.user.id,
            file,
        )
        self.files_status = ""
        yield FilespageState.files_page_load
        
    def delete_selected_files(self):
        self.files_status = f"Deleting selected files..."

        result = self._agentsvc.delete_files(
            self.user.tenant_id,
            self.user.id,
            self.selected_files,
            #drive='default'  # or whatever drive you're using
        )

        if isinstance(result, str):  # If it returned "No files to delete"
            self.files_status = result
        elif "error" in result:
            self.files_status = f"Error deleting files: {result['error']}"
        else:
            deleted_count = len(result.get('deleted', []))
            error_count = len(result.get('errors', []))
            self.files_status = f"Deleted {deleted_count} files. Errors: {error_count}."

        self.selected_files = []
        yield
        return FilespageState.files_page_load
    
    def toggle_file_selection(self, file_name: str):
        self.add_debug_info(f"toggle_file_selection called with file_name: {file_name}")
        self.add_debug_info(f"Current selected_files before toggle: {self.selected_files}")

        self.is_file_selected[file_name] = not self.is_file_selected.get(file_name, False)
        #self.print_is_file_selected_debug()
        file_index = next(index for (index, file) in enumerate(self.files) if file["name"] == file_name)
        if file_name in self.selected_files:
            self.files[file_index]["is_selected"] = False
            self.selected_files.remove(file_name)
        else:
            self.files[file_index]["is_selected"] = True
            self.selected_files.append(file_name)
        self.all_files_selected = len(self.selected_files) == len(self.files)
        self.add_debug_info(f"selected_files after toggle: {self.selected_files}")
        
    def select_all_files(self, is_checked: bool):
        self.add_debug_info(f"select_all_files called. is_checked: {is_checked}")
        self.add_debug_info(f"Current selected_files: {self.selected_files}")
        self.add_debug_info(f"Total files: {len(self.files)}")

        # Determine the new selection state
        new_selection_state = is_checked if is_checked != self.all_files_selected else not self.all_files_selected

        if new_selection_state:
            self.selected_files = [file['name'] for file in self.files]
            self.add_debug_info(f"Selecting all files: {self.selected_files}")
        else:
            self.selected_files = []
            self.add_debug_info("Clearing all selected files")

        # Update is_selected for all files
        for file in self.files:
            file['is_selected'] = new_selection_state
            self.is_file_selected[file['name']] = new_selection_state
            
        self.all_files_selected = new_selection_state
        self.add_debug_info(f"Updated all_files_selected: {self.all_files_selected}")
        self.add_debug_info(f"Final selected_files: {self.selected_files}")
    
    async def download_s3_file(self, filename: str):
        file_info = self._agentsvc.get_file_info(
            self.user.tenant_id,
            self.user.id,
            filename,
        )
        #print("Got file info: ", file_info)
        if 'error' in file_info:
            self.service_status = file_info['error']
        else:
            return rx.redirect(
                file_info['url'],
                external=True
            )

