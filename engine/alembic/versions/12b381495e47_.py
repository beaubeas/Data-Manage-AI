"""empty message

Revision ID: 12b381495e47
Revises: 3d94000b4d4f, b40f446ca242
Create Date: 2024-10-31 09:45:21.278645

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel # added


# revision identifiers, used by Alembic.
revision: str = '12b381495e47'
down_revision: Union[str, None] = ('3d94000b4d4f', 'b40f446ca242')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
