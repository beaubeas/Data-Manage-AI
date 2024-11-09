from typing import TypeVar, Generic, Iterator, List
import bisect
from functools import reduce
from sqlalchemy import event
from time import time
import logging
import re
import json
import os

SYSTEM_AGENTS_DIR = os.path.join(os.path.dirname(__file__), "../../system_agents")

def dict_safe_get(src, *paths, default=None):
    """ Safely get a value from a nested dictionary. """
    try:
        return reduce(lambda d, k: d[k], paths, src)
    except KeyError:
        return default
    
def create_default_google_credential(engine, user, tokens: dict):
    # Create a default Credential for use by our Google tools. This is used
    # if we request powerful scopes from Google. But not needed for regular login.
    if tokens and 'access_token' in tokens and \
        'refresh_token' in tokens and 'expires_at' in tokens:
        try:
            engine.stuff_google_credential_for_user(
                user.tenant_id,
                user.id,
                tokens['access_token'],
                tokens['refresh_token'],
                tokens['id_token'],
                tokens['expires_at']
            )
        except Exception as e:
            print("Error POSTing Google Credential: ", e)

T = TypeVar('T')

class SortedList(Generic[T]):
    def __init__(self):
        self._list: List[T] = []
    
    def add(self, item: T):
        bisect.insort(self._list, item)
    
    def __repr__(self):
        return repr(self._list)

    def __iter__(self) -> Iterator[T]:
        return iter(self._list)
    
    def extend(self, items: List[T]):
        for item in items:
            self.add(item)

    def clear(self):
        self._list.clear()
        
    def all(self) -> list:
        return self._list
    

def before_execute(conn, clauseelement, multiparams, params):
    print("Before execute")
    conn.info.setdefault('query_start_time', []).append(time())

def after_execute(conn, clauseelement, multiparams, params, result):
    print("after execute")
    total_time = time() - conn.info['query_start_time'].pop(-1)
    print(f"Total Query Time: {total_time} seconds")

log_handler: logging.Handler = None
log_tags = []
current_tag = None

def log_query_timings(engine):
    global log_handler

    logging.basicConfig()
    logger = logging.getLogger('sqlalchemy.engine')
    logger.setLevel(logging.INFO)

    log_handler = logging.StreamHandler()

    # Define a formatter with a timestamp
    formatter = logging.Formatter('%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

    # Set the formatter on the handler
    log_handler.setFormatter(formatter)

    # Add the handler to the logger
    logger.addHandler(log_handler)

def set_sql_logging_tag(tag: str):
    global log_handler, current_tag

    if log_handler:
        formatter = logging.Formatter(f"[{tag}] " + '%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        log_handler.setFormatter(formatter)
        current_tag = tag

def push_sql_logging_tag(tag: str):
    global log_handler, log_tags, current_tag

    if log_handler:
        log_tags.append(current_tag)
        set_sql_logging_tag(tag)

def pop_sql_logging_tag():
    global log_handler, log_tags

    if len(log_tags) > 0:
        tag = log_tags.pop()
        set_sql_logging_tag(tag)

#    # Attach the event listeners to your engine
#    event.listen(engine, "before_execute", before_execute)
#    event.listen(engine, "after_execute", after_execute)
# import threading
# import cloudpickle

# def monkeypatch_cloudpickle():
#     lock_class = threading.Lock().__class__

#     def replace_locks_with_none(obj, visited=None):
#         if visited is None:
#             visited = set()

#         if id(obj) in visited:
#             return obj
#         visited.add(id(obj))

#         if isinstance(obj, lock_class):
#             return None  # Replace lock with None

#         if isinstance(obj, dict):
#             return {key: replace_locks_with_none(val, visited) for key, val in obj.items()}
#         elif isinstance(obj, list):
#             return [replace_locks_with_none(item, visited) for item in obj]
#         elif isinstance(obj, tuple):
#             return tuple(replace_locks_with_none(item, visited) for item in obj)
#         elif hasattr(obj, '__dict__'):
#             for key, value in vars(obj).items():
#                 setattr(obj, key, replace_locks_with_none(value, visited))
#         return obj

#     def custom_dumps(obj, *args, **kwargs):
#         # Replace all locks with None before serialization
#         processed_obj = replace_locks_with_none(obj)
#         # Serialize using the original cloudpickle.dumps
#         return original_dumps(processed_obj, *args, **kwargs)

#     original_dumps = cloudpickle.dumps  # Keep reference to the original function, if needed
#     cloudpickle.dumps = custom_dumps