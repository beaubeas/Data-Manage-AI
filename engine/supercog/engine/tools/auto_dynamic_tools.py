from typing import Callable, Any
import re
from collections import namedtuple
import mimetypes

from sqlmodel  import Session, select, or_
from openai import OpenAI
import html2text
import pytextract
from PyPDF2 import PdfReader

from supercog.shared.services import config, db_connect
from supercog.shared.apubsub import EnableToolEvent
from supercog.engine.tool_factory import ToolFactory, ToolCategory, LangChainCallback, LLMFullResult

from supercog.engine.db import Credential
from .ragie_tool import RagieTool
from .csv_tool import CSVTool
from .pdf_tool import PDFTool
from .excel_tool import ExcelTool

ToolChoiceResult = namedtuple("ToolChoiceResult", ["name", "tool_factory_id", "credential_id", "help"])

class AutoDynamicTools(RagieTool):
    def __init__(self):
        super().__init__(
            id = config.DYNAMIC_TOOLS_AGENT_TOOL_ID,
            system_name = "Auto Dynamic Tools",
            logo_url = "/bolt-icon.png",
            auth_config = { },
            category = ToolCategory.CATEGORY_BUILTINS,
            help = """ Functions for enabling tools autonomously. """
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.get_tools_and_connections,
            self.search_knowledge_index,
            self.search_for_tool,
            self.enable_agent_tool,
            self.universal_read_file,
        ])

    async def get_knowledge_indices(self) -> list[str]:
        """ Returns the list of named knowledge indices that you can access to retrieve knowledge. 
            Use 'retrieve_knowledge' to access a given index. """
        return self.run_context.get_user_rag_indices()

    async def get_tools_and_connections(self) -> str:
        """" Returns the list of tools and system connections that can be enabled for the agent. """

        all_tools = await self.get_tools_list()
        res = "Simple tools: " + ", ".join([f"{t.name} - {t.help}" for t in all_tools if t.credential_id is None])
        res += "\nSystem connection tools: " + ", ".join([f"{t.name} - {t.help}" for t in all_tools if t.credential_id is not None])
        return LLMFullResult(res)

    async def get_tools_list(self) -> list[ToolChoiceResult]:
        from supercog.engine.all_tools import SLACK_TOOL_FACTORIES, FACTORY_MAP

        tools = [
            ToolChoiceResult(
                name=candidate.system_name, 
                tool_factory_id=candidate.id, 
                credential_id=None, 
                help=(candidate.help or "").replace("\n", " " )
            )
            for candidate in SLACK_TOOL_FACTORIES if candidate.auth_config == {}
        ]

        engine = db_connect("engine")
        with Session(engine) as session:
            query = select(Credential).where(Credential.tenant_id == self.run_context.tenant_id)
            if self.run_context.run_scope == "private":
                query = query.where(or_(
                        Credential.user_id == self.run_context.user_id, 
                        Credential.scope == 'shared'
                    )
                )
            else:
                query = query.where(Credential.scope == 'shared')
            candidates = [candidate for candidate in session.exec(query).all()]
            
            for candidate in candidates:
                if candidate.tool_factory_id == 'slack_connector':
                    continue
                tool_name = candidate.name
                factory = FACTORY_MAP.get(candidate.tool_factory_id)
                if factory:
                    help = factory.help or ""
                    if factory.system_name.split()[0].lower() not in tool_name.lower():
                        # User has omitted factory name in the Credential name, so add it
                        # back so the "type" of Connection is known
                        tool_name = f"{tool_name} ({factory.system_name})"
                else:
                    help = ""
                tools.append(
                    ToolChoiceResult(
                        name=tool_name, 
                        tool_factory_id=candidate.tool_factory_id, 
                        credential_id=candidate.id,
                        help=help.replace("\n", " " ),
                    )
                )

        engine.dispose()
        return tools

    async def search_for_tool(self, purpose: str) -> list[str]:
        """ Searches for one or more tools related to the indicated purpose. """
        client = OpenAI(api_key=config.get_global("OPENAI_API_KEY"))

        SEARCH_PROMPT = (
            f"Given the list of tools below, return one or two suggestions for the tool that best fits: {purpose}.\n" +
            "Only return the exact names of the tool, comma separated, or NONE if no tool fits the purpose.\n" +
            "----------" +
            await self.get_tools_and_connections()
        )
        messages = [
            {"role": "system", "content": ""},
            {"role": "user", "content": SEARCH_PROMPT}
        ]

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={ "type": "text" },
        )
        result = response.choices[0].message.content
        print("Tool search result choices: ", result)
        if result is None or "NONE" in result:
            # simple keyword search
            purpose2 = purpose.replace("tool", "").lower().strip()
            candidates = [t.name for t in await self.get_tools_list() if (
                purpose in t.name.lower() or purpose2 in t.name.lower()
            )]
            if len(candidates) > 0:
                # sort candidates by longest name first
                candidates.sort(key=lambda x: len(x), reverse=True)
                result = ", ".join(candidates[:2])

        return (result or "NONE").split(",")

    async def enable_agent_tool(self, tool_name: str, callbacks: LangChainCallback) -> str:
        """ Enables the AI agent to use the tool with the indicated name. """

        # Remove use of 'tool' word in the tool name. Use regexp
        # to match. And lowercase.
        tool_name1 = tool_name.lower()
        tool_name2 = re.sub(r"\s+tool\s*", "", tool_name.lower())

        for tool_choice in await self.get_tools_list():
            if tool_choice.name.lower() in [tool_name1, tool_name2]:
                if self.run_context.tool_is_enabled(tool_choice.tool_factory_id):
                    return f"Note: The tool {tool_choice.name} is already enabled"
                
                await self.run_context.publish(
                    self.run_context.create_event(
                        EnableToolEvent, 
                        callbacks, 
                        tool_factory_id=tool_choice.tool_factory_id, 
                        credential_id=tool_choice.credential_id or "",
                        name=tool_choice.name
                    )
                )
                return f"The tool {tool_choice.name} has been enabled."
        else:
            # In case the agent requested a tool that doesn't exist, see if we can suggest one
            suggestions = await self.search_for_tool(tool_name)            
            return f"Error: Tool not found: {tool_name}. Perhaps you want one of: {', '.join(suggestions)}"

    async def universal_read_file(self, file_name: str) -> Any:
        """ Reads the contents for any file type. """

        mime_type, _ = mimetypes.guess_type(file_name, False)
        if mime_type is None:
            return "Error - unable to determine the file type"
        elif mime_type.startswith("image/"):
            return "Enable the Image Analysis & Recognition tool to read image files."
        
        try:
            if mime_type == "text/csv":
                csvtool = CSVTool()
                csvtool.run_context = self.run_context

                return csvtool.read_csv_file(file_name)
            
            elif mime_type in ["text/plain", "application/json", "application/xml"] or mime_type.startswith("text/"):
                return open(file_name, 'r').read()
        
            elif 'html' in mime_type:
                # Use beautifulsoup to extract text
                return html2text.html2text(open(file_name).read())
            
            elif mime_type == "application/pdf":
                pdf_reader = PdfReader(open(file_name, "rb"))
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                
                return LLMFullResult(text)

            elif mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                tool = ExcelTool()
                tool.run_context = self.run_context

                return tool.read_excel_file(file_name)
            else:
                return pytextract.process(file_name)

        except Exception as e:

            print(f"Error reading file {file_name}: {e}. Fall back to pytextract.")
            return pytextract.process(file_name)
        

