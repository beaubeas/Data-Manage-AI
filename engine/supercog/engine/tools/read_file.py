import asyncio
import os
from typing import Callable
import pytextract
import pandas as pd
import glob
import requests
import html2text
import chardet
import PyPDF2
import markdown2
from fpdf import FPDF

from supercog.engine.tool_factory import ToolFactory, ToolCategory, LangChainCallback
from supercog.engine.email_utils  import process_email
from supercog.engine.file_utils   import read_eml, read_pdf

class ReadFileTool(ToolFactory):
    credentials: dict = {}

    def __init__(self):
        super().__init__(
            id="read_file",
            system_name="File Access",
            logo_url="https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRRxjZhawty_IUsjt2xke_qk2AIZCpVd7luGJrTo-emag&s",
            auth_config={},
            category=ToolCategory.CATEGORY_FILES,
            help="""
Read, save, list, and extract content from files.
""",
        )
    
    def get_tools(self) -> list[Callable]:
        # Assuming 'perform_daily_maintenance' is a sample function you'd like to implement
        return self.wrap_tool_functions([
            self.list_filesystem_files,
            self.mkdir, 
            self.read_file,
            self.save_file,
            self.save_pdf_file,
            self.create_agent_directory,
        ])
    
    def create_agent_directory(self) -> str:
        """
        Create and return the path to an agent-specific directory.
        The directory name will consist of the agent name with the character _ and then the agent id.
        """
        agent_dir = self.run_context.create_agent_directory()
        return agent_dir
    
    def read_file(self, file_name: str):
        """
        Returns the contents of the given file.

        This function handles different file types and formats, including:
        - HTTP URLs: Downloads the file.
        - Excel files .xlsx .xls and .csv: Reads the content into a DataFrame and returns a preview.
        - COBOL files (.cbl): Reads and returns the file content as a string.
        - PDF files (.pdf): Extracts text from all pages.
        - EML files (.eml): Parses email content, saves attachments, and returns a structured representation.
        - Other file types: Attempts to extract content using the pytextract library.
        - JSON files: Decodes content with detected encoding, fixes formatting issues, and converts it to a JSON string.

        Args:
            file_name (str): The path to the file to be read.

        Returns:
            str or dict: The content of the file, or a structured representation for specific file types like .eml.
        """
        if file_name.startswith("http"):
            return self._file_download(file_name)
        if file_name.endswith(".xlsx") or file_name.endswith(".xls"):
            df = pd.read_excel(file_name, engine='openpyxl')
            return self.get_dataframe_preview(df)
        elif file_name.endswith(".csv"):
            df = pd.read_csv(file_name)
            return self.get_dataframe_preview(df)
        elif file_name.endswith(".cbl") or file_name.endswith(".CBL"):
            with open(file_name, 'r') as f:
                return f.read()
        elif file_name.endswith(".pdf"):
            return read_pdf(file_name)
        elif file_name.endswith(".eml"):
            agent_dir = self.run_context.create_agent_directory()
            return read_eml(file_name, agent_dir, self.run_context)
        try:
            return pytextract.process(file_name)
        except:
            # Detect the encoding of the file
            with open(file_name, 'rb') as f:
                raw_content = f.read()

            result = chardet.detect(raw_content)
            encoding = result['encoding']

            if encoding is None:
                # If encoding is None, try to read it as binary
                return raw_content.decode('utf-8', errors='replace')

            try:
                content = raw_content.decode(encoding)
            except UnicodeDecodeError:
                # If decoding fails, try to replace errors
                content = raw_content.decode(encoding, errors='replace')
            return content

    def _file_download(self, url: str, limit: int=4000) -> str:
        """ Downloads a file from the web and returns the contents as text, not
            more than `limit` characters. 
        """
        r = requests.get(url)

        if r.status_code == 200:
            mime_type = r.headers.get('content-type') or ""
            if 'html' in mime_type:
                # Use beautifulsoup to extract text
                return html2text.html2text(r.text)[0:limit]
            else:
                return r.text[0:limit]
        else:
            return f"Error: {r.status_code} {r.reason}"
        
    def save_file(self, filename: str, content: str):
        """ Saves the given text content using the provided filename. """
        with open(filename, 'w') as f:
            f.write(content)
        return "file saved"
    
    def save_pdf_file(self, filename: str, content: str, source_format: str="markdown"):
        """ Saves the given text as a PDF file using the provided filename. 
            Source format can be 'markdown', 'text'.
        """

        link = """\n\n_Report created by_ [Supercog](https://supercog.ai)\n"""

        html = markdown2.markdown(content + link)

        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.write_html(html)
        pdf.output(filename)

        self.run_context.upload_user_file_to_s3(
            file_name=filename,
            mime_type="application/pdf"
        )
        download_url: dict = self.run_context.get_file_url(filename)

        return "PDF file saved, download link: " + download_url.get("url", "")

    def mkdir(self, path: str):
        """Create a directory."""
        os.makedirs(path, exist_ok=True)  # Create directory if it doesn't exist
        return "driectory created"
        
    async def list_filesystem_files(self, folder: str=".", callbacks: LangChainCallback=None) -> list[tuple]:
        """ Returns a list of available files on the local agent filesystem with their sizes.
            Folder arg can refer to a sub-folder or be blank.
        """
        await self.log("Getting the list of files...\n", callbacks)
        if ".." in folder or folder.startswith("/") :
            await self.log(f"Ignoring bad folder '{folder}'\n", callbacks)
            folder = ""
    
        glob_pat = os.path.join(folder, "*")
        files_with_sizes = [(filename, os.path.getsize(filename)) for filename in glob.glob(glob_pat)]
        return files_with_sizes
        #await self._delay_for_testing(callbacks)
        #return os.listdir(path)

    async def _delay_for_testing(self, callbacks: LangChainCallback):
        for x in range(20):
            await self.log(f"Next step {x}\n", callbacks)
            print(f"Next step {x}")
            await asyncio.sleep(0.5)


