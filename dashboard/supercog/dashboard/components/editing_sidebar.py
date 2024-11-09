"""The App editor page."""
import reflex as rx
from typing import List, Tuple

from supercog.shared.utils import load_file_content
from supercog.dashboard.state_models import UITool
from supercog.dashboard.editor_state import EditorState
from supercog.dashboard.components.markdown_modal import markdown_modal
from supercog.dashboard.components.modal import new_folder_modal
from supercog.dashboard.components.tool_link import tool_link
from supercog.dashboard.components.runs_table import runs_table
from supercog.dashboard.components.accordion_item import accordion_item

from supercog.dashboard.components.test_prompt_modal import test_prompt_content

def welcome_message() -> rx.Component:
    return rx.chakra.vstack(
        rx.chakra.text("Welcome message"),
        rx.chakra.text_area(
            value=EditorState.app.welcome_message, 
            placeholder="Help message for the user",
            on_change=lambda val: EditorState.set_app_value("welcome_message", val),
            font_style="italic"
        ),
        width="100%",
        align_items="flex-start",
        margin_bottom="1rem"
    )

def trigger() -> rx.Component:
    return rx.chakra.vstack(
        rx.chakra.vstack(
            rx.chakra.text("Trigger"),
            rx.chakra.select(
                EditorState.avail_triggers,
                value=EditorState.app.trigger,
                on_change=lambda val: EditorState.set_app_value("trigger", val),
                is_disabled=~EditorState.agent_editable,
            ),
            rx.cond(
                EditorState.app.trigger_prefix == 'Database', 
                rx.chakra.hstack(
                    rx.chakra.text("Watch table"),
                    rx.chakra.input(
                        value=EditorState.app.trigger_arg,
                        on_change=lambda val: EditorState.set_app_value("trigger_arg", val),
                        is_disabled=~EditorState.agent_editable,
                    ),
                    width="100%",
                    align_items="stretch",
                ),
            ),
            rx.cond(
                EditorState.app.trigger_prefix == 'Gmail', 
                rx.chakra.hstack(
                    rx.chakra.text("Filter"),
                    rx.chakra.input(
                        value=EditorState.app.trigger_arg,
                        on_change=lambda val: EditorState.set_app_value("trigger_arg", val),
                        is_disabled=~EditorState.agent_editable,
                    ),
                    width="100%",
                    align_items="stretch",
                ),
            ),
            rx.cond(
                EditorState.app.trigger_prefix == 'Scheduler', 
                rx.chakra.hstack(
                    rx.text("Describe your schedule"),
                    rx.chakra.input(
                        value=EditorState.app.trigger_arg,
                        on_change=lambda val: EditorState.set_app_value("trigger_arg", val),
                        is_disabled=~EditorState.agent_editable,
                    ),
                    width="100%",
                    align_items="stretch",
                ),
            ),
            rx.cond(
                EditorState.app.trigger_prefix == 'Slack', 
                rx.chakra.hstack(
                    rx.chakra.text("Trigger keywords"),
                    rx.chakra.input(
                        value=EditorState.app.trigger_arg,
                        on_change=lambda val: EditorState.set_app_value("trigger_arg", val),
                        is_disabled=~EditorState.agent_editable,
                    ),
                ),
            ),
            rx.cond(
                EditorState.app.trigger_prefix.contains('Amazon S3'), 
                rx.chakra.hstack(
                    rx.chakra.text("S3 Bucket Name / SQS Arn"),
                    rx.chakra.input(
                        value=EditorState.app.trigger_arg,
                        on_change=lambda val: EditorState.set_app_value("trigger_arg", val),
                        is_disabled=~EditorState.agent_editable,
                    ),
                ),
            ),
            rx.cond(
                EditorState.app.trigger_prefix == 'Email', 
                rx.chakra.hstack(
                    rx.chakra.text("Email address"),
                    rx.chakra.input(
                        value=EditorState.app.agent_email,
                        disabled=True,
                    ),
                    rx.chakra.button(
                        rx.icon(tag="circle_help"), 
                        on_click=EditorState.toggle_markdown_modal
                    ),
                ),
            ),
            rx.cond(
                EditorState.app.trigger_prefix == 'Reflection',
                rx.chakra.hstack(
                    rx.chakra.text("Reflection Instructions"),
                    rx.chakra.icon(
                        tag="info_outline",# Use the correct tag for an info icon
                        name="info",       # Assuming 'info' is a valid icon name in your system
                        cursor="pointer",  # Change cursor to indicate it's hoverable
                        color="blue.500",  # Color the icon for visibility
                        size="sm",         # Small icon size
                        tooltip=rx.chakra.tooltip(
                            label="Instruct the system to look back at the execution of the agent and reflect on mistakes made that can be detected in the output. You will want to specify 'Max Tries: n' in your instructions or accept the default of 5. Mistakes may be indicated by errors returned from tool function executions or just output that is significantly different than the expected output. by reflecting. If you have a simpler type of agent that just creates some output, but that output may not match the level of sophistication you desire, it would be better to use the reflection tool with a chat trigger, so you can interject within the reflection process and indicate when the results are satisfactory.",
                       
                        
                            placement="right",     # Tooltip appears to the right of the icon
                            has_arrow=True,        # Optionally display an arrow pointing to the icon
                        ),
                    ),
                    rx.chakra.input(
                         placeholder="<Review the task execution. Identify any errors returned by function calls. Analyze the nature of these errors to understand what went wrong. Use this information to adjust the task instructions. Once adjustments are made, rerun the task to ensure that the previous mistakes are corrected and that the output aligns with expected results.>",
                        value=EditorState.app.trigger_arg,
                        on_change=lambda val: EditorState.set_app_value("trigger_arg", val),
                        height="auto",  # Let height be automatic to accommodate content
                    ),
                    width="100%",
                    align_items="stretch",
                ),
            ),
            align_items="stretch",
            width="100%",
        ),
        width="98%",
        align_items="stretch",
    )

