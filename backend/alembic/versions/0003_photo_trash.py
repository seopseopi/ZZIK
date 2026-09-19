"""Keep trashed photos and their edit history until restored."""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('photos', sa.Column('trashed_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index('ix_photos_trashed_at', 'photos', ['trashed_at'])


def downgrade():
    op.drop_index('ix_photos_trashed_at', table_name='photos')
    op.drop_column('photos', 'trashed_at')
