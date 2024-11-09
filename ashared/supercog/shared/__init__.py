# We have some decorator based timing functions in ashared/supercog/shared/profiler.py.
# To make it easy to enable or disable those, we import the profiling functions
# here in the main module if this flag is set. If the flag is False then we import
# no-ops functions instead. This way you can always instrument your code with the
# @timeit decorator, and enable/disable the profiling right here.
ENABLE_PROFILING = False

if ENABLE_PROFILING:
    from .profiler import timeit, start_timeit, end_timeit
else:
    from .noprofile import timeit, start_timeit, end_timeit
