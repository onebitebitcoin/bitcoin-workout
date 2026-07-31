import io
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Query, UploadFile
from PIL import Image
from sqlalchemy import String, cast, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from app.config import settings as app_settings
from app.database import get_db
from app.models.challenge import Challenge, ChallengeParticipation
from app.models.post import Post
from app.models.user import User
from app.models.video import Video
from app.routes.auth import get_current_user, get_optional_user
from app.schemas.challenge import (
    ChallengeCreateRequest,
    ChallengeSchema,
    ChallengeUpdateRequest,
    EarnedTitleSchema,
)
from app.services import r2 as r2_service
from app.services.error_codes import (
    E_ADMIN_REQUIRED,
    E_CHALLENGE_ALREADY_COMPLETED,
    E_CHALLENGE_ALREADY_JOINED,
    E_CHALLENGE_CLOSED,
    E_CHALLENGE_CREATE_FAILED,
    E_CHALLENGE_ENDED,
    E_CHALLENGE_FULL,
    E_CHALLENGE_INVALID,
    E_CHALLENGE_NOT_FOUND,
    E_CHALLENGE_NOT_JOINED,
    E_CHALLENGE_NOT_PARTICIPATING,
    E_CHALLENGE_OWNER_REQUIRED,
    E_CHALLENGE_TITLE_TAKEN,
    E_FORBIDDEN,
    E_IMAGE_FORMAT_INVALID,
    E_MANAGER_REQUIRED,
    E_PARTICIPATION_NOT_FOUND,
    api_error,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/challenges", tags=["challenges"])


def _to_schema(
    challenge: Challenge,
    user_id: int | None,
    db: Session,
    *,
    participant_counts: dict[int, int] | None = None,
    my_participations: dict[int, ChallengeParticipation] | None = None,
    creator_map: dict[int, User] | None = None,
) -> ChallengeSchema:
    if participant_counts is not None:
        participant_count = participant_counts.get(challenge.id, 0)
    else:
        participant_count = (
            db.query(func.count(ChallengeParticipation.id))
            .filter(ChallengeParticipation.challenge_id == challenge.id)
            .scalar()
            or 0
        )

    my_upload_count = 0
    joined = False
    completed = False
    if user_id:
        if my_participations is not None:
            p = my_participations.get(challenge.id)
        else:
            p = (
                db.query(ChallengeParticipation)
                .filter(
                    ChallengeParticipation.challenge_id == challenge.id,
                    ChallengeParticipation.user_id == user_id,
                )
                .first()
            )
        if p:
            joined = True
            my_upload_count = p.upload_count
            completed = p.completed_at is not None

    creator_username: str | None = None
    if challenge.creator_id:
        if creator_map is not None:
            creator = creator_map.get(challenge.creator_id)
        else:
            creator = db.get(User, challenge.creator_id)
        creator_username = creator.username if creator else None

    now = datetime.now(timezone.utc)
    recruit_end = challenge.recruit_end
    if recruit_end and recruit_end.tzinfo is None:
        recruit_end = recruit_end.replace(tzinfo=timezone.utc)
    is_recruiting = (
        (recruit_end is None or now <= recruit_end)
        and (challenge.max_participants is None or participant_count < challenge.max_participants)
    )

    return ChallengeSchema(
        id=challenge.id,
        title=challenge.title,
        description=challenge.description,
        reward_title=challenge.reward_title,
        condition_value=challenge.condition_value,
        goal_description=challenge.goal_description,
        start_date=challenge.start_date,
        end_date=challenge.end_date,
        recruit_start=challenge.recruit_start,
        recruit_end=challenge.recruit_end,
        max_participants=challenge.max_participants,
        is_recruiting=is_recruiting,
        is_active=challenge.is_active,
        categories=challenge.categories or [],
        participant_count=participant_count,
        my_upload_count=my_upload_count,
        joined=joined,
        completed=completed,
        creator_id=challenge.creator_id,
        creator_username=creator_username,
        image_url=challenge.image_url,
        image_thumb_url=challenge.image_thumb_url,
    )


def _build_batch_maps(
    challenges: list[Challenge],
    user_id: int | None,
    db: Session,
) -> tuple[dict[int, int], dict[int, ChallengeParticipation], dict[int, User]]:
    """챌린지 목록에 대한 N+1 없이 배치 조회."""
    ids = [c.id for c in challenges]

    participant_counts: dict[int, int] = {}
    if ids:
        rows = (
            db.query(ChallengeParticipation.challenge_id, func.count(ChallengeParticipation.id))
            .filter(ChallengeParticipation.challenge_id.in_(ids))
            .group_by(ChallengeParticipation.challenge_id)
            .all()
        )
        participant_counts = {cid: cnt for cid, cnt in rows}

    my_participations: dict[int, ChallengeParticipation] = {}
    if user_id and ids:
        ps = (
            db.query(ChallengeParticipation)
            .filter(
                ChallengeParticipation.challenge_id.in_(ids),
                ChallengeParticipation.user_id == user_id,
            )
            .all()
        )
        my_participations = {p.challenge_id: p for p in ps}

    creator_ids = list({c.creator_id for c in challenges if c.creator_id})
    creator_map: dict[int, User] = {}
    if creator_ids:
        creators = db.query(User).filter(User.id.in_(creator_ids)).all()
        creator_map = {u.id: u for u in creators}

    return participant_counts, my_participations, creator_map


@router.get("")
def list_challenges(
    q: str | None = Query(None),
    category: str | None = Query(None),
    joined: bool | None = Query(None),
    available: bool | None = Query(None),
    closed: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> dict:
    if closed:
        query = db.query(Challenge).filter(Challenge.is_active == False)
    else:
        query = db.query(Challenge).filter(Challenge.is_active == True)
    if q:
        query = query.filter(Challenge.title.ilike(f"%{q}%"))
    if category:
        query = query.filter(cast(Challenge.categories, String).contains(f'"{category}"'))
    challenges = query.order_by(Challenge.start_date.desc()).offset(offset).limit(limit).all()
    uid = current_user.id if current_user else None

    participant_counts, my_participations, creator_map = _build_batch_maps(challenges, uid, db)
    schemas = [
        _to_schema(c, uid, db, participant_counts=participant_counts,
                   my_participations=my_participations, creator_map=creator_map)
        for c in challenges
    ]

    if joined is not None and uid:
        if joined:
            schemas = [s for s in schemas if s.joined]
        else:
            schemas = [s for s in schemas if not s.joined]

    if available and uid:
        schemas = [s for s in schemas if not s.joined and s.is_recruiting]

    return {"data": {"challenges": schemas}}


def _assert_reward_title_unique(db: Session, reward_title: str, exclude_id: int | None = None) -> None:
    q = db.query(Challenge).filter(Challenge.reward_title == reward_title, Challenge.is_active == True)
    if exclude_id is not None:
        q = q.filter(Challenge.id != exclude_id)
    if q.first():
        raise api_error(409, E_CHALLENGE_TITLE_TAKEN, f"이미 사용 중인 타이틀입니다: '{reward_title}'")


@router.post("")
def create_challenge(
    body: ChallengeCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    _assert_reward_title_unique(db, body.reward_title)
    # 모든 인증된 사용자가 챌린지 생성 가능
    try:
        challenge = Challenge(
            title=body.title,
            description=body.description,
            reward_title=body.reward_title,
            condition_value=body.condition_value,
            goal_description=body.goal_description,
            start_date=body.start_date,
            end_date=body.end_date,
            recruit_start=body.recruit_start,
            recruit_end=body.recruit_end,
            max_participants=body.max_participants,
            categories=body.categories,
            is_active=True,
            creator_id=current_user.id,
        )
        db.add(challenge)
        db.commit()
        db.refresh(challenge)
        logger.info("Challenge created: id=%s title=%r by user_id=%s", challenge.id, challenge.title, current_user.id)
        return {"data": {"challenge": _to_schema(challenge, current_user.id, db)}}
    except SQLAlchemyError as e:
        db.rollback()
        logger.exception("Failed to create challenge for user_id=%s: %s", current_user.id, e)
        raise api_error(500, E_CHALLENGE_CREATE_FAILED, "챌린지 생성에 실패했습니다. 잠시 후 다시 시도해주세요")


@router.post("/{challenge_id}/image")
async def upload_challenge_image(
    challenge_id: int,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not current_user.is_admin:
        raise api_error(403, E_ADMIN_REQUIRED, "관리자만 이미지를 업로드할 수 있습니다")
    challenge = db.get(Challenge, challenge_id)
    if not challenge:
        raise api_error(404, E_CHALLENGE_NOT_FOUND, "챌린지를 찾을 수 없습니다")
    content_type = file.content_type or "image/jpeg"
    if not content_type.startswith("image/"):
        raise api_error(400, E_IMAGE_FORMAT_INVALID, "이미지 파일만 업로드할 수 있습니다")

    raw = await file.read()
    img = Image.open(io.BytesIO(raw)).convert("RGB")

    # 원본 (최대 400×400 정방형 크롭 결과 그대로 저장)
    if img.width > 400 or img.height > 400:
        img = img.resize((400, 400), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=80, optimize=True)
    buf.seek(0)

    # 썸네일 (200×200)
    thumb = img.resize((200, 200), Image.LANCZOS)
    thumb_buf = io.BytesIO()
    thumb.save(thumb_buf, format="JPEG", quality=70, optimize=True)
    thumb_buf.seek(0)

    r2 = r2_service.get_r2_client()
    base_id = uuid.uuid4()
    r2_key = f"challenges/{base_id}.jpg"
    thumb_key = f"challenges/{base_id}_thumb.jpg"

    cache_ctrl = "public, max-age=31536000, immutable"
    r2.put_object(Bucket=app_settings.r2_bucket_name, Key=r2_key, Body=buf, ContentType="image/jpeg", CacheControl=cache_ctrl)
    r2.put_object(Bucket=app_settings.r2_bucket_name, Key=thumb_key, Body=thumb_buf, ContentType="image/jpeg", CacheControl=cache_ctrl)

    image_url = r2_service.get_cdn_url(r2_key)
    image_thumb_url = r2_service.get_cdn_url(thumb_key)
    challenge.image_url = image_url
    challenge.image_thumb_url = image_thumb_url
    db.commit()
    logger.info("Challenge image uploaded: challenge_id=%s url=%s thumb=%s", challenge_id, image_url, image_thumb_url)
    return {"data": {"image_url": image_url, "image_thumb_url": image_thumb_url}}


@router.get("/created")
def my_created_challenges(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    challenges = (
        db.query(Challenge)
        .filter(Challenge.creator_id == current_user.id)
        .order_by(Challenge.created_at.desc())
        .all()
    )
    ids = [c.id for c in challenges]
    participant_counts, my_participations, creator_map = _build_batch_maps(challenges, current_user.id, db)

    completed_counts: dict[int, int] = {}
    if ids:
        rows = (
            db.query(ChallengeParticipation.challenge_id, func.count(ChallengeParticipation.id))
            .filter(
                ChallengeParticipation.challenge_id.in_(ids),
                ChallengeParticipation.completed_at != None,
            )
            .group_by(ChallengeParticipation.challenge_id)
            .all()
        )
        completed_counts = {cid: cnt for cid, cnt in rows}

    result = []
    for c in challenges:
        schema = _to_schema(c, current_user.id, db, participant_counts=participant_counts,
                            my_participations=my_participations, creator_map=creator_map)
        result.append({
            **schema.model_dump(),
            "participant_count": participant_counts.get(c.id, 0),
            "completed_count": completed_counts.get(c.id, 0),
        })
    return {"data": {"challenges": result}}


@router.get("/my")
def my_challenges(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    participations = (
        db.query(ChallengeParticipation)
        .filter(ChallengeParticipation.user_id == current_user.id)
        .options(selectinload(ChallengeParticipation.challenge))
        .order_by(ChallengeParticipation.joined_at.desc())
        .all()
    )
    challenges = [p.challenge for p in participations]
    participant_counts, my_participations, creator_map = _build_batch_maps(challenges, current_user.id, db)
    result = [
        _to_schema(p.challenge, current_user.id, db, participant_counts=participant_counts,
                   my_participations=my_participations, creator_map=creator_map)
        for p in participations
    ]
    return {"data": {"challenges": result}}


@router.get("/titles")
def my_titles(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    completed = (
        db.query(ChallengeParticipation)
        .filter(
            ChallengeParticipation.user_id == current_user.id,
            ChallengeParticipation.completed_at != None,
        )
        .order_by(ChallengeParticipation.completed_at.desc())
        .all()
    )
    titles = [
        EarnedTitleSchema(
            title=p.challenge.reward_title,
            challenge_title=p.challenge.title,
            completed_at=p.completed_at,
        )
        for p in completed
    ]
    return {"data": {"titles": titles}}


@router.delete("/{challenge_id}/leave")
def leave_challenge(
    challenge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    participation = (
        db.query(ChallengeParticipation)
        .filter(
            ChallengeParticipation.challenge_id == challenge_id,
            ChallengeParticipation.user_id == current_user.id,
        )
        .first()
    )
    if not participation:
        raise api_error(404, E_CHALLENGE_NOT_PARTICIPATING, "참여 중인 챌린지가 아닙니다")
    if participation.completed_at is not None:
        raise api_error(400, E_CHALLENGE_ALREADY_COMPLETED, "이미 완료한 챌린지는 취소할 수 없습니다")
    db.delete(participation)
    db.commit()
    logger.info("Challenge left: challenge_id=%s user_id=%s", challenge_id, current_user.id)
    return {"data": {"left": True, "challenge_id": challenge_id}}


@router.post("/{challenge_id}/join")
def join_challenge(
    challenge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise api_error(404, E_CHALLENGE_NOT_FOUND, "챌린지를 찾을 수 없습니다")
    if not challenge.is_active:
        raise api_error(400, E_CHALLENGE_ENDED, "이미 종료된 챌린지입니다")

    now = datetime.now(timezone.utc)
    recruit_end = challenge.recruit_end
    if recruit_end:
        if recruit_end.tzinfo is None:
            recruit_end = recruit_end.replace(tzinfo=timezone.utc)
        if now > recruit_end:
            raise api_error(400, E_CHALLENGE_CLOSED, "모집이 마감된 챌린지입니다")

    if challenge.max_participants is not None:
        count = (
            db.query(func.count(ChallengeParticipation.id))
            .filter(ChallengeParticipation.challenge_id == challenge_id)
            .scalar()
        ) or 0
        if count >= challenge.max_participants:
            raise api_error(400, E_CHALLENGE_FULL, "모집 인원이 가득 찼습니다")

    existing = (
        db.query(ChallengeParticipation)
        .filter(
            ChallengeParticipation.challenge_id == challenge_id,
            ChallengeParticipation.user_id == current_user.id,
        )
        .first()
    )
    if existing:
        raise api_error(409, E_CHALLENGE_ALREADY_JOINED, "이미 참여 중인 챌린지입니다")

    participation = ChallengeParticipation(
        user_id=current_user.id,
        challenge_id=challenge_id,
        upload_count=0,
    )
    db.add(participation)
    db.commit()
    db.refresh(participation)
    return {"data": {"joined": True, "challenge_id": challenge_id}}


@router.get("/{challenge_id}/participants")
def challenge_participants(
    challenge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise api_error(404, E_CHALLENGE_NOT_FOUND, "챌린지를 찾을 수 없습니다")
    if challenge.creator_id != current_user.id:
        raise api_error(403, E_CHALLENGE_OWNER_REQUIRED, "챌린지 생성자만 접근할 수 있습니다")
    participations = (
        db.query(ChallengeParticipation)
        .filter(ChallengeParticipation.challenge_id == challenge_id)
        .options(selectinload(ChallengeParticipation.user))
        .order_by(
            ChallengeParticipation.completed_at.desc().nulls_last(),
            ChallengeParticipation.upload_count.desc(),
        )
        .all()
    )
    # 챌린지 기간 내 실제 인증 포스트 수 배치 조회
    participant_ids = [p.user_id for p in participations]
    post_counts: dict[int, int] = {}
    if participant_ids:
        rows = (
            db.query(Post.user_id, func.count(Post.id))
            .join(Post.video)
            .filter(
                Post.user_id.in_(participant_ids),
                Post.challenge_id == challenge_id,
                Post.created_at >= challenge.start_date,
                Post.created_at <= challenge.end_date,
                Video.status == "active",
            )
            .group_by(Post.user_id)
            .all()
        )
        post_counts = {uid: cnt for uid, cnt in rows}

    result = []
    for p in participations:
        user = p.user
        progress = (
            min(100, round((p.upload_count / challenge.condition_value) * 100))
            if challenge.condition_value > 0
            else 0
        )
        result.append({
            "user_id": p.user_id,
            "username": user.username if user else "",
            "upload_count": p.upload_count,
            "post_count": post_counts.get(p.user_id, 0),
            "condition_value": challenge.condition_value,
            "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            "joined_at": p.joined_at.isoformat(),
            "progress": progress,
        })
    return {
        "data": {
            "challenge": _to_schema(challenge, current_user.id, db).model_dump(),
            "participants": result,
        }
    }


@router.get("/{challenge_id}/videos")
def challenge_videos(
    challenge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise api_error(404, E_CHALLENGE_NOT_FOUND, "챌린지를 찾을 수 없습니다")
    if challenge.creator_id != current_user.id and not current_user.is_admin:
        raise api_error(403, E_CHALLENGE_OWNER_REQUIRED, "챌린지 생성자만 접근할 수 있습니다")

    posts = (
        db.query(Post)
        .filter(Post.challenge_id == challenge_id)
        .options(
            selectinload(Post.user),
            selectinload(Post.video),
        )
        .order_by(Post.created_at.desc())
        .all()
    )

    result = []
    for post in posts:
        u = post.user
        v = post.video
        result.append({
            "post_id": post.id,
            "user_id": post.user_id,
            "username": u.username if u else "",
            "avatar_url": u.avatar_url if u else None,
            "cdn_url": v.cdn_url if v else "",
            "thumbnail_url": post.thumbnail_url,
            "caption": post.caption,
            "created_at": post.created_at.isoformat(),
        })

    return {"data": {"videos": result}}


@router.patch("/{challenge_id}/participants/{user_id}/complete")
def toggle_participant_complete(
    challenge_id: int,
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise api_error(404, E_CHALLENGE_NOT_FOUND, "챌린지를 찾을 수 없습니다")
    if challenge.creator_id != current_user.id and not current_user.is_admin:
        raise api_error(403, E_MANAGER_REQUIRED, "매니저만 완료 처리할 수 있습니다")

    participation = (
        db.query(ChallengeParticipation)
        .filter(
            ChallengeParticipation.challenge_id == challenge_id,
            ChallengeParticipation.user_id == user_id,
        )
        .first()
    )
    if not participation:
        raise api_error(404, E_PARTICIPATION_NOT_FOUND, "참여 정보를 찾을 수 없습니다")

    if participation.completed_at is None:
        participation.completed_at = datetime.now(timezone.utc)
    else:
        participation.completed_at = None

    db.commit()
    return {"data": {"user_id": user_id, "completed_at": participation.completed_at.isoformat() if participation.completed_at else None}}


@router.get("/{challenge_id}")
def get_challenge(
    challenge_id: int,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> dict:
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise api_error(404, E_CHALLENGE_NOT_FOUND, "챌린지를 찾을 수 없습니다")
    uid = current_user.id if current_user else None
    return {"data": {"challenge": _to_schema(challenge, uid, db)}}


@router.patch("/{challenge_id}")
def update_challenge(
    challenge_id: int,
    body: ChallengeUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise api_error(404, E_CHALLENGE_NOT_FOUND, "챌린지를 찾을 수 없습니다")
    if challenge.creator_id != current_user.id and not current_user.is_admin:
        raise api_error(403, E_FORBIDDEN, "수정 권한이 없습니다")
    if body.title is not None:
        challenge.title = body.title
    if body.description is not None:
        challenge.description = body.description
    if body.reward_title is not None:
        _assert_reward_title_unique(db, body.reward_title, exclude_id=challenge_id)
        challenge.reward_title = body.reward_title
    if body.condition_value is not None:
        challenge.condition_value = body.condition_value
    if body.start_date is not None:
        challenge.start_date = body.start_date
    if body.end_date is not None:
        challenge.end_date = body.end_date
    if body.categories is not None:
        challenge.categories = body.categories
    if body.goal_description is not None:
        challenge.goal_description = body.goal_description
    if body.recruit_start is not None:
        challenge.recruit_start = body.recruit_start
    if body.recruit_end is not None:
        challenge.recruit_end = body.recruit_end
    if body.max_participants is not None:
        challenge.max_participants = body.max_participants
    db.commit()
    db.refresh(challenge)
    uid = current_user.id
    return {"data": {"challenge": _to_schema(challenge, uid, db)}}


@router.patch("/{challenge_id}/close")
def close_challenge(
    challenge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise api_error(404, E_CHALLENGE_NOT_FOUND, "챌린지를 찾을 수 없습니다")
    if challenge.creator_id != current_user.id and not current_user.is_admin:
        raise api_error(403, E_FORBIDDEN, "종료 권한이 없습니다")
    if not challenge.is_active:
        raise api_error(400, "ALREADY_CLOSED", "이미 종료된 챌린지입니다")
    challenge.is_active = False
    db.commit()
    logger.info("Challenge closed: id=%s by user_id=%s", challenge_id, current_user.id)
    return {"data": {"closed": True}}


@router.delete("/{challenge_id}")
def delete_challenge(
    challenge_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge:
        raise api_error(404, E_CHALLENGE_NOT_FOUND, "챌린지를 찾을 수 없습니다")
    if challenge.creator_id != current_user.id and not current_user.is_admin:
        raise api_error(403, E_FORBIDDEN, "삭제 권한이 없습니다")
    if challenge.is_active and not current_user.is_admin:
        raise api_error(400, "CHALLENGE_STILL_ACTIVE", "진행 중인 챌린지는 삭제할 수 없습니다. 먼저 종료해 주세요.")
    db.query(ChallengeParticipation).filter(ChallengeParticipation.challenge_id == challenge_id).delete()
    db.delete(challenge)
    db.commit()
    logger.info("Challenge permanently deleted: id=%s by user_id=%s", challenge_id, current_user.id)
    return {"data": {"deleted": True}}


def increment_challenge_upload(db: Session, user_id: int, challenge_id: int) -> None:
    participation = (
        db.query(ChallengeParticipation)
        .filter(
            ChallengeParticipation.challenge_id == challenge_id,
            ChallengeParticipation.user_id == user_id,
        )
        .first()
    )
    if not participation:
        raise api_error(400, E_CHALLENGE_NOT_JOINED, "먼저 챌린지에 참여해주세요")

    challenge = db.query(Challenge).filter(Challenge.id == challenge_id).first()
    if not challenge or not challenge.is_active:
        raise api_error(400, E_CHALLENGE_INVALID, "유효하지 않은 챌린지입니다")

    participation.upload_count += 1
