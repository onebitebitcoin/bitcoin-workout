# Bitcoiners 에러 코드 정의

> 에러 코드 관련 문의 시 이 파일을 먼저 참고한다.
> 코드 소스: `backend/app/services/error_codes.py`
> 프론트엔드 처리: `frontend/src/api/errors.ts`
> 사용자에게 표시 형식: `"사용자 메시지 [E_XXX]"`

## 인증 (Auth)

| 코드 | HTTP | 사용자 메시지 | 발생 상황 |
|------|------|--------------|-----------|
| `E_AUTH_REQUIRED` | 401 | 인증이 필요합니다 | 로그인 없이 인증 필요 엔드포인트 접근 |
| `E_AUTH_INVALID_TOKEN` | 401 | 유효하지 않은 토큰입니다 | JWT 만료·변조 |
| `E_AUTH_INVALID_CREDENTIALS` | 401 | 이메일 또는 비밀번호가 올바르지 않습니다 | 이메일 로그인 실패 |
| `E_AUTH_EMAIL_TAKEN` | 400 | 이미 사용 중인 이메일입니다 | 회원가입 시 이메일 중복 |
| `E_AUTH_USERNAME_TAKEN` | 400 | 이미 사용 중인 닉네임입니다 | 회원가입·프로필 수정 시 닉네임 중복 |
| `E_GOOGLE_AUTH_UNAVAILABLE` | 503 | Google 로그인을 현재 사용할 수 없습니다 | Google OAuth 미설정 환경 |

## 권한 (Permission)

| 코드 | HTTP | 사용자 메시지 | 발생 상황 |
|------|------|--------------|-----------|
| `E_FORBIDDEN` | 403 | 이 작업을 수행할 권한이 없습니다 | 타인의 리소스 수정·삭제 시도 |
| `E_BANNED` | 403 | 계정이 정지된 상태입니다 | 정지된 계정으로 글쓰기·댓글 시도 |
| `E_ADMIN_REQUIRED` | 403 | 관리자 권한이 필요합니다 | 관리자 전용 기능 접근 |
| `E_MANAGER_REQUIRED` | 403 | 매니저만 완료 처리할 수 있습니다 | 챌린지 완료 처리 권한 없음 |
| `E_CHALLENGE_OWNER_REQUIRED` | 403 | 챌린지 생성자만 접근할 수 있습니다 | 챌린지 수정·관리 권한 없음 |

## 리소스 없음 (Not Found)

| 코드 | HTTP | 사용자 메시지 | 발생 상황 |
|------|------|--------------|-----------|
| `E_USER_NOT_FOUND` | 404 | 사용자를 찾을 수 없습니다 | 존재하지 않는 사용자 조회 |
| `E_POST_NOT_FOUND` | 404 | 게시물을 찾을 수 없습니다 | 삭제되거나 없는 게시물 접근 |
| `E_VIDEO_NOT_FOUND` | 404 | 영상을 찾을 수 없습니다 | 삭제되거나 없는 영상 접근 |
| `E_COMMENT_NOT_FOUND` | 404 | 댓글을 찾을 수 없습니다 | 삭제되거나 없는 댓글 접근 |
| `E_CHALLENGE_NOT_FOUND` | 404 | 챌린지를 찾을 수 없습니다 | 삭제되거나 없는 챌린지 접근 |
| `E_JOB_NOT_FOUND` | 404 | 요청한 작업을 찾을 수 없습니다 | 만료되거나 없는 업로드 잡 조회 |
| `E_PARTICIPATION_NOT_FOUND` | 404 | 참여 정보를 찾을 수 없습니다 | 참여 기록 없는 챌린지 작업 시도 |
| `E_CHALLENGE_NOT_PARTICIPATING` | 404 | 참여 중인 챌린지가 아닙니다 | 미참여 챌린지에 업로드 시도 |

## 영상·업로드 (Video / Upload)

