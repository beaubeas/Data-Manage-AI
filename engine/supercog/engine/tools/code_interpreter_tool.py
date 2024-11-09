import asyncio
from typing import Callable, List
from contextlib import contextmanager
from contextlib import asynccontextmanager


from supercog.engine.tool_factory import ToolFactory, ToolCategory

import requests
from e2b_code_interpreter import CodeInterpreter
from e2b import Sandbox

from e2b.api.v2.client.exceptions import UnauthorizedException


class CodeInterpreterTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id="code_interpreter_tool",
            system_name="Code Interpreter",
            logo_url="https://avatars.githubusercontent.com/u/129434473?s=200&v=4",
            auth_config={
                "strategy_token": {
                    "code_interpreter_api_key": "API KEY - find this at https://e2b.dev/docs/getting-started/api-key"
                }
            },
            category=ToolCategory.CATEGORY_DEVTOOLS,
            help="""
Code sandbox to let your agent execute code dynamically
"""
        )
        self._interp: CodeInterpreter = None
        self._env_vars = {}
        self._vars_changed = False

    def get_tools(self) -> List[Callable]:
        return self.wrap_tool_functions([
            self.execute_code,
            self.set_env_var,
        ])

    @asynccontextmanager
    async def get_interp(self):
        if self._interp and not self._vars_changed:
            yield self._interp
        try:
            if self._interp:
                self._interp.close()
            api_key = self.credentials['code_interpreter_api_key']
            self._interp = CodeInterpreter(api_key=api_key, env_vars=self._env_vars).create(api_key=api_key)
            yield self._interp
        except Exception as e:
            raise RuntimeError(f"Error creating sandbox: {e}")

    async def close_sandbox_after_wait(self):
        # Don't know if this is supported for Code Interpreter
        await asyncio.sleep(60*2) # let sandbox live for 2 mins before closing it
        if self._interp is not None:
            self._interp.close()
            self._sandboxID = self._interp.id
            self._interp = None

    async def execute_code(self, code: str) -> dict:
        """
        Execute the given code in a sandboxed interpreter.
        :param code: str
            The code to execute
        :return: str
            The resulting stdout of the code execution
        """
        async with self.get_interp() as interp:
            try:
                print("Running code in eb2 interpreter: ", code)
                execution = interp.notebook.exec_cell(code)
                print("Done: ", execution.to_json())
                return {"status": "success", "message": execution.to_json()}
            except Exception as e:
                return {"status":"error", "message": f"Error running code: {str(e)}"}

    async def set_env_var(self, var_name: str, var_value: str) -> str:
            """ Sets the indicated environment variable in the sandbox. """
            self._env_vars[var_name] = var_value
            self._vars_changed = True
            return "ok"

    def test_credential(self, cred, secrets: dict) -> str:
        """ Test that the given credential secrets are valid. Return None if OK, otherwise
            return an error message.
        """

        try:
            # Get the API key from the secrets
            api_key = secrets.get("code_interpreter_api_key")

            try:
                CodeInterpreter(api_key=api_key)
                return None
            except UnauthorizedException:
                return "Invalid e2b api key"

        except requests.RequestException as e:
            return f"Error testing e2b code interpreter credentials: {str(e)}"

        except Exception as e:
            return str(e)
