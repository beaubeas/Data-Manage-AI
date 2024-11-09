import code
import os
import sys
from io import StringIO
from typing import Callable, List
import subprocess
from contextlib import asynccontextmanager


from supercog.engine.tool_factory import ToolFactory, ToolCategory, LangChainCallback
from supercog.engine.run_context import RunContext

import code
import textwrap

class InteractiveInterpreter(code.InteractiveInterpreter):
    def __init__(self,  locals=None):
        super().__init__(locals)
        self.last_value = None
        self.stdout = StringIO()

    def runcode(self, code):
        # Redirect stdout to the StringIO buffer
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = self.stdout
        sys.stderr = self.stdout
        
        # Run the code
        super().runcode(code)
        
        # Restore stdout
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        
        # Get the output as a string and clear the buffer
        output = self.stdout.getvalue()
        self.stdout.truncate(0)
        self.stdout.seek(0)
        
        return output

class NativeInterpreterTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id="native_interpreter_tool",
            system_name="Native Interpreter",
            logo_url="https://avatars.githubusercontent.com/u/129434473?s=200&v=4",
            auth_config={
            },
            category=ToolCategory.CATEGORY_DEVTOOLS,
            help="""
Use this tool to allow the agent to execute sandboxed code
"""
        )
        self._interp: InteractiveInterpreter = None

    def get_tools(self) -> List[Callable]:
        return self.wrap_tool_functions([
            self.execute_python_code,
            self.execute_system_commands,
            self.set_env_var,
        ])

    @asynccontextmanager
    async def get_interp(self):
        if self._interp is None:
            self._interp = InteractiveInterpreter()
        yield self._interp

    def catch_code(self, code_to_run, single: bool = False) -> str:
        if code_to_run.strip() == "":
            return ""
        try:
            compiled_code = compile(code_to_run, "<string>", "single" if single else "exec")
            return self._interp.runcode(compiled_code)
        except Exception as e:
            return f"Error running code: {e}"


    async def execute_python_code(self, code: str, callbacks: LangChainCallback=None) -> str:
        """
        Execute the given code in a sandboxed interpreter.
        :param code: str
            The code to execute
        :return: str
            The resulting stdout of the code execution
        """
        async with self.get_interp() as interp:
            try:
                code_to_run = textwrap.dedent(code)
                await self.log(code_to_run, callbacks)
                result = self.catch_code(code_to_run)
                print("-----------------")
                print(result)
                return result
            except Exception as e:
                return f"Error running code: " + str(e)

    async def execute_system_commands(self, commands: str, callbacks: LangChainCallback=None) -> str:
        """Executes commands on the underlying linux system inside the container."""
        result = ""
        for cmd in commands.split("\n"):
            if cmd.strip():  # Ensure we don't process empty lines
                try:
                    await self.log(cmd + "\n", callbacks)

                    process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    stdout, stderr = process.communicate()

                    # Log and accumulate stdout
                    if stdout:
                        await self.log(stdout + "\n", callbacks)
                        result += stdout

                    # Log and accumulate stderr
                    if stderr:
                        await self.log(stderr + "\n", callbacks)
                        result += stderr

                    # Check for command failure
                    if process.returncode != 0:
                        result += f"Command failed with return code {process.returncode}\n"

                except Exception as e:
                    result += f"Exception occurred: {str(e)}\n"
                    await self.log(f"Exception: {str(e)}\n", callbacks)
        return result
    
    async def _execute_line(self, code: str) -> str:
        async with self.get_interp() as interp:
            try:
                code_to_run = textwrap.dedent(code)
                print(code_to_run)
                result = self.catch_code(code_to_run, single=True)
                print("-----------------")
                print(result)
                return result
            except Exception as e:
                return f"Error running code: " + str(e)

    async def set_env_var(self, var_name: str, var_value: str) -> str:
            """ Sets the indicated environment variable in the sandbox. """
            os.environ[var_name] = var_value
            return "ok"

    def test_credential(self, cred, secrets: dict) -> str:
        """ Test that the given credential secrets are valid. Return None if OK, otherwise
            return an error message.
        """
        return "OK"
    


async def interploop():
    tool = NativeInterpreterTool()
    tool.run_context = RunContext._get_test_context()
    buffer = []
    while True:
        try:
            if not buffer:
                line = input(">>> ")
            else:
                line = input("... ")
            
            if line.strip() == "" and buffer:
                # Empty line, execute the buffered code
                print(await tool.execute_python_code("\n".join(buffer)))
                buffer = []
                sys.stdout.flush()
            elif line.rstrip().endswith(":"):
                # Start of a new block, add to buffer
                buffer.append(line)
            elif buffer:
                # Continuation of a block, add to buffer
                buffer.append(line)
            else:
                # Single line of code, execute immediately
                if line.startswith("/"):
                    # Special command, execute it
                    print(await tool.execute_system_commands(line[1:]))
                else:
                    print(await tool._execute_line(line))
                buffer = []
                print(">>> ", end="")
                sys.stdout.flush()
        except EOFError:
            break

if __name__ == "__main__":
    # Run the async interpreter loop
    import asyncio
    asyncio.run(interploop())

