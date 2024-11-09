import time
from functools import wraps
import asyncio
from contextvars import ContextVar

# Context variable to track nested calls
timing_stack = ContextVar('timing_stack', default=[])

class TimingContext:
    def __init__(self, func_name):
        self.func_name = func_name
        self.start_time = time.perf_counter()
        self.end_time = None
        self.total_time = 0
        self.child_times = {}

def start_timeit(func_name):
    ctx = TimingContext(func_name)
    stack = timing_stack.get()
    stack.append(ctx)
    timing_stack.set(stack)
    return ctx

def end_timeit(ctx):
    ctx.end_time = time.perf_counter()
    ctx.total_time = ctx.end_time - ctx.start_time
    stack = timing_stack.get()
    stack.pop()
    timing_stack.set(stack)
    if len(stack) == 0:  # This was the root call
        print_report(ctx)
    elif len(stack) > 0:  # This was a nested call
        parent = stack[-1]
        parent.child_times[ctx.func_name] = parent.child_times.get(ctx.func_name, 0) + ctx.total_time

def timeit(func):
    @wraps(func)
    def sync_wrapper(*args, **kwargs):
        ctx = start_timeit(func.__name__)
        try:
            result = func(*args, **kwargs)
        finally:
            end_timeit(ctx)
        return result

    @wraps(func)
    async def async_wrapper(*args, **kwargs):
        ctx = start_timeit(func.__name__)
        try:
            result = await func(*args, **kwargs)
        finally:
            end_timeit(ctx)
        return result

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

def print_report(ctx, indent=""):
    print(f"{indent}{ctx.func_name} took {ctx.total_time:.4f} seconds")
    total_child_time = sum(ctx.child_times.values())
    own_time = ctx.total_time - total_child_time
    if ctx.child_times:
        for child_func, child_time in ctx.child_times.items():
            percentage = (child_time / ctx.total_time) * 100
            print(f"{indent}  {child_func} took {child_time:.4f} seconds ({percentage:.2f}% of total)")
        own_percentage = (own_time / ctx.total_time) * 100
        print(f"{indent}  (own time: {own_time:.4f} seconds, {own_percentage:.2f}% of total)")
        