| 코드 | HTTP | 사용자 메시지 | 발생 상황 |
|------|------|--------------|-----------|
| `E_VIDEO_DURATION_INVALID` | 400 | 영상은 10~60초여야 합니다 | 업로드 영상 길이 범위 초과 |
| `E_VIDEO_FORMAT_INVALID` | 400 | 지원하지 않는 파일 형식입니다 | 허용되지 않는 비디오 MIME 타입 |
| `E_VIDEO_TOO_LARGE` | 400 | 파일이 너무 큽니다 (최대 100MB) | 영상 파일 100MB 초과 |
| `E_AUDIO_DURATION_INVALID` | 400 | 오디오 길이를 확인해주세요 | 녹음 오디오 길이 오류 |
| `E_AUDIO_UPLOAD_FAILED` | 500 | 오디오 업로드에 실패했습니다 | 오디오 R2 업로드 오류 |
| `E_UPLOAD_URL_FAILED` | 500 | 업로드를 시작할 수 없습니다 | presigned URL 생성 실패 |
| `E_VIDEO_PROCESS_FAILED` | 500 | 영상 처리 중 오류가 발생했습니다 | 워커 파이프라인 실패 |
| `E_QUEUE_FAILED` | 500 | 영상 처리 요청에 실패했습니다 | Redis 큐 등록 실패 |

## 이미지·파일 (Image / File)

| 코드 | HTTP | 사용자 메시지 | 발생 상황 |
|------|------|--------------|-----------|
| `E_IMAGE_FORMAT_INVALID` | 400 | 이미지 파일만 업로드할 수 있습니다 | 허용되지 않는 이미지 MIME 타입 |
| `E_IMAGE_TOO_LARGE` | 400 | 이미지가 너무 큽니다 (최대 10MB) | 이미지 파일 10MB 초과 |
| `E_IMAGE_UPLOAD_FAILED` | 500 | 이미지 업로드에 실패했습니다 | 이미지 R2 업로드 오류 |
| `E_FILE_TOO_LARGE` | 400 | 파일이 너무 큽니다 | 기타 파일 크기 초과 |

## 댓글 (Comment)

| 코드 | HTTP | 사용자 메시지 | 발생 상황 |
|------|------|--------------|-----------|
| `E_COMMENT_TOO_SHORT` | 422 | 댓글은 5자 이상 입력해주세요 | 5자 미만 댓글 작성 시도 |
| `E_COMMENT_TOO_LONG` | 422 | 댓글은 500자 이하로 입력해주세요 | 500자 초과 댓글 작성 시도 |
| `E_COMMENT_DAILY_LIMIT` | 429 | 하루에 댓글은 10개까지 작성할 수 있습니다 | 하루 10개 댓글 한도 초과 |

## 챌린지 (Challenge)

| 코드 | HTTP | 사용자 메시지 | 발생 상황 |
|------|------|--------------|-----------|
| `E_CHALLENGE_FULL` | 400 | 모집 인원이 가득 찼습니다 | 정원 초과 챌린지 참여 시도 |
| `E_CHALLENGE_CLOSED` | 400 | 모집이 마감된 챌린지입니다 | 마감된 챌린지 참여 시도 |
| `E_CHALLENGE_ENDED` | 400 | 이미 종료된 챌린지입니다 | 종료된 챌린지 작업 시도 |
| `E_CHALLENGE_EXPIRED` | 400 | 챌린지가 만료되었습니다 | 만료 후 챌린지 작업 시도 |
| `E_CHALLENGE_INVALID` | 400 | 유효하지 않은 챌린지입니다 | 비활성·삭제 챌린지 접근 |
| `E_CHALLENGE_NOT_JOINED` | 400 | 먼저 챌린지에 참여해주세요 | 미참여 상태로 챌린지 업로드 시도 |
| `E_CHALLENGE_ALREADY_JOINED` | 409 | 이미 참여 중인 챌린지입니다 | 중복 챌린지 참여 시도 |
| `E_CHALLENGE_ALREADY_COMPLETED` | 400 | 이미 완료한 챌린지는 취소할 수 없습니다 | 완료 후 참여 취소 시도 |
| `E_CHALLENGE_TITLE_TAKEN` | 409 | 이미 사용 중인 타이틀입니다 | 챌린지 타이틀 중복 |
| `E_CHALLENGE_CREATE_FAILED` | 500 | 챌린지 생성에 실패했습니다 | 챌린지 생성 중 서버 오류 |

## 관리자 전용 (Admin)

| 코드 | HTTP | 사용자 메시지 | 발생 상황 |
|------|------|--------------|-----------|
| `E_ADMIN_SELF_DELETE` | 400 | 자신의 계정은 삭제할 수 없습니다 | 관리자가 본인 계정 삭제 시도 |
| `E_ADMIN_API_KEY_DELETE` | 400 | API 키로는 관리자 계정을 삭제할 수 없습니다 | API 키로 관리자 삭제 시도 |
