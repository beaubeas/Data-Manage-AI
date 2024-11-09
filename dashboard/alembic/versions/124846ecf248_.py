"""empty message

Revision ID: 124846ecf248
Revises: 612be2597b79
Create Date: 2024-04-09 10:52:39.203998

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '124846ecf248'
down_revision: Union[str, None] = '612be2597b79'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('tools', sa.Column('tool_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('tools', 'tool_name')
    # ### end Alembic commands ###
