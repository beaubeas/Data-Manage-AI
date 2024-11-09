"""empty message

Revision ID: 382e51e49046
Revises: 693ae09dc797, e82ad09d36d3
Create Date: 2024-10-23 17:29:31.717083

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel # added


# revision identifiers, used by Alembic.
revision: str = '382e51e49046'
down_revision: Union[str, None] = ('693ae09dc797', 'e82ad09d36d3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
