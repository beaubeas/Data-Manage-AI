from sqlmodel import select
from supercog.dashboard.models import *
from supercog.shared.services import _get_session

session = _get_session()
print("session var available, and all Dashboard models")

