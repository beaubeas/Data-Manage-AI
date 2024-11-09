import reflex as rx
import json

from supercog.dashboard.state_models import AgentState
from supercog.dashboard.editor_state import EditorState

def test_prompt_content(agent: AgentState) -> rx.Component:
    # Buttons HStack: Arranging new and save buttons with spacing and alignment
    buttons = rx.chakra.hstack(
        rx.chakra.button("New", on_click=EditorState.add_user_instruction),
        rx.chakra.spacer(),  # This will push the buttons to the right
        #rx.chakra.button("Save", on_click=lambda: State.save_agent),
        align_items="center",  # Align items vertically in the center
        justify_content="flex-end",  # Align horizontally to the end (right)
        width="100%"
    )
    
    # VStack: Contains top row of buttons and below it, dynamically generated instruction boxes
    return rx.chakra.vstack(
        buttons,
        rx.foreach(agent.prompts, lambda item, idx: render_user_instruction_box(item, idx)),
        align_items="stretch",  # Stretch children to match the width of the container
        width="100%",
    )
def test_prompt_modal(agent: AgentState) -> rx.Component:
    return rx.chakra.modal(
        rx.chakra.modal_overlay(
            rx.chakra.modal_content(
                rx.chakra.modal_header("List of User Instructions"),
                rx.chakra.modal_body(
                    rx.chakra.button("New", on_click=EditorState.add_user_instruction),
                    rx.chakra.vstack(
                        rx.foreach(agent.prompts,render_user_instruction_box),
                        width="600px",
                    ),
                ),
                rx.chakra.modal_footer(
                    rx.chakra.button("Save", on_click=EditorState.save_test_prompt),
                    rx.chakra.button("Cancel", on_click=EditorState.cancel_test_prompt),
                ),
                min_width="630px",
            ),
        ),
        is_open=EditorState.test_prompt_modal_open,
        size="xl",
    )

def render_user_instruction_box(user_instruction, index: int) -> rx.Component:
    # First horizontal stack: Contains the input and prompt engineering components
    hstack1 = rx.chakra.hstack(
        prompt_engineering(index, user_instruction),
        align_items="center",             # Align items vertically in the center
        justify_content="space-between",  # Spread children across the full width
        width="100%"
    )

    # Second horizontal stack: Contains the user instructions and a button to copy to chat
    hstack2 = rx.chakra.hstack(
        rx.chakra.text_area(
            value=user_instruction["value"],
            placeholder="Agent Instructions",
            on_change=lambda val: EditorState.set_user_instruction_value(val, index),
            num_of_lines=5,
            height="auto",              # Let height be automatic to accommodate content
            background="white",         # Set background color of input to white
        ),
        align_items="stretch",         # Stretch button height to match textarea
        justify_content="flex-start",  # Align items to the start
    )

    # Wrap both stacks in a vertical stack for clean organization
    return rx.chakra.vstack(
        hstack1, #butt
        hstack2,
        align_items="stretch",       # Ensure alignment stretches to fit the container width
        width="100%",                # Use the full width available
        border="1px solid #E2E8F0",  # Adding a border, choose color and width as per your design
        padding="8px",               # Optional: add padding inside the box around content
        margin_bottom="10px !important", # Optional: add margin around the box to separate it from other page elements
        class_name="user-instruction-box", 
        #box_shadow="0 4px 6px rgba(0, 0, 0, 0.1)"  # Optional: adding shadow for depth
    )

