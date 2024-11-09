import reflex as rx

from supercog.shared.services import config
from supercog.shared.logging import logger

from .editor_state import EditorState

from .models import User, GUEST_USER_ID
from .state_models import AgentState
from .models import Agent

# We inherit from EditorState because it has all the machinery for running and showing chats.

class GuestState(EditorState):
    agent_id: str

    def on_page_load(self):
        avail_agents = config.get_global("GUEST_AGENTS", required=False)
        if avail_agents is None:
            logger.warn("GUEST_AGENTS is not set")
            return rx.redirect("/")
        else:
            guest_agents = avail_agents.split(",")
        self.agent_id = self.router.page.params.get('agentid', None)
        if self.agent_id is None or self.agent_id not in guest_agents:
            logger.warn("agent id not on GUEST_AGENTS list")
            return rx.redirect("/notfound")
        
        print("Agent is is: ", self.agent_id)

        with rx.session() as sess:
            self._agent = sess.get(Agent, self.agent_id) # type: ignore
            if self._agent is None:
                raise RuntimeError(f"Agent '{self.agent_id}' not found")

            # FIXME: SUPERHACK!!
            # We added this so that "guest" users could run some agents
            user = User(id=GUEST_USER_ID, name="<guest>", email="none", tenant_id="__guest_tenant__")
            #self._agentsvc.user_login("__guest_tenant__", GUEST_USER_ID)
            self.signal_user_authenticated(user, sess)

            # create our UI state version of the agent, and fix any missing creds
            self.load_connections()
            self.app = AgentState.create(sess, self._agent, self._get_uitool_info, fixup_creds=True)



