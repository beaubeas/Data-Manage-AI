# This is to hack around `reflex run` which expects the app to live in file
# named after the module, like:
#   monster/monster.py
# but we actually put our app in `monster/dashboard/dashboard.py`

from supercog.dashboard.dashboard import *

