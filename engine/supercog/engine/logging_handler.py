from uuid import UUID
import traceback
from typing import Any, Dict, List, Optional
from langchain.callbacks import FileCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs.generation import Generation


class FileLogHandler(FileCallbackHandler):
    GREEN = "\033[92m"
    END_COLOR = "\033[0m"

    def __init__(self, filename):
        super().__init__(filename, mode="w")
        self.filename = filename
        self.call_count = 0
        self.sub = 0

    def __getstate__(self):
        # Copy the object's state from self.__dict__ which contains
        # all our instance attributes. Always use the dict.copy()
        # method to avoid modifying the original state.
        state = self.__dict__.copy()
        # Remove the unpicklable entries.
        del state['file']
        return state

    def __setstate__(self, state):
        # Restore instance attributes (i.e., filename and lineno).
        self.__dict__.update(state)

        # # Restore the previously opened file's state. To do so, we need to
        # # reopen it and read from it until the line count is restored.
        try:
            self.file = open(self.filename)
        except:
            traceback.print_exc()
            pass
        # for _ in range(self.lineno):
        #     file.readline()
        # # Finally, save the file.
        # self.file = file

    def on_llm_start(
            self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any
        ) -> Any:
            """Run when LLM starts running."""
            self.printcount("**** LLM START: ", prompts)

    def on_llm_new_token(
        self,
        token: str,
        *,
        chunk: Generation = None,
        run_id,
        parent_run_id = None,
        **kwargs: Any,
    ) -> Any:
        """Run on new LLM token. Only available when streaming is enabled.

        Args:
            token (str): The new token.
            chunk (GenerationChunk | ChatGenerationChunk): The new generated chunk,
            containing content and other information.
        """
        self.printnnl("\033[92m")
        self.printnnl(token)
        if isinstance(chunk.generation_info, dict):
            if 'finish_reason' in chunk.generation_info:
                  self.printnnl("\n")
        self.printnnl("\033[0m")


    def on_llm_end(self, response, **kwargs: Any) -> Any:
        """Run when LLM ends running."""
        self.printcount("============= LLM RESPONSE ===========")
        for gen in response.generations:
            if isinstance(gen, list):
                for g in gen:
                    self.printcount(getattr(g, 'text', '<no text attr>'))
        self.__finish()

    def printcount(self, *args):
        lines = "".join(str(a) for a in args).split("\n")
        for line in lines:
            print(f"{self.call_count+1}.{self.sub+1} ", line, file=self.file)
            self.sub += 1

    def _print_msg(self, message):
        if hasattr(message, '__class__'):
            self.printcount(f"[{message.__class__.__name__}] {message.content}")

    def on_chat_model_start(
        self,
        serialized: Dict[str, Any],
        messages: List[List[BaseMessage]],
        **kwargs: Any,
    ) -> None:
        """Run when LLM starts running."""
        self.sub = 0
        self.printcount("----------- LLM START -----------")
        for msg in messages:
            if isinstance(msg, list):
                for m in msg:
                    self._print_msg(m)
            else:
                self._print_msg(msg)

    def on_chain_start(
        self, serialized: Dict[str, Any], inputs: Dict[str, Any], **kwargs: Any
    ) -> Any:
        """Run when LLM starts running."""
        if hasattr(inputs, 'get') and inputs.get('input') != '':
            self.printcount(">> ", inputs['input'])
        else:
            self.printcount(">>")

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> None:
        self.printcount("<<")

    def on_tool_start(
        self, serialized: Dict[str, Any], input_str: str, **kwargs: Any
    ) -> Any:
        """Run when tool starts running."""
        #self.printcount("******** Logger tool started: ", serialized, " : ", input_str, " : ", kwargs)
        pass

    def on_tool_end(
        self,
        output: Any,
        *,
        run_id: UUID = None,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> Any:
        """Run when tool ends running."""
        self.printcount(self.GREEN, output, self.END_COLOR)

    def __finish(self):
        print("\n", file=self.file)
        self.file.flush()
        self.call_count += 1

    def print(self, *args):
        print(*args, file=self.file)
        self.file.flush()
        
    def printnnl(self, *args):
        print(*args, file=self.file, end="")
        self.file.flush()
