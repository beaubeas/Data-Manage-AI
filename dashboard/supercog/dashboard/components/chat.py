from typing import Any

import reflex as rx

from supercog.dashboard import styles
from .json_viewer import jsonviewer
from .xml_viewer  import xml_viewer

from supercog.dashboard.components import loading_icon
from supercog.dashboard.components.spinner import spinner

from supercog.dashboard.editor_state import QA, Answer, EditorState, GENERATION_COMPLETE_MARK
from supercog.dashboard.global_state import GlobalState
from supercog.dashboard.index_state import IndexState


def setup_prompt_history() -> rx.Component:
    return rx.script("try { setupPromptHistoryOnFocus(); } catch {}")

markdown_components = {
    "a": lambda text, **props: rx.link(
        text, **props, is_external=True, underline="always", color_scheme="blue", cursor="pointer"
    ),
    "code": lambda text: rx.code(text),
    "codeblock": lambda text, **props: rx.box(
        rx.code_block(
            text, **props,
        ),
        # rx.button(
        #     rx.icon("clipboard", size=15), 
        #     variant="surface", 
        #     size="1", 
        #     position="absolute",
        #     bottom="20px",
        #     right="15px",
        #     box_shadow="none",
        #     class_name="copy_button",
        # ),
        position="relative",
        class_name="code_block_div",
    ),
}

def tool_call_block(answer: Answer) -> rx.Component:
    return rx.vstack(
        rx.box(
            rx.cond(
                answer.is_script,
                code_block(answer.code),
                param_block(answer.output, answer.param_json),
            ),
            bg="white",
            border_radius="10px",
            box_shadow="md",
            width="100%",
        ),
    )

def code_block(code: str) -> rx.Component:
    return rx.chakra.accordion(
        rx.chakra.accordion_item(
            rx.chakra.accordion_button(
                rx.chakra.text("Script", size="sm"),
                rx.chakra.accordion_icon(),
            ),
            rx.chakra.accordion_panel(
                rx.code_block(code),
            ),
            border_top_width="0px !important",
            border_bottom_width="0px !important",
        ),
        allow_toggle=True,
        width="100%",
    )

def timestamp(ts: str) -> rx.Component:
    return rx.chakra.text(
        f"{ts}s", 
        size="sm", 
        class_name="light-text"
    )

def detail_block(chats, answer: Answer) -> rx.Component:
    return rx.chakra.accordion(
        rx.chakra.accordion_item(
            rx.chakra.accordion_button(
                rx.cond(
                    ~chats.contains(GENERATION_COMPLETE_MARK),
                    spinner(width="20px", margin_right="1rem"),
                ),
                rx.chakra.text("results", size="sm"),
                timestamp(answer.tool_time),
                rx.chakra.accordion_icon(),
                position="relative",
            ),
            rx.chakra.accordion_panel(
                rx.markdown(
                    f"```\n{chats}\n```",
                    width="100%"
                ),
            ),
            border_top_width="0px !important",
            border_bottom_width="0px !important",
        ),
        allow_toggle=True,
        width="100%",
    )

def normal_output_block(answer: Answer) -> rx.Component:
    return rx.fragment(
        rx.cond(
            answer.requested_var_names,
            request_var_names_block(answer.requested_var_names),
        ),
        rx.markdown(
            answer.output,
            component_map=markdown_components,
        ),
        rx.cond(
            answer.elapsed_time != "",
            rx.chakra.text(
                answer.elapsed_time, 
                size="sm", 
                class_name="elapsed-time"
            ),
        ),
    )


def table_block(answer: Answer) -> rx.Component:
    return rx.vstack(
        # Can't forget the prefix.
        rx.markdown( 
            answer.prefix,
            component_map=markdown_components,
        ),
        # and now the table
        rx.chakra.table_container(
            rx.chakra.table(
                headers=answer.headers,
                rows=answer.rows,
                variant="striped",
            ),
        ),
        rx.markdown( 
            answer.postscript,
            component_map=markdown_components,
        ),
    )

