import reflex as rx

from supercog.dashboard.state_models import AgentState
from supercog.dashboard.components.chat import chat_messages, action_bar
# from supercog.dashboard.pages.edit_agent import make_accordian

# from supercog.dashboard.pages.edit_agent import tool_link

# # Read-only version of the tools in use
# def show_tools(app: AgentState) -> rx.Component:
#     return rx.chakra.vstack(
#         rx.chakra.text("Tools", font_weight="bold", font_size="md"),
#         rx.foreach(
#             app.uitools,
#             lambda tool: rx.hstack(
#                 rx.cond(
#                     tool.logo_url,
#                     rx.image(
#                         src=tool.logo_url,
#                         height="18px",
#                     ),
#                 ),
#                 rx.cond(
#                     tool.agent_url,
#                     rx.link(rx.text(tool.name, font_size="md"), href=tool.agent_url, target="_blank"),
#                     tool_link(tool),
#                 ),
#                 rx.chakra.spacer(),
#                 width="100%",
#                 align_items="stretch",
#             )
#         ),
#     )


# def guest_chat_window(app):
#     return rx.chakra.box(
#         rx.chakra.vstack(
#             # I think we need to use our specific state class, can't just use the parent
#             chat_messages(),
#             # not sure about file uploads in the guest action bar...
#             action_bar(),
#             flex="1",
#             align_items="stretch",
#             overflow="auto",
#             min_width="500px",
#             width="500px",
#         ),
#         rx.chakra.vstack(
#             show_tools(app),
#             rx.chakra.text(
#                 "See the Agent Instructions",
#             ),
#             make_accordian(
#                 "Instructions",
#                 rx.chakra.text(
#                     app.system_prompt,
#                     is_disabled=True,
#                     font_size="md",
#                 ),
#             ),
#             gap="20px",
#         ),
#         padding="2px",
#         width="100%",
#         height="calc(100% - 27px)", #have to substract height of the Agent header
#         display="flex",
#         align_items="stretch",
#         flex="1",
#         gap="20px",
#     )

