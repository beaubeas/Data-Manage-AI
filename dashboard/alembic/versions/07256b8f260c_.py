"""empty message

Revision ID: 07256b8f260c
Revises: cc30848cb34f
Create Date: 2024-02-19 11:01:58.104519

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = '07256b8f260c'
down_revision: Union[str, None] = 'cc30848cb34f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('tools_credential_id_fkey', 'tools', type_='foreignkey')
    op.drop_table('credentials')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_foreign_key('tools_credential_id_fkey', 'tools', 'credentials', ['credential_id'], ['id'])
    op.create_table('credentials',
    sa.Column('id', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('name', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('tool_factory_id', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('scope', sa.VARCHAR(), autoincrement=False, nullable=False),
    sa.Column('secrets_json', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('user_id', sa.VARCHAR(), autoincrement=False, nullable=True),
    sa.Column('tenant_id', sa.VARCHAR(), server_default=sa.text("'tenant1'::character varying"), autoincrement=False, nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='credentials_user_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='credentials_pkey')
    )
    # ### end Alembic commands ###
