from playwright.sync_api import sync_playwright
from supercog.engine.tool_factory import ToolFactory, ToolCategory
from contextlib import contextmanager

import json
import requests
import datetime
import os

from dateutil.relativedelta import relativedelta
from typing import Any, Callable, Optional
import time
from fastapi import FastAPI
from supercog.shared.services import get_service_host

from playwright.async_api import async_playwright
import asyncio
import subprocess

#os.environ['DEBUG'] = 'pw:api'  # Enables debug logging for all Playwright API calls

class PlaywrightTool(ToolFactory):
    credentials: dict = {}
    def __init__(self):
        
        super().__init__(
            id="playwright_connector",
            system_name="Playwright",
            logo_url="https://upload.wikimedia.org/wikipedia/commons/5/52/Collaborative_Robot_Cobot.png",
            auth_config={
            },
            category=ToolCategory.CATEGORY_DEVTOOLS,
            help="""
Use this tool to manipulate and test websites.
"""
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.run_script,
            self.write_script,
            self.read_script,
        ])

    def read_script(self, file_name: str = "") -> str:
        """
        Reads the content of a script file from the playwright directory.
        
        Args:
            file_name (str): The name of the file to read the script from.
        
        Returns:
            str: The content of the script file.
        """
        if not file_name:
            raise ValueError("File name is not provided.")
        
        # Create the full path for the script file
        script_path = os.path.join(os.getcwd(), 'playwright', file_name)
        
        # Read the script from the file
        try:
            with open(script_path, 'r') as f:
                script_content = f.read()
            print(f"Script read from {script_path}")
            return script_content
        except IOError as e:
            print(f"Error reading script from file: {e}")
            return ""

    async def run_script(self, script_text: str = "", file_name: str = "") -> str:
        """
        Performs automation on websites using async python scripting.
        Args:
            script_text (str): The actual text of the script to be run.
            file_name (optional) (str): a script file to be run
        :return: Captured stdout and stderr output
        """
        is_temp_file: bool = False
        playwright_dir = os.path.join(os.getcwd(), 'playwright')
        
        if file_name:
            print(f"Setting script file to {file_name}")
            script_file = os.path.join(playwright_dir, file_name)
        else:
            # Create a temporary file to save the script
            script_file = os.path.join(playwright_dir, 'temp_script.py')
            is_temp_file = True
            with open(script_file, 'w') as f:
                f.write(script_text)
        
        # Function to run the script asynchronously and capture stdout and stderr
        async def run_subprocess():
            process = await asyncio.create_subprocess_exec(
                'python', script_file,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            return stdout.decode(), stderr.decode()
        
        # Run the subprocess and capture the output
        stdout, stderr = await run_subprocess()
        
        # Clean up the temporary script file
        if is_temp_file:
            os.remove(script_file) 
        
        return f"STDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"

    def write_script(self,
                     script_text:    str = "",
                     file_name:      str = "") -> str:
        """
        Writes the script text to a file in the playwright directory.
        
        Args:
            script_text (str):    The actual text of the script to be written.
            file_name (str):      The name of the file to write the script to.
        
        Returns:
            str: The full path of the written script file.
        """
        if not script_text:
            raise ValueError("Script content is empty.")
        
        if not file_name:
            raise ValueError("File name is not provided.")
        
        # Ensure the playwright directory exists
        playwright_dir = os.path.join(os.getcwd(), 'playwright')
        os.makedirs(playwright_dir, exist_ok=True)
        
        # Create the full path for the script file
        script_path = os.path.join(playwright_dir, file_name)
        
        # Write the script to the file
        try:
            with open(script_path, 'w') as f:
                f.write(script_text)
            print(f"Script written to {script_path}")
            return script_path
        except IOError as e:
            print(f"Error writing script to file: {e}")
            return ""
        
    '''
    async def run_script(self, script: str) -> str:
        """
        Performs automation on websites  using async python scripting.
        :param script: The script to run which would have been designed by the user and the llm
        :return: 
        """
        # Enable verbose logging for Playwright
        os.environ['DEBUG'] = 'pw:api,pw:browser*'
        async with async_playwright() as p:
            exec(script)
        return "Successfully ran script"
    '''