#Here is the Agent Instructions tab
def agent_instructions_tab() -> rx.Component:
    return rx.tabs.content(
        rx.chakra.vstack(
            rx.chakra.text_area(
                value=EditorState.app.system_prompt,
                on_change=lambda val: EditorState.set_app_value("system_prompt", val),
                width="100%",
                flex="1",
                overflow="auto",
                is_disabled=~EditorState.agent_editable,
            ),
            rx.chakra.accordion(
                tool_block(),
                agent_settings(),
                default_index=[0],
                allow_multiple=True,
                allow_toggle=True,
                width="100%",
            ),
            align_items="start",
            width="100%",
            height="90%", 
            overflow="auto",
        ),
        value="agent_instructions",
        width="100%",
        height="100%",  # This should ensure the content area takes full vertical space
        flex="1",  # Encourage content to expand
        overflow="hidden",
    )

# Below is the User Instructions tab 
def user_instructions_tab() -> rx.Component:
    return rx.tabs.content(
        rx.chakra.box(
            test_prompt_content(EditorState.app),
            align_items="start",
            width="100%",
            height="100%",
            overflow="scroll",
            padding="1rem",
        ),
        value="user_instructions",
        width="100%",
        #height="100%",
        flex="1",
        overflow="hidden",
    )

# Below is the history block of the  Memory and Learning tab
def run_history_block() -> rx.Component:
    return rx.chakra.box(
        rx.chakra.vstack(
            runs_table(flex="1", overflow="hidden"),
            align_items="flex-start",  # Ensures children of vstack aligned to the start (left)
            width="100%",              # Ensure the vstack fills the width of its container
            height="100%",             # Ensure vstack takes full height it can within its container
            overflow="auto",
        ),
        align_items="center",  # Centers the header over the box specifically
        width="100%",          # Match the width of the data editor to align them exactly
        padding="0",           # Remove padding around the container box
        flex="1",
        overflow="hidden",
    )


