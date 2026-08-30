from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", extra="ignore")

    # Database
    database_url: str = "sqlite:///./dev.db"

    # JWT
    secret_key: str
    access_token_expire_minutes: int = 1440  # 1일 (refresh 토큰으로 자동 갱신)
    refresh_token_expire_minutes: int = 129600  # 90일

    # Cloudflare R2
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket_name: str = ""
    r2_public_url: str = ""

    # Admin
    admin_secret_key: str

    # Google OAuth
    google_client_id: str = ""
    google_client_secret: str = ""

    # Redis
    redis_url: str = ""

    # App
    # APP_URL: the publicly reachable base URL of this backend server.
    # Used as the redirect_uri base for Google OAuth.
    # IMPORTANT: Register "{APP_URL}/api/v1/auth/google/callback" in Google Cloud Console
    #   → APIs & Services → Credentials → OAuth 2.0 Client → Authorized redirect URIs
    app_url: str = "http://localhost:5173"
    app_base_url: str = "http://localhost:8000"
    # LNURL_BASE_URL: LNURL-auth 전용 공개 URL. 비워두면 app_base_url 을 따른다.
    # LUD-04 는 linkingKey 를 HMAC-SHA256(hashingKey, FQDN) 으로 파생한다. 이 URL 의
    # 도메인이 바뀌면 같은 지갑이 다른 공개키를 만들어 기존 계정에 못 들어오고,
    # 로그인 실패가 아니라 빈 새 계정이 조용히 생긴다. 그래서 서비스 도메인을
    # 옮기더라도 이 값은 라이트닝 사용자가 처음 가입한 도메인으로 고정한다.
    lnurl_base_url: str = ""
    frontend_url: str = "http://localhost:5173"
    environment: str = "development"
    port: int = 8000

    @property
    def lnurl_origin(self) -> str:
        """LNURL 에 박히는 base URL. 지갑 신원이 걸려 있어 서비스 도메인과 분리한다."""
        return self.lnurl_base_url or self.app_base_url


settings = Settings()
