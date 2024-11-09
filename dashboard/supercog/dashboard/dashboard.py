"""Welcome to Reflex!."""
import os
import sys
import traceback
from typing import Optional
from pydantic import BaseModel

import rollbar

from fastapi_lifespan_manager import LifespanManager

lifespan_manager = LifespanManager()

from supercog.dashboard import styles
from supercog.dashboard.slack.app import initialize_slack

# Import all the pages.
from supercog.dashboard.pages import *
from .utils import log_query_timings

import reflex as rx

class MyMiddle(rx.Middleware):
    """Middleware to preprocess and postprocess requests."""

    async def preprocess(self, app: rx.App, state, event):
        if hasattr(app, 'state_manager') and app.state_manager:
            app.state_manager.lock_expiration = 3*60*1000
            return None

def custom_backend_handler(
    exception: Exception,
) -> Optional[rx.event.EventSpec]:
    # My custom logic for backend errors
    rollbar.report_exc_info(sys.exc_info())
    traceback.print_exc()
    return rx.toast.error(str(sys.exc_info()[1]))


rb_token = os.environ.get("ROLLBAR_TOKEN")
if rb_token:
    rb_env = os.environ.get("ENV", "dev")
    print("CONNECTING TO ROLLBAR: ", rb_token[0:5], rb_env)
    rollbar.init(rb_token, environment=rb_env)

# Create the app.
app = rx.App(
    style=styles.base_style, 
    stylesheets=["styles.css"],
    theme=rx.theme(appearance="light"),
    backend_exception_handler=custom_backend_handler,
    overlay_component=(
        rx.fragment(
            rx.toast.provider(
                close_button=True,
                toast_options=rx.toast.options(
                    dismissible=True,
                    duration=5000,
                    style={
                        "zIndex": "var(--chakra-zIndices-toast)"
                    }
                ),

            ),
        )
    )
)
# We have long running requests running the agents
app.add_middleware(MyMiddle())

if os.environ.get("SQL_LOGGING", "0") == "1":
    with rx.session() as session:
        log_query_timings(session.bind)

async def cancel_agent_run(run_id: str):
    from .engine_client import EngineClient
    print("Cancelling agent run", run_id)
    EngineClient().cancel_run(run_id)
    return {"status": "cancelled"}

app.api.add_api_route("/cancelrun/{run_id}", cancel_agent_run)

class SignupWaitlistRequest(BaseModel):
    email: str
    request: Optional[str]

async def signup_waitlist(request: SignupWaitlistRequest):
    from .models import Lead

    with rx.session() as sess:
        print("Creaing a lead with email: ", request.email)
        sess.add(Lead(email=request.email, request=request.request))
        sess.commit()

    return {"status": "OK"}

app.api.add_api_route("/signup_waitlist", signup_waitlist, methods=["POST"])

initialize_slack(app)