def memory_block(heading: str,
                 memories: List[Tuple[str,bool]],
                 tool_name: str="") -> rx.Component:
    return rx.chakra.accordion(
        accordion_item(
            header=rx.fragment(
                rx.chakra.heading(heading, size="sm"),
                rx.chakra.accordion_icon(),
            ),
            header_kwargs={
                "padding": "0.5rem 0"
            },
            content=rx.fragment(
                rx.chakra.box(
                    rx.foreach(
                        memories,
                        lambda memory, index: memory_box(memory, index, tool_name),
                    ),
                    width="100%",
                ),
                rx.chakra.hstack(
                    rx.chakra.button(
                        "New",
                        on_click=lambda: EditorState.new_memory(tool_name),
                        variant="outline",
                    ),
                    rx.chakra.button(
                        "Save",
                        on_click=EditorState.save_agent,
                        color_scheme="green",
                        margin="1rem",
                        is_disabled=EditorState.agent_memory_has_not_changed
                    ),
                    align_self="end",
                    justify_content="end",
                ),
                width="100%",
            )
        ),
        width="100%",
        allow_toggle=True,
    )


# Below is the Memory block of the  Memory and Learning tab
def memory_box(memory: Tuple[str,bool],
               index: int,
               tool_name: str="") -> rx.Component:
    return rx.chakra.hstack(
        rx.chakra.text_area(
            value=memory[0],
            on_change=lambda val: EditorState.on_change_memory(val, index, tool_name),
            number_of_lines=2, 
            margin_bottom="8px"
        ),
        rx.chakra.tooltip(
            rx.chakra.button(
                rx.icon(tag="trash-2", size=15),
                on_click=lambda: EditorState.delete_memory(index, tool_name),
                size="sm",
                variant="outline",
            ),
            label="Delete Memory"
        ),
    )

def tool_memory_blocks() -> rx.Component:
    return rx.foreach(
        EditorState.real_tools,
        lambda uitool: tool_memory_block(uitool),
        align_items="center",    # Centers the header over the box specifically
        width="100%",            # Match the width of the data editor to align them exactly
        padding="0",             # Remove padding around the container box

    )

def tool_memory_block(uitool: UITool) -> rx.Component:
    return rx.chakra.box(
        memory_block(
            f"{uitool.name} Tool Memory",
            EditorState.agent_memories,
            uitool.name
        ),
        key=uitool.name,        # Add a key to help React efficiently update the UI
        width="100%",           # Ensure each block takes the full width of the container
        padding="2px",          # Optional padding for visual separation
        border="1px solid #ccc" # Optional border for visual clarity
    )

def agent_memory_block() -> rx.Component:
    return memory_block(EditorState.app.name+" Agent Memory", EditorState.agent_memories)
                
def memory_and_learning_tab() -> rx.Component:
    return rx.tabs.content(
        rx.chakra.vstack(
            rx.chakra.box(
                rx.chakra.vstack(
                    agent_memory_block(),
                    #tool_memory_blocks(),
                    run_history_block(),
                    align_items="flex-start",  # Ensures children vstack aligned to start (left)
                    width="100%",              # Ensure vstack fills the width of its container
                    height="100%",             # Ensure vstack takes the full height within its container
                ),
                align_items="center",    # Centers the header over the box specifically
                width="100%",            # Match the width of the data editor to align them exactly
                height="100%",
                padding="0",             # Remove padding around the container box
            ),
            align_items="flex-start", # Ensures children of outer vstack aligned to start (left)
            width="100%",             # Ensure the vstack fills the width of its container
            height="100%",            # Ensure the vstack takes the full height it can within its container
            overflow="auto",
        ),
        value="memory",
        padding="2px",     # Provide padding inside the outer box
        width="100%",      # Ensure the box fills the width of its container
        height="100%",     # Ensure the box takes full vertical space available
        overflow="hidden", # Ensures the outermost container respects boundaries
        flex="1",
    )

def system_prompt() -> rx.Component:
    return rx.chakra.vstack(
        rx.tabs.root(
            rx.tabs.list(
                rx.tabs.trigger("Agent Instructions", value="agent_instructions"),
                rx.tabs.trigger("User Prompts",  value="user_instructions"),
                rx.tabs.trigger("Memory & Learning",  value="memory"),
                margin_bottom="1rem",
                width="100%",
            ),
            agent_instructions_tab(),
            user_instructions_tab(),
            memory_and_learning_tab(),
            
            default_value="agent_instructions",
            
            width=        "100%",
            height=       "100%",
            align_items=  "flex-start",
            #margin=      "1em", # Adds space around the outside of the box
            flex=         "1",   # allows box expand fill. Encourage  tab root to fill its container
            flex_shrink=  "0",   # Prevents the box from shrinking below its minimum content size, 
            display=      "flex",
            flex_direction= "column",
        ),
        width=        "100%",
        align_items=  "stretch",
        flex=         "1",
        overflow=     "hidden",
        #height=      "100%",  # Encourage outermost container to take full vertical space of parent
    )

