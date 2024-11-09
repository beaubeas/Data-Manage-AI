from sqlmodel import select
from supercog.engine.db import *
from supercog.shared.services import _get_session
from supercog.engine.tool_factory import ToolFactory

session = _get_session()
print("session var and 'select' available, and all Engine models. Also 'load_agent' function.")


