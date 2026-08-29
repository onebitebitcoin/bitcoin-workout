/**
 * 업로드 메인 카테고리 — 단일 소스.
 *
 * Orange Story는 "비트코인" 활동(공부·결제·노드·모임 등)과 그 밖의 "일상"
 * 두 축으로만 기록을 나눈다.
 *
 * DB(posts.tags[0], challenges.categories)에는 이 한글 원본 문자열이 그대로 저장된다.
 * 값을 바꾸면 별도 alembic 데이터 마이그레이션이 필요하다.
 */
export const MAIN_CATEGORIES = ['비트코인', '일상'] as const
export type MainCategory = typeof MAIN_CATEGORIES[number]

/** 카테고리 값 → i18n 키(upload 네임스페이스의 `tagChallenge.` 접두사 제외). */
export const MAIN_CATEGORY_LABEL_KEYS: Record<MainCategory, string> = {
  '비트코인': 'categoryBitcoin',
  '일상': 'categoryDaily',
}
