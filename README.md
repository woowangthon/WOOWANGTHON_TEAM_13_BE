# WOOWANGTHON_TEAM_13_BE

2026 AI 우왕톤 13팀 F4의 백엔드 저장소입니다.

## 프로젝트 구조

```text
WOOWANGTHON_TEAM_13_BE/
├── app/
│   ├── app.py                 # FastAPI 애플리케이션 진입점
│   ├── api/
│   │   ├── router.py          # API 라우터 통합
│   │   └── v1/
│   │       └── health.py      # v1 Health Check API
│   ├── core/                  # 환경설정, 로깅, 공통 예외 처리
│   ├── db/                    # DB 연결 및 세션 관리
│   ├── integrations/          # AI 서버, 스토리지 등 외부 서비스 연동
│   ├── models/                # SQLAlchemy 데이터베이스 모델
│   ├── repositories/          # 데이터 접근 로직
│   ├── schemas/               # Pydantic 요청·응답 스키마
│   └── services/              # 비즈니스 로직
├── tests/
│   ├── unit/                  # 단위 테스트
│   ├── integration/           # 통합 테스트
│   └── test_health.py         # Health Check API 테스트
├── .github/
│   └── workflows/             # GitHub Actions 워크플로
├── .gitignore
├── pytest.ini                 # pytest 설정
├── requirements.txt           # Python 의존성 및 버전
└── ruff.toml                  # Ruff 린트 설정
```

## 커밋 규칙

커밋 메시지는 다음 형식을 사용합니다.

```text
<type>: <변경 내용>
```

| Type | 설명 |
| --- | --- |
| `feat` | 새로운 기능 추가 |
| `fix` | 버그 수정 |
| `docs` | 문서 변경 |
| `style` | 코드 포맷팅, 세미콜론 누락 등 코드 동작에 영향을 주지 않는 변경 |
| `refactor` | 기능 변경이 없는 코드 리팩터링 |
| `test` | 누락된 테스트 추가 또는 기존 테스트 수정 |
| `chore` | 라이브러리 추가 등 빌드 프로세스 또는 보조 도구 변경 |
| `perf` | 성능 향상 관련 변경 |
| `build` | 빌드 관련 파일 변경 |

예시:

```text
feat: 사용자 회원가입 API 추가
fix: 일정 조회 시 시간대 변환 오류 수정
docs: API 실행 방법 추가
test: health check API 테스트 추가
chore: FastAPI 의존성 추가
```

### 작성 원칙

- 커밋 타입은 소문자로 작성합니다.
- 타입 뒤에 콜론과 공백을 넣습니다.
- 변경 내용을 짧고 명확하게 작성합니다.
- 하나의 커밋에는 하나의 논리적인 변경만 포함합니다.

## Supabase JWT 인증 확인

백엔드는 Google·Kakao 공급자의 토큰이 아니라 Supabase 로그인 세션의
`access_token`을 검증합니다. 프론트엔드는 인증이 필요한 API를 호출할 때
다음 헤더를 전달해야 합니다.

```http
Authorization: Bearer <SUPABASE_ACCESS_TOKEN>
```

로컬 서버를 실행한 뒤 `http://localhost:8000/docs`에서 `Authorize`를 눌러
Supabase access token을 입력하면 보호된 API를 테스트할 수 있습니다.

```bash
uvicorn app.app:app --reload
```

JWT 검증은 Supabase JWKS 공개키를 사용하며 서명, 발급자(`iss`),
대상(`aud`), 만료 시간(`exp`), 사용자 식별자(`sub`)를 확인합니다.
토큰이 없거나 검증에 실패하면 `401 Unauthorized`와
`WWW-Authenticate: Bearer` 헤더를 반환합니다.

## 로컬 프론트엔드 연동

로컬 백엔드 기본 주소는 `http://localhost:8000`이며, 기본 CORS 허용
주소는 Vite 개발 서버인 `http://localhost:5173`입니다. 다른 프론트엔드
주소를 함께 허용하려면 `.env`의 `CORS_ORIGINS`에 쉼표로 구분해 추가합니다.

```dotenv
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

브라우저에서 `Authorization: Bearer <SUPABASE_ACCESS_TOKEN>` 헤더를 포함한
요청과 CORS 사전 요청(`OPTIONS`)을 허용합니다.

## 초대 코드와 매장 가입

사장님은 자신이 소유한 매장에 직원 이름과 2026년 최저시급 이상의 시급을
지정해 6자리 초대 코드를 발급할 수 있습니다. 코드는 `0`, `O`, `1`, `I`를
제외한 영문 대문자와 숫자로 구성됩니다.

```http
POST /api/v1/stores/{storeId}/invitations
Authorization: Bearer <SUPABASE_ACCESS_TOKEN>
Content-Type: application/json

{
  "staffName": "지은",
  "hourlyWage": 10320
}
```

직원은 로그인 후 코드를 확인하고 가입합니다.

```http
POST /api/v1/invitations/verify
POST /api/v1/memberships/join

{ "code": "K7P2QX" }
```

잘못된 코드를 5회 입력하면 해당 사용자의 코드 확인을 10분 동안 잠급니다.
가입이 완료되면 `GET /api/v1/users/me`와 `GET /api/v1/users/me/stores`에서
실제 소유·직원 매장 목록을 반환합니다.

## 사용자 정보 API

사용자 정보 API는 모두 Supabase access token이 필요합니다. 첫
`GET /api/v1/users/me` 요청에서 JWT의 `sub`와 연결되는 애플리케이션 사용자가
없으면 자동으로 생성합니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `GET` | `/api/v1/users/me` | 내 정보 조회 및 최초 사용자 생성 |
| `PATCH` | `/api/v1/users/me` | 닉네임 수정 |
| `DELETE` | `/api/v1/users/me` | 회원 탈퇴(프로필 삭제 및 재생성 방지) |
| `GET` | `/api/v1/users/me/stores` | 내 소속 매장 목록 조회 |

DB 스키마를 반영한 뒤 서버를 실행합니다.

```bash
alembic upgrade head
uvicorn app.app:app --reload
```

## 매장 API

매장 API는 모두 Supabase access token이 필요하며, 현재 로그인한 사용자가
소유한 매장만 조회·수정·삭제할 수 있습니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/v1/stores` | 매장 등록 |
| `GET` | `/api/v1/stores` | 내가 소유한 매장 목록 조회 |
| `GET` | `/api/v1/stores/{storeId}` | 매장 상세 조회 |
| `PATCH` | `/api/v1/stores/{storeId}` | 매장 정보 수정 |
| `DELETE` | `/api/v1/stores/{storeId}` | 매장 삭제 |

사업자 인증 기능이 구현되기 전까지 `businessVerificationId`는 선택값이며,
별도의 인증 완료 여부 검증은 수행하지 않습니다. 매장 대표 이미지는
`photoUrl`로 등록하거나 수정할 수 있습니다.
