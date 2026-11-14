# 실행 방법 · 환경변수

[README로 돌아가기](../README.md)

### 사전 준비

- Python 3.12 사용 권장
- Supabase 프로젝트와 접속 가능한 PostgreSQL DB
- Supabase Auth 설정 및 로그인 가능한 테스트 계정
- AI·이미지·사업자 조회·Web Push를 검증하려면 해당 연동 설정

### 설치

```bash
git clone https://github.com/woowangthon/WOOWANGTHON_TEAM_13_BE.git
cd WOOWANGTHON_TEAM_13_BE

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

cp .env.example .env
```

### 환경변수

`.env`의 다음 기본 설정에 실제 값을 입력합니다.

```dotenv
DATABASE_URL=postgresql+asyncpg://<USER>:<PASSWORD>@<HOST>:<PORT>/<DATABASE>
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=0

SUPABASE_URL=https://<PROJECT_REF>.supabase.co
SUPABASE_JWT_ISSUER=https://<PROJECT_REF>.supabase.co/auth/v1
SUPABASE_JWT_AUDIENCE=authenticated
SUPABASE_JWKS_URL=https://<PROJECT_REF>.supabase.co/auth/v1/.well-known/jwks.json

CORS_ORIGINS=http://localhost:5173
```

`<...>`는 실제 프로젝트 값으로 교체합니다. DB 비밀번호에 URL 예약 문자가 있으면 URL 인코딩이 필요합니다. 애플리케이션 DB 연결은 SSL을 요구합니다. 기본 설정만으로 모든 외부 연동 기능을 검증할 수는 없습니다.

| 검증할 기능 | 추가 환경변수 및 준비 |
| --- | --- |
| AI 답변·초안·요약 | `GEMINI_API_KEY`, 계정에서 사용 가능한 `GEMINI_MODEL` 설정. 예제 모델 기본값은 `.env.example` 참고 |
| 이미지 업로드 | `SUPABASE_SECRET_KEY`, 비공개 버킷 `SUPABASE_STORAGE_BUCKET=content-files`, 공개 버킷 `SUPABASE_STORE_PHOTO_BUCKET=store-photos` 생성 |
| 사업자 상태조회 | 공공데이터포털에서 발급받은 `NTS_BUSINESS_API_KEY` |
| Web Push | `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY`, `VAPID_SUBJECT`; FE의 `VITE_VAPID_PUBLIC_KEY`에 같은 공개키 설정 및 브라우저 알림 구독 |

`.env`, 서버 비밀키, VAPID 비밀키는 저장소에 커밋하거나 FE에 전달하지 않습니다.

### DB 마이그레이션 및 서버 실행

저장소 루트에서 실행합니다.

```bash
alembic upgrade head
uvicorn app.app:app --reload --host 0.0.0.0 --port 8000
```

| 항목 | 주소 |
| --- | --- |
| 서버 | http://localhost:8000 |
| Swagger UI | http://localhost:8000/docs |
| OpenAPI JSON | http://localhost:8000/openapi.json |
| Health Check | http://localhost:8000/api/v1/health/live |

다음: [실행 결과 확인 · 핵심 기능 검증](verification.md)
