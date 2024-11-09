from supercog.dashboard.settings_state import SettingsState

import reflex as rx

def usage_tables() -> rx.Component:
    return rx.chakra.vstack(
        rx.chakra.heading(
            "Agent Usage, last 24 hours", 
            size="md", 
            padding_top="60px", 
            padding_bottom="20px"
        ),
        rx.data_table(
            data=SettingsState.agent_data,
        ),
        rx.chakra.heading(
            "Usage by model, last 24 hours", 
            size="md", 
            padding_top="60px", 
            padding_bottom="20px"
        ),
        rx.data_table(
            data=SettingsState.model_data,
        ),
        align_items="flex-start",
    )
