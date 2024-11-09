om playwright.sync_api import sync_playwright
from supercog.engine.tool_factory import ToolFactory, ToolCategory
from contextlib import contextmanager
import json
import requests
import datetime
from dateutil.relativedelta import relativedelta
from typing import Any, Callable, Optional
import time
from fastapi import FastAPI
from supercog.shared.services import get_service_host

class CodeIntrospectionTool(ToolFactory):
    def __init__(self):
        
        super().__init__(
            id="code_introspection_connector",
            system_name="CodeIntrospection",
            logo_url="https://upload.wikimedia.org/wikipedia/commons/9/9e/Ink_and_Marker_Robot_Illustration_29.jpg",
            auth_config={
            },
            category=ToolCategory.CATEGORY_BUILTIN,
            help="""
Use this tool to access suoercode internal code
"""
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.read_source_directory,
            self.write_source_file,
        ])

    def read_source_directory(self) -> dict:
        """
        Returns a source directory in supercog in a way that it can be consumed best by the LLM
        :param creds_pk:  A dictionary containing credentials.
        :param script:    The script to run which would have been designed by the user and the llm
        :return:         
        """
