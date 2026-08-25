"""drop reward_points — 점수(땀방울) 체계 제거

Revision ID: c7d8e9f0a1b2
Revises: d953acd3a18d
Create Date: 2026-08-26

포인트 적립/정산/리더보드를 서비스에서 걷어내면서 테이블도 함께 내린다.
downgrade는 빈 스키마만 복원한다 — 적립 이력 자체는 되살아나지 않는다.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c7d8e9f0a1b2'
down_revision: Union[str, None] = 'd953acd3a18d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('reward_points')


def downgrade() -> None:
    op.create_table(
        'reward_points',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('points', sa.Float(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('reference_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(), server_default='fixed', nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('reward_points', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reward_points_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_reward_points_status'), ['status'], unique=False)
        batch_op.create_index(
            'ix_reward_points_user_status_created',
            ['user_id', 'status', 'created_at'],
            unique=False,
        )
