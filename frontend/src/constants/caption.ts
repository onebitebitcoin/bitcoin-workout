/**
 * 게시물 설명(caption) 글자수 상한 — 단일 소스.
 *
 * 백엔드 `app/schemas/video.py`의 `CAPTION_MAX_LEN`과 같은 값을 유지해야 한다.
 * DB 컬럼은 text 라 길이 제한이 없고, 이 값만이 유일한 상한이다.
 */
export const CAPTION_MAX_LEN = 2200

/**
 * og:description 에 넣을 설명의 최대 길이.
 * 본문 상한(2200자)을 그대로 메타 태그에 넣으면 크롤러가 임의로 자르거나 무시한다.
 */
export const OG_DESCRIPTION_MAX_LEN = 200
