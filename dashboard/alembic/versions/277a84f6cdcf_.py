"""empty message

Revision ID: 277a84f6cdcf
Revises: f8a6c574417a
Create Date: 2024-02-14 22:54:02.346171

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '277a84f6cdcf'
down_revision: Union[str, None] = 'f8a6c574417a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('agents', 'welcome_message',
               existing_type=sa.VARCHAR(),
               nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('agents', 'welcome_message',
               existing_type=sa.VARCHAR(),
               nullable=False)
    # ### end Alembic commands ###
