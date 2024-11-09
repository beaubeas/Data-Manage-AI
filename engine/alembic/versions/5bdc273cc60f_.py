"""empty message

Revision ID: 5bdc273cc60f
Revises: b103e0c542e8
Create Date: 2024-07-01 16:56:06.966113

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel # added


# revision identifiers, used by Alembic.
revision: str = '5bdc273cc60f'
down_revision: Union[str, None] = 'b103e0c542e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('run', sa.Column('model', sa.VARCHAR(), server_default='', nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('run', 'model')
    # ### end Alembic commands ###