def prompt_engineering(index: int, user_instruction) -> rx.Component:
    current_choice = user_instruction["engineering"]
    instruction    = user_instruction["value"]
    name           = user_instruction["name"]
    
    instruction_name_input = rx.chakra.input(
        value=name,
        placeholder="New Prompt",
        on_change=lambda val: EditorState.set_user_instruction_name(val, index),
        max_length=20,  # Limits the number of characters that can be input
        width="200px",  # Explicit width for the input
        style={"minWidth": "200px","fontWeight":"bold"},  # Ensures the input box does not shrink below 200px
        background="white",  # Set background color of input to white
        variant="flushed",
        margin_left="5px",
        margin_inline="0 !important",
        padding_left="0",
        size="lg",
    )

    delete_button = rx.chakra.tooltip(
        rx.chakra.button(
            rx.icon("trash-2",size=16),
            on_click=EditorState.del_user_instruction(index),
            size="sm",
            variant="outline",
        ),
        label="Delete Prompt"
    )

    run_button = rx.chakra.tooltip(
        rx.chakra.button(
            rx.icon("play", size=16),
            on_click=EditorState.send_a_prompt(user_instruction["value"], index),
            size="sm",
            variant="solid",
        ),
        label="Run Prompt",
    ),

    moveup_button = rx.chakra.tooltip(
        rx.chakra.button(
            rx.icon("arrow-up",size=12),
            on_click=EditorState.moveup_user_instruction(index),
            size="sm",
            variant="unstyled",
            padding="0",
        ),
        label="Move Up"
    )

    movedown_button = rx.chakra.tooltip(
        rx.chakra.button(
            rx.icon("arrow-down",size=12),
            on_click=EditorState.movedown_user_instruction(index),
            size="sm",
            variant="unstyled",
            padding="0",
        ),
        label="Move Down"
    )

    # Removed 9/30: its use is unclear
    # The selection pull down defined below
    # options = rx.chakra.select(
    #     EditorState.avail_prompt_engineering_strategies,
    #     placeholder="<Strategy>",
    #     value= current_choice,
    #     on_change=lambda val: EditorState.set_user_instruction_engineering(val, index),
    #     flex="1",  # Allows the dropdown to expand and fill the space
    # )
 
    # Removed 9/30: its use is unclear
    # # Define buttons with controlled width
    # button1 = rx.cond(
    #     current_choice == "Chain of thought",
    #     rx.chakra.vstack(
    #         rx.chakra.button(
    #             "engineer the prompt ↠",
    #             on_click=EditorState.engineer_the_prompt("Chain of thought", index, instruction),
    #             size=   "sm",
    #             variant="link",
    #         ),
    #         spacing=    "10px",
    #         align_items="flex-start"
    #     )
    # )

    # Removed 9/30: its use is unclear
    # button2 = rx.cond(
    #     current_choice == "Original Prompt",
    #     rx.chakra.vstack(
    #         rx.chakra.button(
    #             "Reset to original ↠",
    #             #on_click=EditorState.return_to_original(index),
    #             size=   "sm",
    #             variant="link",
    #         ),
    #         spacing=    "10px",
    #         align_items="flex-start"
    #     )
    # )

    # Removed 9/30: its use is unclear
    # button3 = rx.cond(
    #     current_choice == "A U T O M A T",
    #     rx.chakra.vstack(
    #         rx.chakra.button(
    #             "engineer the prompt ↠",
    #             #on_click=EditorState.engineer_the_prompt("A U T O M A T", index, instruction),
    #             size="sm",
    #             variant="link",
    #         ),
    #         spacing="10px",
    #         align_items="flex-start"
    #     )
    # )

    # Removed 9/30: its use is unclear
    # def generate_engineering_vstack(label: str, engineering_arg: str, placeholder: str, index: int):
    #     return rx.chakra.vstack(
    #         rx.chakra.text(
    #             f"{label}",
    #             size="sm",
    #             margin_bottom="0px",
    #         ),
    #         rx.chakra.input(
    #             placeholder=placeholder,
    #             value=user_instruction[engineering_arg],
    #             on_change=lambda val: EditorState.set_user_instruction_engineering_arg(engineering_arg, val, index),
    #             background="white",
    #             border="2px solid #CBD5E0",
    #             border_radius="4px",
    #         ),
    #         spacing="2px",
    #         align_items="flex-start",
    #         width="100%",
    #     )

    # Removed 9/30: its use is unclear
    # Create individual vstacks for each persona type
    # vstack_agent = generate_engineering_vstack("'A' Agent Persona", "Agent Persona", "<Act as a ...>", index)
    # vstack_user = generate_engineering_vstack("'U' User Persona", "User Persona","<Describe the audience>", index)
    # vstack_targeted = generate_engineering_vstack("'T' Targeted Action", "targeted action","<Describe the task>", index)
    # vstack_output = generate_engineering_vstack("'O' Output Definition", "output definition","<i.e. list of steps, Python Code, ...>", index)
    # vstack_mode = generate_engineering_vstack("'M' Mode / Style", "mode","<i.e. Aggressive, Hemingway style, ...>", index)
    # vstack_atypical = generate_engineering_vstack("'A' Atypical Cases", "atypical cases","<List edge cases and how to proceed >", index)
    # vstack_topic = generate_engineering_vstack("'T' Topic Whitelisting", "Topic Whitelisting","<List permitted converation topics>", index)

    # Removed 9/30: its use is unclear
    # automat_form= rx.cond(
    #     current_choice == "A U T O M A T",
    #     rx.chakra.box(
    #         rx.chakra.grid(
    #             vstack_agent,
    #             vstack_user,
    #             vstack_targeted,
    #             vstack_output,
    #             vstack_mode,
    #             vstack_atypical,
    #             vstack_topic,
    #             template_columns="repeat(auto-fill, minmax(220px, 1fr))",  # Adjusts the number of columns dynamically
    #             gap="20px",
    #             auto_rows="auto",  # Sets the minimum height of the rows
    #             align_items="start",  # Aligns items to the start of the grid area
    #             justify_content="flex-start",  # Aligns content to the start of the grid line
    #             width="100%",
    #             padding="1rem",
    #         ),
    #         border="1px solid #E2E8F0",
    #         border_radius="8px",
    #         background="white",
    #         width="100%",  # Ensures the box takes full width it can within its container
    #         overflow="hidden",  # Adds hidden overflow
    #     )
    # )
    # Stack the components horizontally with appropriate spacing and alignment
    return rx.chakra.vstack(
        rx.chakra.hstack(
            rx.chakra.hstack(
                rx.chakra.text(f"{index+1}.", style={"fontWeight": "bold"}),
                instruction_name_input,
                movedown_button,
                moveup_button,
            ),
            # options, # Removed 9/30: its use is unclear
            rx.chakra.hstack(
                delete_button,
                run_button,
                gap="0.5rem",
            ),
            # button1, # Removed 9/30: its use is unclear
            # button2, # Removed 9/30: its use is unclear
            # button3, # Removed 9/30: its use is unclear
            justify_content="space-between",  # Align items to the start of the hstack
            width="100%",
        ),
        # Removed 9/30: its use is unclear
        # rx.chakra.vstack(
        #     automat_form,
        #     spacing="20px",  # Space between any other items in the VStack, if added
        #     align_items="stretch",  # Stretch children to match the width of the container
        #     justify_content="flex-start",  # Content aligns at the start of the VStack
        #     width="100%",  # VStack takes the full width it can within its container
        #     height="100%",  # Ensure VStack takes the full vertical space it can
        #     border="1px solid #E2E8F0",
        #     border_radius="8px",
        #     background="white",
        #     overflow="hidden",  # Adds hidden overflow
        # ),
        width="100%"
    )