def tool_output_with_json_block(answer: Answer) -> rx.Component:
    return rx.chakra.accordion(
        rx.chakra.accordion_item(
            rx.chakra.accordion_button(
                rx.chakra.text("results", size="sm"),
                timestamp(answer.tool_time),
                rx.chakra.accordion_icon(),
                position="relative",
            ),
            rx.chakra.accordion_panel(
                rx.markdown(answer.before_json),
                jsonviewer(data=answer.tool_json),
            ),
            border_top_width="0px !important",
            border_bottom_width="0px !important",
        ),
        allow_toggle=True,
        width="100%",
    )


def json_block(tool_json: Any) -> rx.Component:
    return rx.chakra.accordion(
        rx.chakra.accordion_item(
            rx.chakra.accordion_button(
                rx.chakra.text("results", size="sm"),
                rx.chakra.accordion_icon(),
            ),
            rx.chakra.accordion_panel(
                jsonviewer(data=tool_json),
            ),
            border_top_width="0px !important",
            border_bottom_width="0px !important",
        ),
        allow_toggle=True,
        width="100%",
    )

def param_block(func_call: str, tool_json: Any) -> rx.Component:
    return rx.chakra.accordion(
        rx.chakra.accordion_item(
            rx.chakra.accordion_button(
                rx.chakra.text(func_call, size="sm"),
                rx.chakra.accordion_icon(),
            ),
            rx.chakra.accordion_panel(
                jsonviewer(data=tool_json),
            ),
            border_top_width="0px",
            border_bottom_width="0px",
        ),
        allow_toggle=True,
        width="100%",
    )

def xml_block(tool_xml: Any) -> rx.Component:
    return rx.chakra.accordion(
        rx.chakra.accordion_item(
            rx.chakra.accordion_button(
                rx.chakra.text("results", size="sm"),
                rx.chakra.accordion_icon(),
            ),
            rx.chakra.accordion_panel(
                xml_viewer(xml=tool_xml),
            ),
        ),
        allow_toggle=True,
        width="100%",
    )
def error_block(error_message) -> rx.Component:
    return rx.box(
        rx.box(
            rx.markdown(
                f"```\n{error_message}\n```",
                width="100%",
                component_map=markdown_components,
            ),
            style={
                "white-space": "pre-wrap",
                "max-height": "200px",  # Adjust the max height as needed
                "overflow-y": "auto",
                "padding": "1em",
                "border": "1px solid red",
                "background-color": "#ffe5e5",
                "border-radius": "5px",
                "width": "100%"
            }
        ),
        style={
            "width": "100%",
            "display": "flex",
            "justify-content": "center",
            "align-items": "center"
        }
    )
def audio_block(url, json):
    return rx.vstack(
        #rx.text(f"Debug - URL type: {type(url)}"),
        #rx.text(f"Debug - URL value: {url}"),
        json_block(json),
        rx.html(url),
        spacing="4",
        align_items="center",
    )

def request_var_names_block(var_names: list[str]) -> rx.Component:
    # Render a form requesting the user to provide values for the requested variables
    return rx.chakra.form(
        rx.chakra.heading("Please provide values for these secrets:", size="sm", margin_bottom="1em"),
        rx.foreach(
            var_names,
            lambda var_name:
                rx.chakra.hstack(
                    rx.chakra.text(var_name),
                    rx.chakra.input(
                        name=var_name,
                    ),
                ),
        ),
        rx.chakra.button("Save", type_="submit"),
        on_submit=EditorState.save_env_vars,
        bg="white",
        margin_top="1em",
        padding="1em",
        border_radius="10px",
    )

