"""empty message

Revision ID: 5e578b533622
Revises: 24bbe7266ce5
Create Date: 2024-02-21 07:47:06.113858

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '5e578b533622'
down_revision: Union[str, None] = '24bbe7266ce5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('tenants',
    sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('domain', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.alter_column('agents', 'tenant_id',
               existing_type=sa.VARCHAR(),
               nullable=False,
               existing_server_default=sa.text("'tenant1'::character varying"))
    op.drop_column('tools', 'tenant_id')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('tools', sa.Column('tenant_id', sa.VARCHAR(), server_default=sa.text("'tenant1'::character varying"), autoincrement=False, nullable=False))
    op.alter_column('agents', 'tenant_id',
               existing_type=sa.VARCHAR(),
               nullable=True,
               existing_server_default=sa.text("'tenant1'::character varying"))
    op.drop_table('tenants')
    # ### end Alembic commands ###
