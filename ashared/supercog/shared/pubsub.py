from typing import Any
import json
import redis

AGENT_EVENTS_CHANNEL = "agent_events"
REDIS_HOST = "localhost"
REDIS_PORT = 6379

class PubSub:
    def __init__(self):

        self.redis = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)

    def publish(self, channel: str, message: Any):
        if not isinstance(message, str):
            if hasattr(message, "json"):
                message = message.json()
            else:
                message = json.dumps(message)
        self.redis.publish(channel, message)

    def agent_saved_event(self, agent_id: str):
        return {"type": "agent_saved", "agent_id": agent_id}

    def run_created_event(self, agent_id: str, run_id: str):
        return {"type": "run_created", "agent_id": agent_id, "run_id": run_id}
    
pubsub = PubSub()