# Alternative user question block (NOT USED CURRENTLY) Questions from the user get formatted here
def user_markdown_box(qa: QA) -> rx.Component:
    return rx.chakra.box(
        rx.cond(
            qa.question != "",
            rx.markdown(
                qa.question,
                # Here you can still apply styles that were originally used
                # for the text component, such as background or shadow,
                # by utilizing the inline CSS capabilities of Markdown or
                # leveraging global and component-specific styles as needed
                # <sup><a href="#">2</a></sup>.
                class_name="chat_answer_box",
                bg=qa.question_bg,
                #style={
                #    "whiteSpace": "pre-wrap",  # Ensure text wraps
                #    "textAlign": "left",
                #    "wordWrap": "break-word"  # Ensures that long words will wrap and not overflow
                #}
            ),
        ),
        text_align="left",
        margin_top="0.2em",
        margin_bottom="0.2em",
        style={
            "display": "block",
            "overflow": "hidden"  # Optional, can be 'auto' if scrollbars when content overflows
        }
    )

def user_formatted_box(qa: QA)  -> rx.Component:
    return rx.chakra.box(
        rx.cond(
            qa.question != "",
                rx.chakra.text(
                    rx.chakra.avatar(
                        name=qa.user_name,
                        size="xs",
                        background_color="#DDD",
                        margin_right="4px",
                    ),
                    qa.question,
                    #bg=styles.border_color,
                    shadow=styles.shadow_light,
                    **styles.message_style,
                    p=4,
                    bg=qa.question_bg_sc,
                    class_name="sc_chat_question_box",
                    style={
                        "whiteSpace": "pre-wrap",  # Ensure text wraps
                        "textAlign": "left",
                        "wordWrap": "break-word",  # Ensures that long words will wrap and not overflow
                        "left": "10%",
                    }
                ),
        ),
        text_align="left",
        margin_top="0.2em",
        margin_bottom="0.2em",
        style={
            "display": "block",
            "overflow": "hidden"  # Optional, can be 'auto' if scrollbars when content overflows
        }
    )

def message(qa: QA, index: int) -> rx.Component:
    """A single question/answer message. A single user
       question (QA.question) can have a list of answers.
       Each answer can optionally have tool output.
    Args:
        qa: The question/answer pair.
    Returns:
        A component displaying the question/answer pair.
    """

    return rx.chakra.box(
        # First display the question
        user_formatted_box(qa),
        rx.chakra.box(
            # Now go down each answer
            rx.foreach(
                qa.answers,
                lambda answer: rx.chakra.container(
                    rx.chakra.box(
                        # This is the block for LLM output, INCLUDING tool function calls.
                        # Empty answer - turn on spinner until it completes.
                        rx.cond(
                            answer.output == "",
                            spinner(width="20px"),
                            # Non empty check if it's a table
                            rx.cond(
                                answer.table_results,
                                table_block(answer),                    # handle tables
                                # check if it's an errored function call
                                rx.cond(
                                    answer.error_flag,                
                                    error_block(answer.output),         # handle LLM errors
                                    # check if this tool call should be hidden
                                    rx.cond(
                                        answer.hide_function_call,
                                        rx.fragment(),                  # handle hidden functions
                                        rx.cond(
                                            answer.is_tool_call,
                                            tool_call_block(answer),    # handle tool function calls
                                            normal_output_block(answer) # handle normal output
                                        ),
                                    ),
                                ),
                            ),
                        ),
                        # This is the block for tool output
                        rx.cond(
                            answer.tool_output != "",
                            rx.cond(
                                # Error block
                                answer.error_flag,
                                error_block(answer.tool_output),
                                rx.cond(
                                    # Audio block: test this case first because also a json block
                                    answer.audio_results,
                                    audio_block(answer.audio_url, answer.tool_json),
                                    rx.cond(
                                        # JSON block
                                        answer.object_results,
                                        tool_output_with_json_block(answer),
                                        rx.cond(
                                            answer.requested_var_names,
                                            request_var_names_block(answer.requested_var_names),
                                            rx.cond(
                                                # XML block
                                                answer.xml_results,
                                                xml_block(answer.tool_xml),
                                                # ANd finally Tool
                                                detail_block(answer.tool_output, answer),
                                            ),
                                        ),
                                    ),
                                ),
                            ),
                        ),
                        p=2,
                        class_name=f"sc_chat_answer_box {qa.answer_class}",
                    ),
                    rx.html("<div style='clear:both'></div>"),
                    class_name="answer_container",
                    padding_left="0",
                    text_align=answer.alignment,
                    max_width="100%",
                    left="-10%",
                ),
            ),
            text_align="center",
            style={"display": "block"},
        ),
        width="100%",
    )

