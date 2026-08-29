"""add_btc_price_krw_to_posts

Revision ID: cbb7d21fb47c
Revises: 004aa221ea8d
Create Date: 2026-08-29

"나의 오렌지 나무" 기능을 위해 게시물 생성 시점의 BTC/KRW 가격을 박제하는 컬럼을 추가한다.
기존 게시물은 그 시점의 가격을 알 수 없으므로 NULL로 남기고 백필하지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cbb7d21fb47c'
down_revision: Union[str, None] = '004aa221ea8d'  # expand 단계: ADD COLUMN 은 구 코드가 모르므로 안전하다
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('posts', sa.Column('btc_price_krw', sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column('posts', 'btc_price_krw')
