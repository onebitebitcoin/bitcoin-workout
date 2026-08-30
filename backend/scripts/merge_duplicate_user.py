"""도메인 전환으로 갈라진 lnauth 중복 계정을 원래 계정으로 합친다.

배경: LUD-04 는 지갑의 linkingKey 를 LNURL 의 FQDN 으로 파생한다. 도메인이 바뀌면
같은 지갑이 다른 공개키를 내놓아 빈 새 계정이 생긴다 (docs/LNURL-DOMAIN-MIGRATION.md).
`LNURL_BASE_URL` 고정으로 신규 발생은 막았지만, 이미 생긴 계정에 쌓인 콘텐츠는
사람이 판단해 옮겨야 한다 — 두 계정이 동일인이라는 것은 암호학적으로 증명할 수 없다.

기본은 dry-run 이다. 실제 반영은 --apply 를 붙일 때만 한다.

    python scripts/merge_duplicate_user.py --from 134 --to 70
    python scripts/merge_duplicate_user.py --from 134 --to 70 --apply
"""
from __future__ import annotations

import argparse
import os
import sys

from sqlalchemy import text

# backend/ 루트를 sys.path에 추가 (scripts/seed_first_survey.py 와 같은 방식)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal  # noqa: E402

# (테이블, 사용자 컬럼, 같은 사용자에게 중복되면 안 되는 짝 컬럼 또는 None)
# 짝 컬럼이 있으면 대상 계정에 이미 있는 행은 옮기지 않고 버린다 — UNIQUE 위반 방지.
OWNED_ROWS: list[tuple[str, str, str | None]] = [
    ("posts", "user_id", None),
    ("videos", "user_id", None),
    ("comments", "user_id", None),
    ("post_likes", "user_id", "post_id"),
    ("post_views", "user_id", "post_id"),
    ("follows", "follower_id", "following_id"),
    ("follows", "following_id", "follower_id"),
    ("notifications", "user_id", None),
    ("notifications", "actor_id", None),
    ("challenges", "creator_id", None),
    ("challenge_participations", "user_id", "challenge_id"),
    ("surveys", "created_by", None),
    ("users", "referred_by_id", None),
]


def describe(session, user_id: int) -> str:
    row = session.execute(
        text(
            "SELECT username, oauth_provider, left(oauth_sub, 16) AS pub, created_at "
            "FROM users WHERE id = :id"
        ),
        {"id": user_id},
    ).first()
    if row is None:
        sys.exit(f"오류: 사용자 {user_id} 가 없다")
    return f"{user_id} {row.username!r} provider={row.oauth_provider} pub={row.pub}… 가입={row.created_at}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="src", type=int, required=True, help="합쳐서 없앨 중복 계정 id")
    parser.add_argument("--to", dest="dst", type=int, required=True, help="콘텐츠를 받을 원래 계정 id")
    parser.add_argument("--apply", action="store_true", help="실제로 반영한다 (없으면 dry-run)")
    args = parser.parse_args()

    if args.src == args.dst:
        sys.exit("오류: --from 과 --to 가 같다")

    session = SessionLocal()
    try:
        print(f"원본(비울 계정): {describe(session, args.src)}")
        print(f"대상(남길 계정): {describe(session, args.dst)}")
        print()

        moved = dropped = 0
        for table, column, pair in OWNED_ROWS:
            if pair is None:
                conflict_sql = None
            else:
                conflict_sql = (
                    f"SELECT 1 FROM {table} d "
                    f"WHERE d.{column} = :dst AND d.{pair} = {table}.{pair}"
                )

            where = f"{column} = :src"
            if conflict_sql:
                move_where = f"{where} AND NOT EXISTS ({conflict_sql})"
                drop_where = f"{where} AND EXISTS ({conflict_sql})"
            else:
                move_where, drop_where = where, None

            n_move = session.execute(
                text(f"SELECT count(*) FROM {table} WHERE {move_where}"),
                {"src": args.src, "dst": args.dst},
            ).scalar_one()
            n_drop = (
                session.execute(
                    text(f"SELECT count(*) FROM {table} WHERE {drop_where}"),
                    {"src": args.src, "dst": args.dst},
                ).scalar_one()
                if drop_where
                else 0
            )
            if not n_move and not n_drop:
                continue

            print(f"  {table}.{column}: 이관 {n_move}건" + (f", 중복이라 삭제 {n_drop}건" if n_drop else ""))
            moved += n_move
            dropped += n_drop

            if args.apply:
                if drop_where:
                    session.execute(
                        text(f"DELETE FROM {table} WHERE {drop_where}"),
                        {"src": args.src, "dst": args.dst},
                    )
                session.execute(
                    text(f"UPDATE {table} SET {column} = :dst WHERE {column} = :src"),
                    {"src": args.src, "dst": args.dst},
                )

        print(f"\n합계: 이관 {moved}건, 삭제 {dropped}건")

        # 중복 계정은 로그인 경로를 끊고 남긴다. DELETE 는 되돌릴 수 없고,
        # 남겨두면 나중에 오판이었음이 드러나도 복구할 수 있다.
        print(f"  users[{args.src}]: oauth_sub 를 비워 로그인 경로를 끊고 계정 자체는 남긴다")
        if args.apply:
            session.execute(
                text(
                    "UPDATE users SET oauth_sub = NULL, is_banned = true, "
                    "username = username || ' (병합됨→" + str(args.dst) + ")' "
                    "WHERE id = :src"
                ),
                {"src": args.src},
            )
            session.commit()
            print("\n반영 완료.")
        else:
            session.rollback()
            print("\ndry-run 이라 아무것도 바꾸지 않았다. 반영하려면 --apply 를 붙여라.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
