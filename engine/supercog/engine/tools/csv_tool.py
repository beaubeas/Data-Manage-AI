import os
import random
from supercog.engine.tool_factory import ToolFactory, ToolCategory
import pandas as pd
import numpy as np

from openpyxl import load_workbook
from typing import Any, Callable, Optional
import csv
import datetime
from zoneinfo import ZoneInfo

class CSVTool(ToolFactory):
    credentials: dict = {}

    def __init__(self):
        super().__init__(
            id = "csv_connector",
            system_name = "CSV",
            logo_url=super().logo_from_domain("office.com"),
            auth_config = {},
            category=ToolCategory.CATEGORY_FILES,
            help="""
Read and write CSV files.
"""
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.read_csv_file,
            self.write_csv_file,
            self.append_to_csv_file,
            self.write_to_daily_accumulation_file,
        ])
    
    def read_csv_file(self, file_name: str) -> dict:
        """
        Read a CSV file and return its contents as a dataframe.
    
        Keyword arguments:
        file_name -- full file path
    
        Returns:
        A dictionary with status, message, and dataframe.
        """
        try:
            df = pd.read_csv(file_name)
            return {
                "status": "success",
                "message": "File read successfully",
                "dataframe": self.get_dataframe_preview(df)
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error reading file {file_name}: {str(e)}"
            }
        
    def write_csv_file(
        self,
        file_name: str,
        dataframe_var: Optional[str] = None,
        rows: Optional[list] = None,
        encoding: str = 'utf-8-sig'
    ) -> dict:
        """
        Write data to a CSV file. Data can be provided either as a dataframe or as a list of rows.
    
        Keyword arguments:
        file_name     -- full file path
        dataframe_var -- name of the dataframe variable (optional)
        rows          -- A list of rows, where each row is a list of strings representing the values
                         for each column. The first row should contain the column headers.
        encoding      -- The encoding to use when writing the file (default: 'utf-8')
    
        Returns:
        A dictionary with status and message.
        """
        try:
            if dataframe_var:
                df, _ = self.get_dataframe_from_handle(dataframe_var)
                df.to_csv(file_name, index=False, encoding=encoding, quoting=csv.QUOTE_ALL)
            elif rows:
                with open(file_name, 'w', newline='', encoding=encoding) as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_ALL)
                    writer.writerows(rows)
            else:
                return {
                    "status": "error",
                    "message": "Either dataframe_var or rows must be provided"
                }
            
            # Verify the written content
            #with open(file_name, 'r', encoding=encoding) as f:
            #    content = f.read()
            #    print(f"Sample of written content: {content[:500]}")  # Debug print
            
            return {
                "status": "success",
                "message": f"Data written to {file_name} successfully"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error writing to file {file_name}: {str(e)}"
            }

    def append_to_csv_file(
        self,
        file_name: str,
        dataframe_var: Optional[str] = None,
        rows: Optional[list] = None,
        encoding: str = 'utf-8-sig'
    ) -> dict:
        """
        Append data to an existing CSV file. Data can be provided either as a dataframe or as a list of rows.
        We assume all files come in with a header row and we ignore that row if it is an append.
        Keyword arguments:
        file_name     -- full file path
        dataframe_var -- name of the dataframe variable (optional)
        rows          -- A list of rows, where each row is a list of strings representing the values
                         for each column. The first row should contain the column headers.
        encoding      -- The encoding to use when writing the file (default: 'utf-8-sig')

        Returns:
        A dictionary with status and message.
        """
        try:
            mode = 'a'  # Open file in append mode

            # Check if file exists and is not empty
            file_exists = os.path.isfile(file_name) and os.path.getsize(file_name) > 0

            if dataframe_var:
                # Get the dataframe from the provided variable
                df, _ = self.get_dataframe_from_handle(dataframe_var)

                # Open the file in append mode and do not write the header if the file already exists
                df.to_csv(
                    file_name, 
                    mode=mode, 
                    index=False, 
                    encoding=encoding, 
                    quoting=csv.QUOTE_ALL, 
                    header=not file_exists  # Only write header if the file does not exist
                )
            elif rows:
                # Append rows to the CSV file
                with open(file_name, mode, newline='', encoding=encoding) as f:
                    writer = csv.writer(f, quoting=csv.QUOTE_ALL)

                    if file_exists and rows:
                        writer.writerows(rows[1:])  # Skip headers if the file already exists
                    else:
                        writer.writerows(rows)  # Write everything if file doesn't exist
            else:
                return {
                    "status": "error",
                    "message": "Either dataframe_var or rows must be provided"
                }

            return {
                "status": "success",
                "message": f"Data appended to {file_name} successfully"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error appending to file {file_name}: {str(e)}"
            }

    def write_to_daily_accumulation_file(
        self,
        file_path: str,
        dataframe_var: Optional[str] = None,
        rows: Optional[list] = None,
        encoding: str = 'utf-8-sig',
        timezone: str = 'America/Los_Angeles'
    ) -> dict:
        """
        Append data to a daily accumulation CSV file. The file name will include today's date.

        Keyword arguments:
        file_path     -- full file path (including folders and original file name)
        dataframe_var -- name of the dataframe variable (optional)
        rows          -- A list of rows to append (optional). Row 0 must be a header row with column labels.
        encoding      -- The encoding to use when writing the file (default: 'utf-8-sig')
        timezone      -- The timezone to use for the date in the filename (default: ''America/Los_Angeles').
                         Use IANA timezone names, e.g., 'America/Los_Angeles', 'Europe/London', 'Asia/Tokyo'.
        
        Returns:
        A dictionary with status and message.
        """
        try:
            # Split the file path into directory and file name
            directory, original_file_name = os.path.split(file_path)
            
            # Split the file name and extension
            file_name, file_extension = os.path.splitext(original_file_name)
            
            # Get today's date in DD_MM_YY format
            today_date = datetime.datetime.now(ZoneInfo(timezone)).strftime("%m_%d_%y")
            
            # Construct the new file name with the date
            new_file_name = f"{file_name}_{today_date}{file_extension}"
            
            # Combine the directory and new file name
            new_file_path = os.path.join(directory, new_file_name)
            
            # Call the existing append_to_csv_file method with the new file path
            result = self.append_to_csv_file(
                file_name=new_file_path,
                dataframe_var=dataframe_var,
                rows=rows,
                encoding=encoding
            )
            
            return result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Error appending to daily accumulation file: {str(e)}"
            }
