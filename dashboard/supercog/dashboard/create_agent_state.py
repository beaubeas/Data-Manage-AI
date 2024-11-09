from typing import Any
import reflex as rx
import yaml
from pathlib import Path
from .costs import calc_tokens_cents

from .agents_common_state import AgentsCommonState

class CreateAgentState(AgentsCommonState):
    examples: list[dict] = yaml.safe_load(open(Path(__file__).parent / "examples.yaml"))

    def create_page_load(self):
        pass

