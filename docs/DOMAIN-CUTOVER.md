# 도메인 전환 런북 — stackhealth.life → bitcoiners.life

> Bitcoiners 리브랜딩의 코드 작업은 끝났다. `frontend/index.html`(canonical, OG, JSON-LD), `frontend/public/sitemap.xml`, `frontend/public/robots.txt`는 이미 `bitcoiners.life` 기준으로 갱신돼 있다. 남은 건 서버에서 직접 실행해야 하는 인프라 전환뿐이고, 이 문서가 그 절차다.
>
> 이 문서는 서버 SSH 접속 후 사용자가 직접 실행하는 절차서다. Claude는 이 문서 작성 과정에서 서버에 접속하지 않았고 실제 인프라도 건드리지 않았다 — 아래 명령은 전부 리포지토리 파일(`CLAUDE.md`, `scripts/deploy.sh`, `backend/app/config.py` 등)을 근거로 작성했고, 리포지토리에 없어 서버에서만 확인 가능한 부분은 **확인 필요**로 표시했다.

## 0. 전제 — 왜 순서가 중요한가

인증서 없이 DNS부터 돌리면 그 사이 `https://bitcoiners.life`는 브라우저 경고를 띄운다. nginx가 새 도메인을 받기 전에 301을 걸면 기존 `stackhealth.life` 트래픽이 그대로 끊긴다. 환경변수를 코드 배포보다 먼저 바꾸면 서버가 재시작되기 전까지 예전 도메인 기준으로 리다이렉트가 나간다. 그래서 아래 순서를 지킨다: `DNS 추가` → `인증서 발급` → `nginx 양쪽 허용` → `검증` → `301 전환` → `환경변수 갱신 및 재배포`.

## 1. 사전 확인

### 1-1. 기존 영상(R2 CDN)은 이 작업과 무관하다

`backend/app/services/r2.py`의 `get_cdn_url()`은 `settings.r2_public_url`(`R2_PUBLIC_URL`, 예: `https://<bucket>.r2.dev`)을 그대로 붙여 URL을 만든다. 이 값은 Cloudflare R2 버킷의 퍼블릭 도메인이지, 웹 서비스 도메인(`stackhealth.life`/`bitcoiners.life`)과는 완전히 별개다. 웹 도메인을 바꿔도 이미 올라간 영상·썸네일 링크(`R2_PUBLIC_URL` 기준)는 그대로 살아있다 — 영상이 끊길까 걱정할 필요는 없다. R2 버킷명·CDN URL은 이번 작업에서 손댈 항목이 아니다(5장 참조).

### 1-2. Cloudflare가 앞단에 있다 — DNS 추가 시 프록시 상태를 맞춰라

git 히스토리(`04690e2`, `0c8e267` 커밋 — "Cloudflare 521 개선")에 따르면 `stackhealth.life`는 Cloudflare를 경유한다(521은 Cloudflare 고유 에러 코드로, 프록시가 아니면 발생하지 않는다). `bitcoiners.life` A 레코드를 추가할 때 기존 `stackhealth.life` 레코드와 같은 프록시 상태(오렌지 클라우드 on/off)로 맞춰야 한다. **확인 필요**: 정확한 SSL/TLS 모드(Flexible/Full/Full strict)는 Cloudflare 대시보드에서 `stackhealth.life` 존 설정을 직접 확인해야 한다.

### 1-3. 실제 서버 설정 파일 위치를 먼저 특정한다

- 운영 환경변수 파일: 리포지토리 루트의 `.env` (`.gitignore`에 등록돼 git 추적 대상이 아니다). `backend/app/config.py`의 `model_config = SettingsConfigDict(env_file="../.env", ...)`가 이 파일을 읽는다. **확인 필요**: 서버의 실제 `.env` 값은 이 문서 작성 시점에 확인할 수 없었다. 아래 표의 키가 현재 어떤 값인지는 서버에서 직접 `cat .env`로 확인한다.
- nginx upstream 파일(포트 전환용): `/etc/nginx/conf.d/stackhealth-upstream.conf`. 이건 blue/green 포트(8017/8018)만 정의하는 파일이라 도메인 전환과는 별개다. 리포지토리의 `nginx/upstream.conf`는 `deploy.sh`가 배포마다 덮어쓰는 참조용 사본이며 git에는 커밋되지 않는다(gitignore 처리, 커밋 `eebf1c1`).
- nginx 서버 블록(server_name, ssl_certificate 경로가 있는 실제 사이트 설정 파일)은 리포지토리 어디에도 없다 — upstream.conf와는 다른 파일이고, 순수하게 서버에만 존재한다. **확인 필요**: 서버에서 아래로 먼저 찾는다.
  ```bash
  sudo grep -rl "stackhealth.life" /etc/nginx/sites-available/ /etc/nginx/conf.d/ 2>/dev/null
  ```
