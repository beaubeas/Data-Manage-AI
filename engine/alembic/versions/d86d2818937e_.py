"""empty message

Revision ID: d86d2818937e
Revises: b8ee64a0bf68
Create Date: 2024-04-29 17:45:48.345236

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel # added


# revision identifiers, used by Alembic.
revision: str = 'd86d2818937e'
down_revision: Union[str, None] = 'b8ee64a0bf68'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('agents', sa.Column('agent_slug', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('agents', sa.Column('temperature', sa.Float(), nullable=True))
    op.add_column('agents', sa.Column('max_agent_time', sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('agents', 'max_agent_time')
    op.drop_column('agents', 'temperature')
    op.drop_column('agents', 'agent_slug')
    # ### end Alembic commands ###
