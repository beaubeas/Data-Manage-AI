import pytest
import os
from supercog.engine.tools.read_file import ReadFileTool

from .test_helpers import run_context
import markdown2

@pytest.fixture
def tool(run_context):
    tool = ReadFileTool()
    tool.run_context=run_context
    yield tool

@pytest.mark.asyncio
async def test_writing_pdf(tool):
    content = open("../docs/USE_CASES.md").read()
    res = tool.save_pdf_file("test.pdf", content)
    print(res)