def chat_messages() -> rx.Component:
    return rx.chakra.vstack(
        rx.chakra.vstack(
            rx.foreach(EditorState.chats, message),
            width="100%",
            align_items="flex-start",  # Align items to the start (left) of the container,
            id="chatwindow",
        ),
        rx.cond(
            ~EditorState.processing & EditorState.chats.length() >= 1,
            reflect_button(),
        ),
        rx.script("try { window.setupChatScrolling(); } catch {}"),
        py="8",
        flex="1",
        padding_x="4",
        align_self="auto",
        overflow="scroll",
        padding_bottom="1em",
        padding_top="0",
        bg="#F8F8F8",
        id="chatoutput",
        width="100%",
        border_radius="0.5em",
        max_height=styles.chat_height,
        align_items="flex-start",  # Ensure the outer stack also aligns items to the start
    )

def usage_label() -> rx.Component:
    return rx.chakra.tooltip(
        rx.chakra.text(
            EditorState.usage_message,
            color="#999",
            font_size="8pt",
            cursor="default",
        ),
        label=EditorState.costs_message,
    )

def reflect_button() -> rx.Component:
    return rx.chakra.button(
        "Reflect",
        background_color="#A5A5A5",
        color="white",
        align_self="flex-end",
        variant="outline",
        on_click=EditorState.reflect_chat,
        _hover={
            "background_color": "#2B6CB0", #"#63B3ED",
            "color": "white",
        },
        size="xs",
        padding_top="2px",
        padding_right="20px",
        padding_bottom="2px",
        padding_left="20px",
    )

def download_button() -> rx.Component:
    return rx.dropdown_menu.root(
        rx.dropdown_menu.trigger(
            rx.chakra.button(rx.icon("download", size=16), variant="outline"),
        ),
        rx.dropdown_menu.content(
            rx.dropdown_menu.item(
                "Download Chat",
                on_click=EditorState.download_chat_transcript,
            ),
            rx.dropdown_menu.item(
                "Download Agent",
                on_click=EditorState.download_agent,
            ),
            variant="soft",
        ),
    )

def upload_button() -> rx.Component:
    return rx.chakra.popover(
        rx.chakra.popover_trigger(
            rx.chakra.button(rx.icon("upload", size=16), variant="outline"),
        ),
        rx.chakra.popover_content(
            rx.upload(
                rx.chakra.button(
                    "Upload File to Chat",
                    size="sm",
                    variant="outline",
                    width="100%",
                ),
                id="upload_chat",
                on_drop=EditorState.handle_chat_upload(rx.upload_files(upload_id="upload_chat")),
            ),
            rx.upload(
                rx.chakra.button(
                    "Upload Agent",
                    size="sm",
                    variant="outline",
                    width="100%",
                ),
                id="upload_agent",
                accept = {
                    "application/yaml": [".yaml"],
                    "application/b64": [".b64"],
                },
                on_drop=IndexState.handle_upload_agent(rx.upload_files(upload_id="upload_agent")),
            ),
            width="130px",
        ),
    )

def command_tooltip() -> rx.Component:
    return rx.cond(
        EditorState.filtered_commands,
        rx.chakra.box(
            rx.foreach(
                EditorState.filtered_commands,
                lambda cmd: rx.chakra.box(
                    rx.chakra.text(cmd),
                    py="2",
                    cursor="pointer",
                    _hover={"bg": styles.accent_color},
                    on_click=lambda: [
                        EditorState.set_test_prompt(cmd + " "),
                        EditorState.set_filtered_commands([]),
                        rx.set_focus("question")
                    ],
                ),
            ),
            position="absolute",
            bottom="80px",
            left="0",
            width="100%",
            bg="white",
            border="1px solid #DDD",
            border_radius="5px",
            padding="2",
            z_index="10",
        ),
    )

