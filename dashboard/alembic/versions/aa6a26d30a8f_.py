"""empty message

Revision ID: aa6a26d30a8f
Revises: 
Create Date: 2024-02-14 22:22:43.244326

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = 'aa6a26d30a8f'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('users',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('gtoken_sub', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('gtoken_email', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('gtoken_json', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('users')
    # ### end Alembic commands ###
