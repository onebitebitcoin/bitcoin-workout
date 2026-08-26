"""remap 업로드 카테고리 — 운동 전용 2종 → Bitcoiners 2종

Revision ID: 004aa221ea8d
Revises: c7d8e9f0a1b2
Create Date: 2026-08-26

Bitcoiners 리브랜딩으로 업로드 메인 카테고리를 운동 전용 2종
(가벼운 활동/땀 흘리는 운동)에서 비트코이너의 하루 전반을 담는 2종
(비트코인/일상)으로 바꾼다.

`posts.tags`(JSON 배열을 담은 Text 컬럼)의 tags[0]과
`challenges.categories`(JSON 배열 컬럼) 원소를 아래 매핑으로 치환한다.
세부 태그 UI 자체는 이번에 폐기했지만 기존 값(tags[1:])은 손대지 않고
그대로 둔다 — 편집 UI에서만 더 이상 노출되지 않을 뿐 데이터는 보존된다.

    가벼운 활동                              → 일상
    땀 흘리는 운동                           → 일상
    홈트, 러닝, 요가, 웨이트,
    런닝, 조깅, 계단 오르기, 산책             → 일상

기존 운영 데이터는 전부 운동 기록이었고 "비트코인" 카테고리로 보낼
근거가 없어 전부 "일상"으로 몰아넣는다. 필요하면 사용자가 나중에
직접 재분류하면 된다. 매핑에 없는 값(자유 입력된 문자열 등, 백엔드가
화이트리스트 검증을 하지 않아 존재할 수 있다)은 절대 건드리지 않는다.

WARNING — 이 마이그레이션은 비가역이다. downgrade()는 리비전 체인만
c7d8e9f0a1b2로 되돌릴 뿐, 위 매핑이 다대일(예: 홈트/러닝/요가/웨이트가
전부 "일상" 하나로 합쳐짐)이라 원본 카테고리 값은 복원할 수 없다.
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '004aa221ea8d'
down_revision: Union[str, None] = 'c7d8e9f0a1b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CATEGORY_MAP = {
    '가벼운 활동': '일상',
    '땀 흘리는 운동': '일상',
    '홈트': '일상',
    '러닝': '일상',
    '요가': '일상',
    '웨이트': '일상',
    '런닝': '일상',
    '조깅': '일상',
    '계단 오르기': '일상',
    '산책': '일상',
}


def _remap_posts_tags(bind: sa.engine.Connection) -> None:
    """posts.tags[0]만 매핑 치환한다. tags[1:]는 원본 그대로 둔다."""
    posts = sa.table('posts', sa.column('id', sa.Integer), sa.column('tags', sa.Text))
    rows = bind.execute(sa.select(posts.c.id, posts.c.tags).where(posts.c.tags.isnot(None))).fetchall()
    for row in rows:
        try:
            tags = json.loads(row.tags or '[]')
        except (json.JSONDecodeError, TypeError):
            continue
        if not isinstance(tags, list) or not tags or not isinstance(tags[0], str):
            continue
        mapped = _CATEGORY_MAP.get(tags[0])
        if mapped is None:
            continue
        new_tags = [mapped, *tags[1:]]
        bind.execute(
            posts.update().where(posts.c.id == row.id).values(tags=json.dumps(new_tags, ensure_ascii=False))
        )


def _remap_challenge_categories(bind: sa.engine.Connection) -> None:
    """challenges.categories의 각 원소를 매핑 치환한다. UI는 이번에 손대지 않는다.

    posts.tags(Text 컬럼, 애플리케이션이 ensure_ascii=False로 직접 직렬화)와 달리
    이쪽은 SQLAlchemy JSON 컬럼이라 드라이버 기본 직렬화를 탄다. DB에는 한글이
    유니코드 이스케이프로 들어가지만 애플리케이션이 저장하는 방식과 동일하므로
    일부러 맞추지 않는다. raw SQL로 LIKE 검색할 때만 주의하면 된다.
    """
    challenges = sa.table('challenges', sa.column('id', sa.Integer), sa.column('categories', sa.JSON))
    rows = bind.execute(sa.select(challenges.c.id, challenges.c.categories)).fetchall()
    for row in rows:
        categories = row.categories
        if not isinstance(categories, list) or not categories:
            continue
        mapped = [_CATEGORY_MAP.get(c, c) if isinstance(c, str) else c for c in categories]
        # 다대일 매핑이라 서로 다른 원소가 같은 값이 될 수 있다
        # (["가벼운 활동","산책"] → ["일상","일상"]). 순서를 지키며 중복만 제거한다.
        new_categories = []
        for c in mapped:
            if c not in new_categories:
                new_categories.append(c)
        if new_categories == categories:
            continue
        bind.execute(
            challenges.update().where(challenges.c.id == row.id).values(categories=new_categories)
        )


def upgrade() -> None:
    bind = op.get_bind()
    _remap_posts_tags(bind)
    _remap_challenge_categories(bind)


def downgrade() -> None:
    # 다대일 매핑(홈트/러닝/요가/웨이트/런닝/조깅/계단 오르기/산책 → 일상 등)이라
    # 원본 카테고리 값을 복원할 방법이 없다. 리비전 체인만 되돌리고 데이터는 그대로 둔다.
    pass