def action_bar() -> rx.Component:
    """The action bar to send a new message."""
    return rx.chakra.hstack(
            rx.vstack(
                rx.chakra.text(
                    EditorState.temp_upload_file,
                    overflow="hidden",
                    white_space="nowrap",
                    text_overflow="ellipsis",
                    max_width="150px",
                ),
                #upload_button(),
                rx.cond(
                    EditorState.temp_upload_file,
                    rx.icon(tag="x", size=12, margin_top="-10px", on_click=EditorState.clear_upload_file),
                ),
                rx.upload(
                    rx.chakra.button(rx.icon("upload", size=15), variant="outline"),
                    id="upload_chat",
                    padding="10",
                    on_drop=EditorState.handle_chat_upload(rx.upload_files(upload_id="upload_chat")),
                ),
                height="100%",
                justify="end",
                align="center",
            ),
            rx.chakra.form(
                rx.chakra.form_control(
                    rx.chakra.hstack(
                        command_tooltip(),
                        rx.chakra.text_area(
                            #on_change=lambda text: [EditorState.filter_metacommands_tooltip(text)],
                            placeholder="Make a request to the agent...",
                            id="question",
                            _placeholder={"color": "#fffa"},
                            is_read_only=False,
                            height="3em",
                            style=styles.input_style,
                        ),
                        setup_prompt_history(),
                        rx.chakra.vstack(
                            rx.chakra.button(
                                rx.cond(
                                    EditorState.processing,
                                    rx.box(
                                        loading_icon(height="24px"),
                                    ),
                                    rx.chakra.text("Send"),
                                ),
                                type_="submit",
                                id="submit_button",
                                border_top_right_radius="10px",
                                _hover={"bg": styles.accent_color},
                                is_loading=EditorState.processing,
                                width="58px",
                            ),
                            rx.cond(
                                EditorState.processing,
                                rx.chakra.tooltip(
                                    rx.chakra.button(
                                        rx.icon(tag="ban", size=16),
                                        border_bottom_right_radius="10px",
                                        _hover={"bg": styles.accent_color},
                                        on_click=EditorState.cancel_agent_run,
                                    ),
                                    label="Cancel",
                                ),
                                rx.chakra.tooltip(
                                    rx.chakra.button(
                                        rx.icon("message-square-plus"),
                                        border_bottom_right_radius="10px",
                                        _hover={"bg": styles.accent_color},
                                        on_click=lambda: EditorState.reset_chat() #type:ignore
                                    ),
                                    label="New Chat",
                                ),
                            ),
                            align_items="stretch"
                        ),
                    ),
                    is_disabled=EditorState.processing,
                ),
                rx.chakra.input(
                    id="timezone",
                    type_="hidden",
                    name="timezone"
                ),
                rx.script(
                    """
                    document.getElementById('agent_request_form').addEventListener('submit', function(e) {
                        var timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
                        var offsetInMinutes = new Date().getTimezoneOffset();
                        var offsetInHours = -offsetInMinutes / 60;
                        var offsetSign = offsetInHours >= 0 ? '+' : '-';
                        var formattedOffset = 'UTC' + offsetSign + Math.abs(offsetInHours);
                        document.getElementById('timezone').value = formattedOffset;
                    });
                    """
                ),
                id="agent_request_form",
                on_submit=EditorState.call_engine_service, #scottp- I moved the upload clearing to call_engine_service
                reset_on_submit=True,
                width="70%",
                border="1px solid #DDD",
                border_radius="10px",
            ),
            rx.vstack(
                usage_label(),
                download_button(),
                height="100%",
                justify="end",
                align="center",
            ),
            width="100%",
            justify_content="center",
            id="action_bar",
            margin_bottom="2rem",
        )

def chat(**kwargs) -> rx.Component:
    return rx.vstack(
        chat_messages(),
        action_bar(),
        on_unmount=EditorState.unmount_chat,
        align_items="stretch",
        gap="1rem",
        overflow_x="auto",
        **kwargs,
    )
