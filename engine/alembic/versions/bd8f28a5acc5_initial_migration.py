"""initial migration

Revision ID: bd8f28a5acc5
Revises: 
Create Date: 2024-02-25 11:59:02.167337

"""
from typing import Sequence, Union
import sqlmodel.sql.sqltypes

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd8f28a5acc5'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass

def downgrade() -> None:
    pass
