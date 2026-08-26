# Bitcoiners Mobile (Flutter WebView Wrapper)

배포된 웹앱을 감싸는 Android/iOS 앱입니다.

## 자동 빌드 (GitHub Actions)

`mobile/` 파일이 변경되어 `main`에 푸시되면 자동으로 APK를 빌드하고 R2에 업로드합니다.

### GitHub Secrets 설정 (필수)

GitHub 저장소 → Settings → Secrets and variables → Actions에서 아래 시크릿을 등록하세요:

| 시크릿 이름 | 값 설명 |
|---|---|
| `APP_URL` | 배포된 웹앱 URL (예: `https://xxx.up.railway.app`) |
| `ADMIN_SECRET_KEY` | `.env`의 `ADMIN_SECRET_KEY` 값 |
| `R2_PUBLIC_URL` | R2 공개 URL (예: `https://pub-xxx.r2.dev`) |
| `ANDROID_KEYSTORE_BASE64` | (선택) 서명용 키스토어를 base64 인코딩한 값 |
| `ANDROID_KEY_STORE_PASSWORD` | (선택) 키스토어 비밀번호 |
| `ANDROID_KEY_PASSWORD` | (선택) 키 비밀번호 |
| `ANDROID_KEY_ALIAS` | (선택) 키 별칭 |

> `ANDROID_KEYSTORE_BASE64`를 설정하지 않으면 debug 서명으로 빌드됩니다.

### 키스토어 생성 방법 (서명 APK용)

```bash
# 1. 키스토어 생성
keytool -genkey -v -keystore release.keystore -alias stack_health \
  -keyalg RSA -keysize 2048 -validity 10000

# 2. base64 인코딩 → GitHub Secret에 등록
base64 -i release.keystore | tr -d '\n'
```

### 수동 빌드 트리거

GitHub 저장소 → Actions → "Flutter APK Build & Deploy" → "Run workflow"

## 로컬 빌드 (Flutter 설치 필요)

```bash
cd mobile
flutter pub get
flutter build apk --release --dart-define=APP_URL=https://your-app.railway.app
```
