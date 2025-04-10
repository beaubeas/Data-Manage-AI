"""empty message

Revision ID: 759efe09d366
Revises: 693ae09dc797
Create Date: 2024-10-22 22:31:07.076104

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel # added


# revision identifiers, used by Alembic.
revision: str = '759efe09d366'
down_revision: Union[str, None] = '382e51e49046'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('doc_indexes', sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('doc_indexes', 'status')
    # ### end Alembic commands ###
