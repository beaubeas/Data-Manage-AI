import asyncio
import json
import time
import signal
import os
import multiprocessing

from supercog.shared.apubsub import pubsub
from .enginemgr import AgentTask, EngineManager

# This class takes incoming requests to the agentsvc
# and dispatches them via a Redis based worker queue.
#
# Agents have "tenant affinity" and so we run one or more per tenant, and
# dispatch tasks to a stream per tenant.

# This class will start agent "workers" on demand.

class AgentDispatcher:
    def __init__(self, enginemgr):
        self.started_consumers = {}  # Dictionary to keep track of started consumers

    async def connect(self):
        print("Agent dispatcher connecting to Redis")
        self.redis = await pubsub.get_client()

    async def enqueue_task(self, tenant_id: str, task_data: AgentTask) -> str:
        # Queues an agent task and returns the task ID for identifying it later
        if not self.redis:
            await self.connect()
        
        stream_name = f'agents:{tenant_id}'

        # Check for active consumers before publishing
        active_consumers = await self.check_stream_consumers(stream_name)
        if not active_consumers:
            print(f"Warning: No active consumers for {stream_name}")
            # Execute a worker for this task type
            await self.exec_worker(tenant_id)
            # Wait for the worker to become active
            await self.wait_for_worker(stream_name)
        
        await self.redis.xadd(stream_name, {'task': task_data.json()})

    async def check_stream_consumers(self, stream_name):
        heartbeat_keys = await self.redis.keys("heartbeat:consumer_*")
        active_consumers = []

        task_id = stream_name.split(':')[1]
        for key in heartbeat_keys:
            heartbeat_data = await self.redis.get(key)
            if heartbeat_data:
                data = json.loads(heartbeat_data)
                print(data)
                if task_id in data['streams']:
                    consumer_name = key.split(':')[1]
                    last_heartbeat = data['timestamp']
                    if time.time() - last_heartbeat < 15:  # Consider consumer alive if heartbeat within last 15 seconds
                        active_consumers.append(consumer_name)

        return active_consumers

    async def exec_worker(self, tenant_id: str):
        # This function will start a new worker process
        process = multiprocessing.Process(target=self.run_async_worker, args=(tenant_id,))
        process.start()
        self.started_consumers[tenant_id] = process
        print(f"Executed new worker for task type: {tenant_id}, process: {process}")
        EngineManager.reset_db_connections()

    @staticmethod
    def run_async_worker(tenant_id: str):
        # This function runs the async worker in a new event loop
        asyncio.run(EngineManager([tenant_id]).task_loop())

    async def wait_for_worker(self, stream_name, timeout=30):
        # Wait for the worker to become active
        start_time = time.time()
        while time.time() - start_time < timeout:
            active_consumers = await self.check_stream_consumers(stream_name)
            if active_consumers:
                print(f"Worker for {stream_name} is now active")
                return True
            await asyncio.sleep(0.3)
        print(f"Timeout waiting for worker for {stream_name}")
        return False

    def close(self):
        self.cleanup_consumers()

    def cleanup_consumers(self):
        for task_type, process in self.started_consumers.items():
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                print(f"Terminated consumer process {process.pid} for task type: {task_type}")
            except ProcessLookupError:
                print(f"Consumer for task type {task_type} already terminated")
            except Exception as e:
                print(f"Error terminating consumer for task type {task_type}: {str(e)}")

class NoOpDispatch(AgentDispatcher):
    enginemgr: EngineManager

    def __init__(self, enginemgr: EngineManager):
        self.enginemgr = enginemgr
    
    async def enqueue_task(self, tenant_id: str, task_data: AgentTask) -> str:
        await self.enginemgr._process_task(task_data.model_dump(), synchronous=False)

    def close(self):
        pass

if os.environ.get('TASK_QUEUE_AGENTS'):
    print("Running Agents in separate processes")
    AgentDispatcherClass = AgentDispatcher
else:
    print("Using single process for Agents")
    AgentDispatcherClass = NoOpDispatch
