"""empty message

Revision ID: 9f2b081be91f
Revises: 47b58f81639e
Create Date: 2024-04-29 10:47:21.820625

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '9f2b081be91f'
down_revision: Union[str, None] = '47b58f81639e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('agents', sa.Column('agent_slug', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('agents', sa.Column('temperature', sa.Float(), server_default=sa.text('0.0'), nullable=True))
    op.add_column('agents', sa.Column('max_agent_time', sa.Integer(), server_default=sa.text('180'), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('agents', 'max_agent_time')
    op.drop_column('agents', 'temperature')
    op.drop_column('agents', 'agent_slug')
    # ### end Alembic commands ###
