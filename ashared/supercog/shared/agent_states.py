# I wrote code to suppoort "states" within agents via
# syntax in the instructions:
#
# [[state1]]
# instructions for state1
# [[state2]]
# instructions for state2
#
# but I never got the resulting agent to work properly. So for
# now I've just saved this code off here.

class AgentStates:
    def get_agent_states(self) -> list[str]:
        # Regexp search for patterns like:
        # [[state]]
        # across lines in the system prompt       
        pattern = r'^\s*\[\[(.*?)\]\]'
        return [s.strip() for s in re.findall(pattern, self.system_prompt or "", re.MULTILINE)]

    def get_active_prompt(self) -> list:
        if not self.state:
            return parse_markdown(self.system_prompt or "")
        return self.get_state_prompt(self.state)
    
    def get_state_prompt(self, state: str) -> list:
        lines = (self.system_prompt or "").split("\n")
        active: list[str] = []
        collecting = False
        for line in lines:
            if not collecting and re.match(fr'^\s*\[\[\s*{state}\s*\]\]', line):
                collecting = True
            elif not state and not collecting and re.match(r'^\s*\[\[(.*)\]\]', line):
                collecting = True # default to first state if "state" not specified
            elif collecting and re.match(r'^\s*\[\[(.*)\]\]', line):
                # next state
                break
            elif collecting and not line.startswith("#"):
                active.append(line)

        if len(active) > 0:
            # parse prompt as markdown to remove special parts
            return parse_markdown("\n".join(active))
        
        # unknown state, default to the last one
        return []

    def get_state_welcome_message(self, state_: str|None=None):
        prompt_nodes = self.get_state_prompt(state_ or self.state or "")
        node = next((n for n in prompt_nodes if n.tag == NodeTypes.CODE_BLOCK), None)
        if node:
            return node.content

    def get_state_welcome_message_map(self) -> dict[str,str]:
        map = {}
        for state in self.get_agent_states():
            map[state] = self.get_state_welcome_message(state)
        return map
