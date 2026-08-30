"""게시물 설명(posts.caption) 길이 제한 확대 — varchar(140) → text

Revision ID: 21777a3ca33d
Revises: c7d8e9f0a1b2
Create Date: 2026-08-30

피드에서 설명이 2줄로 잘린 뒤 펼쳐볼 방법이 없다는 문제를 고치면서, 애초에
설명을 길게 쓸 수 없다는 근본 제약도 함께 푼다. 상한을 140자 → 2200자
(인스타그램 수준)로 올린다.

컬럼 타입은 text 로 바꾸고 길이 상한은 애플리케이션
(app.schemas.video.CAPTION_MAX_LEN)에서만 강제한다. varchar(2200) 으로 두면
다음에 상한을 조정할 때 또 DDL 이 필요해지기 때문이다.

이 마이그레이션은 expand 전용이라 blue-green 무중단 배포에 안전하다. 구 코드가
붙어 있어도 140자 이하만 쓸 뿐이고, 넓어진 컬럼에서 읽는 것은 아무 문제가 없다.
따라서 앱 배포보다 먼저 반영해도 된다.

WARNING — downgrade() 는 varchar(140) 으로 되돌리므로, 그 사이 저장된 140자
초과 설명이 있으면 PostgreSQL 이 에러를 내거나(기본 동작) 데이터가 잘린다.
되돌리기 전에 초과 행을 먼저 정리해야 한다:

    SELECT id FROM posts WHERE char_length(caption) > 140;
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '21777a3ca33d'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'posts', 'caption',
        existing_type=sa.String(length=140),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'posts', 'caption',
        existing_type=sa.Text(),
        type_=sa.String(length=140),
        existing_nullable=True,
    )
