import pytest

from supercog.engine.all_tools import NativeInterpreterTool
from supercog.engine.run_context import RunContext

from .test_helpers import run_context

   
@pytest.mark.asyncio    
async def test_basic_tool_factory(run_context: RunContext):
    interp = NativeInterpreterTool()
    interp.run_context = run_context

    print(await interp.execute_python_code("print('Hello, world!')"))

    await interp.execute_python_code("x = 5")

    await interp.execute_python_code("""
print("This is x: ", x)
""")
    #assert await interp.execute_python_code("x") == "5"