- 인증서 발급 방식(certbot Let's Encrypt인지 Cloudflare Origin CA 인증서인지)도 리포지토리에 기록이 없다. **확인 필요**:
  ```bash
  sudo certbot certificates
  ```
  이 명령 결과에 `stackhealth.life`가 나오면 certbot 관리 대상이니 아래 2-2의 certbot 절차를 그대로 쓴다. 안 나오면 Cloudflare Origin CA 인증서를 수동 발급해 넣은 구성이므로 절차가 달라진다 — 그 경우 진행 전에 재확인한다.
- Google Cloud Console 프로젝트 접근 권한(OAuth 클라이언트 수정 권한)이 있는 계정으로 로그인 가능한지 미리 확인한다. 3장에서 필요하다.

### 1-4. 다음 배포가 밟게 될 위험 — 파괴적 마이그레이션과 blue-green 창

이 항목은 `scripts/deploy.sh` 자체가 안고 있는 위험이라 도메인 전환 여부와 무관하게 다음 `git push`에서 그대로 발생한다. 2장 Step 6("환경변수 갱신 후 재배포")에서 이 스크립트를 실행하는 순간 아래 상황을 그대로 밟게 되므로, 실행 전에 읽어둔다.

**배포 시퀀스와 문제 지점**

```
[3/8] 프론트엔드 빌드                                        (78~82행)
[4/8] alembic upgrade head                                  (86행)  ← reward_points DROP + 카테고리 리맵
[5/8] NEXT_SLOT 기동 (새 코드)                                (89~91행)
[6/8] 헬스체크, 최대 60초                                     (93~119행)
[7/8] nginx 전환 → NEXT_SLOT, 5초 대기 후 CURRENT_SLOT 종료    (121~151행)
```

두 슬롯은 같은 PostgreSQL DB를 본다(`CLAUDE.md` 배포 인프라 섹션). 4단계에서 스키마가 바뀌고 나서 7단계에서 구 슬롯이 완전히 죽을 때까지, `CURRENT_SLOT`은 여전히 nginx가 트래픽을 흘려보내는 대상이다 — 재시작되는 건 다음 슬롯뿐이다.

현재 운영(`origin/main`, 커밋 `dfb2fdd` / v0.19.1)에서 도는 코드는 포인트(땀방울) 체계가 살아 있는 버전이다. 로컬 `main`은 이미 그 위에 `851b043`(포인트 체계 제거, `reward_points` 테이블을 내리는 마이그레이션 `c7d8e9f0a1b2` 포함)을 얹어 origin보다 1커밋 앞서 있고, 카테고리 리맵 마이그레이션(`004aa221ea8d`)은 아직 커밋되지 않은 채 워킹 디렉터리에 남아 있다. 다음 push는 이 두 마이그레이션을 한 번에 운영으로 실어 나른다. 이 문서를 쓰는 시점 기준으로는 아직 일어나지 않았지만, 재배포하는 순간 그대로 재현된다.

**구 슬롯에서 실제로 깨지는 지점**

아래는 전부 `git show dfb2fdd:<파일>`로 구 코드를 직접 읽고 확인한 경로다. `reward_points`가 사라진 순간부터 구 슬롯이 죽기 전까지, 이 경로들이 그 테이블을 조회하거나 쓴다.

| 경로 | 위치 (`dfb2fdd` 기준) | 사용자에게 보이는 증상 |
|---|---|---|
| `POST /api/v1/videos/confirm` (비가공 업로드 확정) | `routes/videos.py:215` | `add_points()`가 `db.commit()` 전에 실행되다 INSERT가 실패한다. 방금 만든 `Video`/`Post` row는 커밋되지 않고 롤백되며 요청은 500으로 끝난다. 사용자는 R2에 파일을 이미 올려놓고도 게시물이 생기지 않아 처음부터 다시 시도해야 한다 |
| `POST /api/v1/videos/upload-pipeline`, `/upload-multi` (워커 처리 경로) | `worker/tasks/full_pipeline.py:534`, `full_pipeline_multi.py:364` | 압축·카툰 필터·근육 히트맵 오버레이·오디오 머지·자막 번인까지, UI가 "최대 3분"이라 안내하는 처리 전 과정이 다 끝난 뒤 마지막 DB 저장 단계에서 이 INSERT가 실패한다. 예외 핸들러가 R2의 압축 파일은 정리해주지만 그대로 재-raise해 잡은 "failed"로 남는다. 사용자는 긴 처리 시간을 다 기다리고 "영상 처리에 실패했습니다. 다시 시도해주세요"만 본다 — 결과물은 아무것도 남지 않는다 |
| `PATCH /api/v1/videos/posts/{post_id}` (메인 카테고리 수정 시에만) | `routes/videos.py:478-506` | 캡션·시간·서브태그 수정은 영향이 없다. 메인 카테고리(`tags[0]`)를 바꿀 때만 `RewardPoint`를 조회하러 가서 거기서 500이 난다 |
| `POST /api/v1/feed/{post_id}/comments` | `routes/comments.py:140` | 댓글 insert 후 `add_points`가 실패해 코멘트 자체가 롤백된다. 댓글이 달리지 않는다 |
| `DELETE /api/v1/feed/{post_id}/comments/{comment_id}` | `routes/comments.py:170-186` | 삭제 전에 `RewardPoint`를 조회하므로 본인 댓글도 지울 수 없다 |
| `GET /api/v1/rewards/summary` | `routes/rewards.py:23-29` | 첫 줄부터 `settle_queued_rewards()`가 테이블을 찾다 500 |
| `GET /api/v1/users/me/hashrate`(104행), `/me/stats`(121행), `/me/weekly-points`(177행), `/me/monthly-points`(244행), `/leaderboard`(273행) | `routes/users.py` | 전부 `RewardPoint` 합계·조인 쿼리라 500. `/me/stats`는 응답 자체가 실패하는 것과 별개로, 응답 뒤 도는 백그라운드 정산(`_settle_rewards_background`)도 서버 로그에 예외를 남긴다 |
| 관리자 `PATCH /admin/videos/{id}/reject`(121행), `DELETE /admin/videos/{id}`(138행), `GET /admin/hashrate*`(467행), `/admin/weekly-summary`(570행) | `routes/admin.py` | 영상 반려·삭제도 내부적으로 `revoke_queued_upload_reward()`를 거치므로, 이 구간에는 관리자가 신고된 영상을 반려·삭제하지도 못한다 |
| `DELETE /admin/users/{id}` | `routes/admin.py:325` | 삭제 캐스케이드 중간에 `RewardPoint` 삭제가 끼어 있다. 한 트랜잭션이라 실패하면 전체가 롤백돼 부분 삭제는 남지 않지만, 이 구간에는 사용자 삭제 자체가 안 된다 |
| 시간당 백그라운드 정산 루프 | `main.py:_settle_rewards_loop` (68-83행) | 예외를 잡아 롤백하고 로그만 남긴 뒤 계속 도는 구조라 크래시로 번지지 않는다. 이 구간에는 매시간 에러 로그 한 줄이 쌓일 뿐이다 — 목록 중 유일하게 사용자에게 노출되지 않는 항목 |

카테고리 리맵(`004aa221ea8d`)이 따로 만드는 증상은 하나뿐이고, 그마저도 크래시는 아니다. 프론트엔드는 4단계 전에 이미 새 빌드(6종 카테고리)로 교체돼 있어 신규 페이지 로드에는 영향이 없다. 다만 배포 전부터 열려 있던 브라우저 탭은 구 프론트엔드 번들을 그대로 실행 중인데, `frontend/src/pages/upload/StepMeta.tsx:9`의 `MAIN_CATEGORIES = ['가벼운 활동', '땀 흘리는 운동']` 하드코딩 목록이 그 안에 살아있다. 리맵 후 `post.tags[0]`은 `'일상'`이나 `'스택헬스'`가 되어 이 목록에 더는 없으므로, `PostEditPage.tsx:46`의 `includes(tags[0]) ? tags[0] : null` 판정이 `null`로 떨어진다. 그 탭에서 게시물 수정 화면을 열면 메인 카테고리 선택이 조용히 풀려서 보이는 정도다. 저장을 누르면 위 표의 `PATCH .../posts/{id}` 경로를 타고 결국 500으로 끝나고, 새로고침하면 사라지는 증상이라 영향은 작다.

**창의 길이**

스크립트만 놓고 보면 하한은 4단계에서 DROP 문이 실행되는 순간이고, 상한은 7단계에서 `sleep 5` 뒤 `CURRENT_SLOT`이 죽는 순간이다. 그 사이에 세 구간이 순서대로 더해진다: 카테고리 리맵이 `posts`/`challenges`를 행 단위 Python 루프로 순회하며 UPDATE하는 나머지 시간(개별 UPDATE를 반복하는 구조라 DROP 자체보다 오래 걸릴 수 있다), 5단계에서 mediapipe·OpenCV 같은 무거운 의존성을 새 프로세스가 다시 로드하는 재시작 시간, 6단계의 헬스체크 대기(2초 간격, 최대 60초). 여기에 7단계의 고정 5초가 붙는다. **확인 필요**: 정확한 초 단위 값은 운영 DB의 `posts` 행 수와 서버 자원에 따라 달라져 리포지토리만으로는 알 수 없다 — 실제 배포 로그에서 [4/8] 시작부터 [7/8]의 "이전 슬롯 종료" 줄까지 타임스탬프 차이를 재보는 쪽이 정확하다. 최선의 경우에도 수십 초, 리맵 대상 데이터가 많거나 새 프로세스 기동이 느리면 1분을 넘길 수 있는 구간으로 봐야 한다.

**완화 방안 — 무엇을 고를지는 결정할 사람의 몫이다**

네 가지를 검토했다. 나열 순서에 우선순위는 없다.

- **A. 저트래픽 시간대에 배포하고 위험을 감수한다**: 새벽 등 실사용자가 적은 시간(KST 기준)에 `bash scripts/deploy.sh`를 돌린다. 스크립트 변경이 필요 없어 지금 바로 쓸 수 있지만, 창을 없애지는 못하고 확률만 낮춘다. 그 시간에 마침 업로드 중이거나 댓글을 쓰던 사용자는 위 표의 증상을 그대로 겪는다.
- **B. 배포를 2단계로 쪼갠다 — 코드 먼저, DROP은 나중에**: 이번 push에서는 `c7d8e9f0a1b2`/`004aa221ea8d` 두 마이그레이션을 빼고 코드만(포인트 UI·라우트 제거분 포함) 올려 양쪽 슬롯이 전부 새 코드로 넘어가게 한 뒤, 별도 배포에서 마이그레이션만 실행한다. 어느 순간에도 "포인트를 참조하는 코드"와 "포인트 테이블이 없는 스키마"가 함께 있지 않게 된다. 대신 배포를 두 번 나눠 실행해야 하고, 이번처럼 코드 삭제와 마이그레이션이 이미 한 커밋(`851b043`)에 같이 들어간 경우 커밋을 다시 쪼개는 작업이 먼저 필요하다.
- **C. DROP 대신 rename — 다만 이것만으로는 창을 없애지 못한다**: `op.drop_table('reward_points')`를 `op.rename_table('reward_points', 'reward_points_deprecated')`로 바꾸고, 진짜 DROP은 몇 배포 뒤 구 코드가 완전히 사라졌다고 확신할 때 별도로 실행한다. rename도 그 순간 `reward_points`라는 이름의 테이블을 없애는 건 DROP과 같아서, 구 슬롯이 이 이름으로 쿼리하는 한 위 표의 에러는 그대로 재현된다. 이 방법의 실질적인 이점은 데이터를 되돌릴 여지를 남긴다는 데 있다 — B와 묶어 "코드 배포 → 검증 → rename → 검증 → 진짜 DROP" 순서로 쓸 때 의미가 생긴다.
- **D. 마이그레이션 실행 순서를 7단계 뒤로 옮긴다 (구조적 해결, 스크립트 수정 필요)**: `scripts/deploy.sh`의 4단계를 7단계(구 슬롯 종료) 뒤로 옮긴다. 신규 코드는 애초에 `reward_points`를 참조하지 않으니 새 슬롯이 옛 스키마 위에서 먼저 뜨는 건 문제가 안 된다 — 문제는 항상 "구 코드가 새 스키마를 보는" 조합이었다. B처럼 커밋을 쪼갤 필요 없이 순서 변경만으로 창을 구조적으로 없애지만, `scripts/deploy.sh` 자체를 고쳐야 하고(이 문서 작성 범위 밖이라 이번에는 손대지 않았다), 새 코드가 신규 컬럼 추가처럼 스키마 확장에 의존하는 경우엔 이 순서가 거꾸로 문제를 만들 수 있어 케이스마다 재검토가 필요하다.

이번처럼 코드 삭제와 DROP이 한 커밋에 이미 묶인 상황에는 D가 창 자체를 없애는 방법이고, 당장 커밋을 다시 쪼갤 여유가 없다면 A로 진행하는 것도 현실적인 선택이다. 다만 셋 중 무엇을 택할지, 혹은 다른 조합을 쓸지는 실제 트래픽 패턴과 재작업 여유를 아는 쪽에서 정할 일이다.

### 1-5. dev(스테이징) 환경 — 이 런북이 지금까지 다루지 않았던 부분

`scripts/deploy.sh`의 마지막 단계는 운영 배포가 끝난 뒤 dev 환경을 조용히 따라 갱신한다. 이 문서의 이전 판에는 이 단계가 전혀 언급되지 않았다 — 도메인을 옮기면서 이 존재를 놓치기 쉽다.

**[8/8]이 실제로 하는 일** (158-186행)

- 프론트엔드 정적 파일과 백엔드/워커 코드는 운영과 dev가 같은 디렉터리(`backend/`, `worker/`, 빌드된 프론트 정적 파일)를 공유한다. Step 1~3에서 이미 새 코드로 갱신돼 있으므로 8단계에서 새로 받아오는 파일은 없다.
- `.env.dev`에서 `DATABASE_URL=` 줄을 읽어(`grep`+`cut`) `stack_health_dev` DB에 대고 같은 `alembic upgrade head`를 한 번 더 돌린다 — 운영에 적용한 것과 동일한 마이그레이션 세트다. 1-4에서 다룬 `reward_points` DROP과 카테고리 리맵이 dev DB에도 그대로 들어간다는 뜻이다.
- `.env.dev`에 `DATABASE_URL`이 없으면 마이그레이션만 건너뛰고 경고를 찍지만, 그 아래 `stack-health-app-dev`/`stack-health-worker-dev` 재시작은 조건 없이 실행된다. dev DB가 새 스키마를 못 받았어도 새 코드로는 재시작된다는 뜻이라, 코드와 스키마가 어긋난 채로 dev가 뜰 수 있다.
- 8단계 전체는 `set +e`로 감싼 서브셸이다. 실패해도 종료 코드를 `DEV_RC`에 담아 경고 문구(`journalctl --user -u stack-health-app-dev -u stack-health-worker-dev`로 확인하라는 안내)만 찍고, 이미 끝난 운영 배포에는 영향을 주지 않는다. 배포가 CI(`.github/workflows/deploy.yml`)로 무인 실행되는 경우 이 경고 한 줄을 실제로 보는 사람이 없을 수 있어, dev가 깨진 채로 방치될 수 있다.

**도메인 전환과 겹치는 지점**

- `.env.dev`는 리포지토리에 없다(서버 전용). 그 안에 `APP_URL`/`APP_BASE_URL`에 해당하는 dev용 키가 있는지, 있다면 지금 값이 무엇인지는 이 문서만으로 확인할 수 없다. **확인 필요**: 서버에서 `cat .env.dev`로 직접 본다.
- **결정 필요**: `dev.stackhealth.life`를 이번 전환에서 `dev.bitcoiners.life`로 함께 옮길지는 아직 정해지지 않았다. 옮기기로 하면 최소한 아래가 추가로 필요하다 — 2장의 절차를 dev 도메인에 맞춰 한 번 더 반복하는 셈이다.
  - `dev.bitcoiners.life` DNS A레코드·인증서·nginx server_name 추가 (Step 1~3과 동일한 절차)
  - `.env.dev`의 도메인 관련 키 갱신
  - dev가 별도 Google OAuth 클라이언트를 쓰는지, 쓴다면 그 redirect_uri도 3장과 같은 방식으로 재등록해야 하는지 확인 — 이것도 `.env.dev`를 봐야 알 수 있다
  - 옮기지 않기로 하면 dev는 계속 `dev.stackhealth.life`로 남는다. 5장의 301은 프로덕션 서버 블록에 거는 것이므로, dev 서버 블록에 같은 301을 걸지 않는 한 dev 접속은 그대로 이어진다 — 다만 그 경우 dev만 옛 브랜드 도메인에 남는 비대칭 상태가 굳어진다는 점은 인지해둔다.

## 2. 전환 순서

### Step 1 — DNS A레코드 추가 (stackhealth.life는 그대로 둔다)

```bash
dig stackhealth.life A +short   # 기존 IP 확인
```

확인한 IP로 `bitcoiners.life` A레코드를 새로 추가한다. 기존 `stackhealth.life` 레코드는 건드리지 않는다 — 두 도메인이 같은 서버를 가리키는 상태로 만드는 게 목적이다.

**성공 확인**:
```bash
dig bitcoiners.life A +short   # 위에서 확인한 IP와 일치해야 함
```
DNS 전파는 TTL에 따라 수 분~수 시간 걸릴 수 있다. 전파 전에 다음 단계로 넘어가면 인증서 발급(HTTP-01 challenge)이 실패한다.

### Step 2 — bitcoiners.life 인증서 발급

1-3에서 `sudo certbot certificates`로 certbot 관리 대상임을 확인했다면:

```bash
sudo certbot certonly --nginx -d bitcoiners.life
```

기존 `stackhealth.life` 인증서 발급 시 `--nginx` 대신 `--webroot`를 썼을 수도 있으니, `sudo certbot certificates` 출력의 `stackhealth.life` 항목에 적힌 발급 방식을 그대로 따른다.

**성공 확인**:
```bash
sudo certbot certificates | grep -A3 "bitcoiners.life"
openssl s_client -connect bitcoiners.life:443 -servername bitcoiners.life </dev/null 2>/dev/null | openssl x509 -noout -dates
```

### Step 3 — nginx server_name에 bitcoiners.life 추가 (양쪽 다 받는 상태)

1-3에서 찾은 서버 블록 파일에 `server_name`을 두 도메인 모두 포함하도록 수정한다. 기존 블록이 대략 이런 구조일 것이다(실제 파일 내용에 맞춰 조정한다):

```nginx
server {
    listen 443 ssl;
    server_name stackhealth.life bitcoiners.life;

    ssl_certificate     /etc/letsencrypt/live/bitcoiners.life/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bitcoiners.life/privkey.pem;

    location / {
        proxy_pass http://stackhealth_app;   # 업스트림 이름은 stackhealth-upstream.conf 기준, 바꾸지 않는다
        proxy_set_header Host $host;
        proxy_set_header Connection "";
        # ... 기존 proxy_set_header 들은 그대로 유지
    }
}
```

`ssl_certificate` 경로는 Step 2에서 발급한 인증서로 바꾸되, `stackhealth.life` 인증서도 만료 전까지는 그대로 둔다(둘 다 유효해야 두 도메인이 동시에 정상 응답한다).

**성공 확인**:
```bash
sudo nginx -t                 # 문법 검증, 반드시 reload 전에 실행
sudo systemctl reload nginx   # 또는 sudo nginx -s reload
curl -Ik https://stackhealth.life/health   # 기존 도메인 정상 응답 유지
curl -Ik https://bitcoiners.life/health    # 새 도메인도 정상 응답
```
두 요청 다 `HTTP/2 200`과 `{"status":"ok"}` 계열 응답이 나와야 다음 단계로 넘어갈 수 있다.

### Step 4 — 검증 (전환 전 마지막 확인)

301을 걸기 전에 `bitcoiners.life`가 완전히 정상 동작하는지 브라우저로 직접 확인한다. 이 시점에는 백엔드 환경변수가 아직 옛 도메인 기준이라 로그인 리다이렉트나 공유 링크는 `stackhealth.life`로 나갈 수 있다 — 이건 정상이다. 여기서 보는 건 TLS와 정적 자산·API 응답이 정상인지다.

- `https://bitcoiners.life/` 접속 → 인증서 경고 없이 로딩되는지
- `curl -sI https://bitcoiners.life/assets/` 로 정적 자산 서빙 확인
- API 응답 확인: `curl -s https://bitcoiners.life/health`

### Step 5 — stackhealth.life → bitcoiners.life 301 전환

검증이 끝났으면 옛 도메인 블록을 리다이렉트 전용으로 바꾼다. Step 3에서 합쳐뒀던 `server_name`을 분리한다:

```nginx
server {
    listen 443 ssl;
    server_name stackhealth.life;

    ssl_certificate     /etc/letsencrypt/live/stackhealth.life/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/stackhealth.life/privkey.pem;

    return 301 https://bitcoiners.life$request_uri;
}

server {
    listen 443 ssl;
    server_name bitcoiners.life;
    # ... Step 3의 proxy_pass 블록 전체
}
```

**성공 확인**:
```bash
sudo nginx -t && sudo systemctl reload nginx
curl -IL https://stackhealth.life/   # 301 → https://bitcoiners.life/ 로 이어지는지
curl -sI https://stackhealth.life/some/path | grep -i location   # 경로가 보존되는지 ($request_uri)
```

### Step 6 — 환경변수 갱신 후 재배포

서버 `.env` 파일에서 아래 키를 `bitcoiners.life` 기준으로 바꾼다.

| 키 | 용도 | 근거 |
|---|---|---|
| `APP_URL` | Google OAuth redirect_uri의 베이스 (`backend/app/services/google_oauth.py:49`) | **중요** — 3장 참고. 빠뜨리면 구글 로그인이 죽는다 |
| `APP_BASE_URL` | 로그인 후 프론트 리다이렉트, OG 메타태그(`main.py:270`), LNURL 콜백(`services/lnauth.py:19`) | 공유 링크·라이트닝 로그인이 옛 도메인을 가리키게 됨 |
| `FRONTEND_URL` | `backend/app/config.py`에 설정값만 존재, 현재 코드에서 참조하는 곳 없음(확인 완료) | 당장 기능엔 영향 없지만 `backend/.env.example` 템플릿과 일관성 위해 갱신 권장 |
| `VITE_APP_BASE_URL` | 프론트 빌드 시점에 정적 JS로 구워지는 변수(아래 "왜 재배포까지 필요한가" 참고), `frontend/src` 전체 검색 결과 현재 사용처 없음(확인 완료) | 지금은 죽은 변수라 실질적 영향은 없지만 `.env.example` 스펙과 맞춰 갱신 권장 |

루트 `.env.example`에는 원래 `APP_URL` 항목이 없었다 — 이 문서 초안 작성 뒤 팀장이 주석과 함께 추가해뒀다(`backend/app/services/google_oauth.py`가 이 값을 쓴다는 안내 포함). 이제 남은 확인은 하나뿐이다: 서버의 실제 `.env`에 이 키가 들어 있는지.
```bash
grep -E "^(APP_URL|APP_BASE_URL|FRONTEND_URL|VITE_APP_BASE_URL)=" .env
```

#### 왜 `.env`만 고치고 끝나지 않는가

`APP_URL`·`APP_BASE_URL`·`FRONTEND_URL`은 `backend/app/config.py`의 pydantic `Settings`가 프로세스 시작 시 한 번만 읽는 값이다. 그래서 반영되려면 백엔드 프로세스가 다시 시작돼야 한다 — `deploy.sh`의 Step 5(`systemctl --user restart "stack-health-app-$NEXT_SLOT"`, 스크립트 89~91번째 줄)가 이 역할을 한다.

`VITE_APP_BASE_URL`은 다르다. Vite는 이 값을 런타임에 읽지 않고, `npm run build` 시점에 정적 JS 파일 안에 문자열로 박아 넣는다. `deploy.sh` Step 3(78~82번째 줄)이 `.env`를 `source`한 뒤 `npm run build`를 실행하는 지점이 바로 그 시점이다. 프로세스를 재시작해도 이미 빌드된 정적 파일은 그대로라, 이 변수를 쓰는 코드가 있다면 재빌드 없이는 값이 바뀌지 않는다.

두 종류 다 `scripts/deploy.sh`를 그대로 실행하면 Step 3(재빌드)과 Step 5(재시작)를 순서대로 거치므로 자동으로 해결된다. 문제는 지름길이다 — `.env`만 고치고 활성 슬롯을 `systemctl --user restart`로 직접 재시작하면 blue-green 무중단 스왑 없이 그 자리에서 바로 끊기는 데다, 프론트 정적 자산은 재빌드되지 않은 채로 남는다. 지금은 `VITE_APP_BASE_URL`을 쓰는 코드가 없어 눈에 띄는 차이가 없지만, 이후 이 값을 쓰는 코드가 생기면 이 지름길에서 값이 반영 안 되는 채로 남는다.

> **주의**: 여기서 실행하는 `scripts/deploy.sh`에는 도메인 전환과 무관한 별도 위험이 걸려 있다 — 1-4("다음 배포가 밟게 될 위험") 참고. 이 배포가 처음으로 `reward_points` DROP과 카테고리 리맵을 운영에 실어 나르는 배포라면, 재배포 전에 1-4의 완화 방안 중 하나를 먼저 정해둔다.

값을 넣거나 고친 뒤 재배포한다:

```bash
bash scripts/deploy.sh
```

CI(`.github/workflows/deploy.yml`)는 `main` 브랜치 push에 물려 있으니, 코드 변경 없이 `.env`만 바꾼 경우에도 서버에서 `scripts/deploy.sh`를 직접 실행해야 한다 — push만으로는 트리거되지 않는다.

**성공 확인**:
```bash
curl -s https://bitcoiners.life/api/v1/auth/google | grep -o "redirect_uri=[^&]*"
# https://bitcoiners.life/api/v1/auth/google/callback 이 URL-encode된 형태로 나와야 함
```

## 3. Google OAuth 재등록 — 반드시 이 단계를 빠뜨리지 말 것

> **경고**: 이 단계를 건너뛰면 Google 로그인이 즉시 깨진다. `redirect_uri`가 Google Cloud Console에 등록된 값과 정확히 일치하지 않으면 Google이 `redirect_uri_mismatch` 에러로 콜백을 거부한다.

`backend/app/services/google_oauth.py:45-49`의 `_google_redirect_uri()`가 실제로 만드는 값:

```python
return f"{settings.app_url}/api/v1/auth/google/callback"
```

즉 Step 6에서 `APP_URL`을 `https://bitcoiners.life`로 바꿨다면, 등록해야 할 정확한 URI는:

```
https://bitcoiners.life/api/v1/auth/google/callback
```

**등록 절차**:
1. Google Cloud Console → APIs & Services → Credentials → 해당 OAuth 2.0 Client ID
2. Authorized redirect URIs에 위 URI를 추가한다 (기존 `https://stackhealth.life/api/v1/auth/google/callback`은 Step 5의 301 리다이렉트가 안정화될 때까지 남겨둔다 — 캐시된 옛 링크로 들어오는 로그인 시도를 위한 안전망이다)
3. 저장 후 몇 분 내 반영된다 (Google 쪽은 즉시 반영되는 편이지만 캐시 지연 가능)

**성공 확인**: 실제 브라우저에서 `https://bitcoiners.life/api/v1/auth/google`로 로그인을 끝까지 시도해 콜백이 `redirect_uri_mismatch` 없이 성공하는지 확인한다. 이건 curl로 대체 검증이 안 되는 단계다 — 브라우저로 직접 확인한다.

## 4. 롤백

| 단계 | 문제 상황 | 롤백 방법 |
|---|---|---|
| Step 1 (DNS) | 전파 지연으로 접속 불가 | 그냥 대기. 되돌릴 것 없음 |
| Step 2 (인증서) | 발급 실패 (HTTP-01 challenge 실패 등) | `stackhealth.life` 서비스에는 영향 없음. DNS 전파를 더 기다리거나 challenge 방식 재확인 후 재시도 |
| Step 3 (nginx 양쪽 허용) | `nginx -t` 실패 또는 reload 후 응답 이상 | 수정 전 파일을 백업해뒀다면 그걸로 복원 후 `sudo nginx -t && sudo systemctl reload nginx`. 백업이 없으면 추가한 `server_name`과 `ssl_certificate` 줄만 제거 |
| Step 5 (301 전환) | `stackhealth.life` 접속자가 리다이렉트 루프에 빠지거나 502 발생 | `return 301` 블록을 제거하고 Step 3의 "양쪽 다 받는" 상태로 되돌린 뒤 `nginx -t && reload` |
| Step 6 (환경변수) | Google 로그인 실패, 공유 링크가 깨짐 | `.env`의 `APP_URL`/`APP_BASE_URL`을 `https://stackhealth.life`로 되돌리고 `bash scripts/deploy.sh` 재실행 |

### nginx 관련 롤백에서 가장 흔한 함정

`CLAUDE.md`는 이 영역에서 실제로 겪은 두 가지 실패를 각각 기록해뒀다.

하나는 일반 경고다: 리포지토리의 `nginx/upstream.conf`는 nginx가 직접 읽지 않는 참조용 사본이라, 이 파일만 고치고 `nginx reload`를 해도 실제 upstream은 그대로다. 이번 도메인 전환에서 건드리는 서버 블록 파일도 같은 함정에 걸릴 수 있다 — 리포지토리에는 그 파일 자체가 없으므로, 반드시 1-3에서 찾은 서버의 실제 파일을 직접 수정해야 한다. 엉뚱한 파일을 고치면 nginx는 문법 검증도 reload도 다 통과하는데 `server_name`도 SSL 인증서 경로도 반영되지 않는, 알아채기 어려운 상태가 된다.

다른 하나는 **2026-05-31 장애** 기록이다. 이때는 실제 파일(`/etc/nginx/conf.d/stackhealth-upstream.conf`)을 맞게 고쳤는데도 전체 502/521이 떴다 — 원인은 upstream을 8018(green)로 돌렸을 때 green 슬롯 자체가 떠 있지 않았던 것이었다. 파일을 맞게 고쳤는지와는 별개로, 전환 직후에는 항상 두 도메인 모두에서 실제 응답을 curl로 확인하고 넘어가야 한다는 교훈이다. Step 3·Step 5의 "성공 확인" 절차를 생략하지 않는 이유가 여기 있다.

서버 블록 파일을 고치기 전에는 반드시 원본을 백업해둔다:

```bash
sudo cp /etc/nginx/<실제 서버 블록 파일 경로> /etc/nginx/<실제 서버 블록 파일 경로>.bak-$(date +%Y%m%d)
```

## 5. 건드리면 안 되는 것

이름에 `stackhealth`가 들어가지만 바꾸면 배포·운영이 깨지는 식별자들이다.

| 식별자 | 바꾸면 안 되는 이유 |
|---|---|
| `/home/measly/stack-health/` | `.github/workflows/deploy.yml`이 이 절대경로로 `scripts/deploy.sh`를 직접 호출한다 |
| `/etc/nginx/conf.d/stackhealth-upstream.conf` | 실제 nginx가 읽는 blue/green 포트 정의 파일. 파일명이 아니라 내용(포트 번호)만 바뀌어야 하는 대상 |
| `/tmp/stackhealth-deploy.lock` | 동시 배포 방지용 flock 대상 파일. 다른 이름으로 바꾸면 락이 무력화돼 배포 두 개가 겹칠 수 있다 |
| `stack-health-worker@{1,2}` | systemd `--user` 템플릿 유닛. `scripts/deploy.sh`가 이 유닛명으로 재시작을 호출한다 |
| `server.stackhealth.life` | Redis 서버 호스트명(`worker/DEPLOY.md`). DNS 레코드가 이 이름으로 걸려 있어 바꾸면 워커가 Redis에 연결 못 한다 |
| R2 버킷명 / `R2_PUBLIC_URL` | 이미 업로드된 모든 영상·썸네일 링크가 이 값을 기준으로 생성돼 있다(1-1 참조). 바꾸면 기존 콘텐츠가 전부 404 |
| `com.stackhealth.app` | 안드로이드 패키지 ID. Google Play 스토어에 이 ID로 등록돼 있어 바꾸면 별개 앱 취급된다 |

## 6. SEO 체크리스트 (301 전환 이후)

코드 쪽 SEO 자산은 이미 `bitcoiners.life` 기준으로 맞춰져 있다 — `frontend/public/sitemap.xml`, `frontend/public/robots.txt`, `frontend/index.html`의 canonical·OG·JSON-LD 태그 전부 확인 완료. 남은 건 검색엔진에 새 도메인을 알리는 절차다.

- [ ] Google Search Console에 `bitcoiners.life` 속성 새로 등록 (도메인 속성 또는 URL 접두어 속성)
- [ ] Search Console의 "주소 변경 도구"(Change of Address tool)로 `stackhealth.life` → `bitcoiners.life` 이전 신고 (301이 안정화된 뒤 실행 — Step 5 완료 후)
- [ ] `https://bitcoiners.life/sitemap.xml` 제출 (내용은 이미 새 도메인 기준)
- [ ] Bing Webmaster Tools에도 동일하게 새 사이트 등록 + sitemap 제출
- [ ] 임의 페이지 여러 개를 골라 `curl -sI`로 canonical 태그와 실제 서빙 도메인이 일치하는지 재확인
- [ ] 기존 `stackhealth.life`로 걸린 외부 백링크·소셜 공유 링크 목록이 있다면 301로 정상 흡수되는지 샘플 확인
- [ ] 2~4주 후 Search Console에서 `stackhealth.life` 색인이 줄고 `bitcoiners.life` 색인이 느는지 추적

## 부록 — 모바일 앱 참고사항 (이번 서버 인프라 전환 범위 밖)

`mobile/lib/main.dart:10-13`의 `kAppUrl`은 웹뷰가 로드할 URL을 `--dart-define=APP_URL`로 받고, 기본값은 이미 `https://bitcoiners.life`였다. 다만 이 문서 초안 작성 시점에는 `.github/workflows/flutter-build.yml:65`의 실제 빌드 명령이 `--dart-define=APP_URL=https://stackhealth.life`로 옛 도메인을 덮어쓰고 있었다 — 이 값도 지금은 `bitcoiners.life`로 고쳐졌다.

남은 건 재빌드뿐이다. 이미 스토어에 배포된 APK는 빌드 시점 값이 그대로 굳어 있어서, 이번 수정을 반영하려면 새 APK를 빌드해 다시 배포해야 한다. 이 워크플로는 `mobile/**` 변경이나 자체 파일 변경을 포함한 `main` push에 물려 있고(`on.push.paths`), 코드 변경 없이 강제로 새로 돌리려면 `workflow_dispatch`로 수동 실행한다:
```bash
gh workflow run flutter-build.yml
```
기존에 설치된 앱은 스토어 업데이트를 받기 전까지 계속 `stackhealth.life`를 열지만, Step 5의 301 리다이렉트가 살아있는 한 정상 동작한다.
