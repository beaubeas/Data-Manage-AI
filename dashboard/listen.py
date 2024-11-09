import redis
import json

r = redis.Redis(host='localhost', port=6379, decode_responses=True)
from streetlamp.state_models import AgentTrigger

def handle_message(message):
    data = message['data']
    at = AgentTrigger(**(json.loads(data)))
    print("Agent Trigger: ", at)

pubsub = r.pubsub()
pubsub.subscribe(**{'triggers': handle_message})
pubsub.run_in_thread()