def open_close_editor_button() -> rx.Component:
    return rx.chakra.tooltip(
        rx.chakra.button(
            rx.cond(
                EditorState.agent_editable,
                rx.icon("panel_left_close", size=20),
                rx.icon("panel_left_open", size=20),
            ),
            on_click=EditorState.toggle_editor_pane,
            padding_inline_start="0.5rem",
            padding_inline_end="0.5rem",
        ),
        label=rx.cond(
            EditorState.agent_editable,
            "Close Editor",
            "Open Editor",
        ),
    )

def agent_settings() -> rx.Component:
    return accordion_item(
        header=rx.fragment(
            rx.chakra.heading("Settings", size="sm"),
            rx.chakra.accordion_icon(),
        ),
        content=rx.chakra.vstack(
            rx.chakra.hstack(
                rx.chakra.vstack(
                    rx.chakra.text("Model", color="#888"),
                    rx.chakra.select(
                        EditorState.avail_models, 
                        value=EditorState.run_model,
                        on_change=lambda val: EditorState.change_model(val)
                    ),
                ),
                rx.chakra.vstack(
                    rx.chakra.text("Temperature"),
                    rx.chakra.input(
                        value=EditorState.app.temperature,
                        on_change=lambda val: EditorState.set_app_value("temperature", val),
                    ),
                ),
                rx.chakra.vstack(
                    rx.chakra.text("Max Exec Time"),
                    rx.chakra.number_input(
                        value=EditorState.app.max_agent_time,
                        on_change=lambda val: EditorState.set_app_value("max_agent_time", val),
                    ),
                ),
                align_items="stretch",
                height="80px",
                overflow="scroll",
            ),
            rx.chakra.hstack(
                rx.chakra.text("Indexes:"),
                rx.chakra.input(
                    value=EditorState.app.index_list,
                    on_change=lambda val: EditorState.set_app_value("index_list", val),
                ),
                width="100%",
            ),
        ),
    )

def tool_row(tool: UITool) -> rx.Component:
    return rx.hstack(
        tool_link(tool, show_delete=False),
        rx.hstack(
            rx.cond(
                tool.credential_id,
                rx.chakra.tooltip(
                    rx.chakra.button(
                        rx.icon(tag="pencil", size=15),
                        on_click=EditorState.prompt_for_edit_connection(tool.credential_id),
                        size="sm",
                        variant="outline",
                    ),
                    label="Edit Tool"
                ),
            ),
            rx.chakra.tooltip(
                rx.chakra.button(
                    rx.icon(tag="trash-2", size=15),
                    on_click=EditorState.force_remove_uitool(tool.tool_id, tool.tool_factory_id, tool.name),
                    size="sm",
                    variant="outline",
                ),
                label="Remove Tool"
            ),
        ),
        
        width="100%",
        align="center",
        justify="between",
    )

def tool_block() -> rx.Component:
    return accordion_item(
        header=rx.fragment(
            rx.chakra.heading("Tools", size="sm"),
            rx.chakra.hstack(
                rx.cond(
                    EditorState.agent_editable,
                    rx.chakra.button(
                        "Add Tool", 
                        on_click=EditorState.toggle_tools_modal.stop_propagation
                    ),
                ),
                rx.chakra.accordion_icon(),
                gap="0.5rem",
            ),
        ),
        header_kwargs={
            "padding": "0 1rem"
        },
        content=rx.chakra.vstack(
            rx.foreach(
                EditorState.app.uitools,
                tool_row
            ),
            align_items="stretch",
            width="100%",
        ),
    )

def editing_sidebar(**kwargs) -> rx.Component:
    return rx.chakra.vstack(
        welcome_message(),
        trigger(),
        system_prompt(),
        rx.chakra.text(EditorState.warn_message, color="red", font_weight="bold"),
        markdown_modal("Email Trigger Help", load_file_content(tag="EMAIL_TRIGGER_HELP")),
        new_folder_modal(),
        width="100%",
        height="100%",
        overflow="hidden",
        **kwargs,
    ),
