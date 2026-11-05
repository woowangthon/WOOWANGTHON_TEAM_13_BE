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

## 매뉴얼 API

매뉴얼 API는 모두 Supabase access token이 필요합니다. 등록·수정·삭제와 카테고리
생성, 종류 추천은 매장 소유자만 할 수 있습니다. 멤버십 구현 전까지는 조회도
매장 소유자만 가능합니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/v1/stores/{storeId}/manual-categories` | 매뉴얼 카테고리 생성 |
| `POST` | `/api/v1/stores/{storeId}/manuals/recommendations` | 매뉴얼 종류 추천 |
| `POST` | `/api/v1/stores/{storeId}/manuals` | 매뉴얼 등록 |
| `GET` | `/api/v1/stores/{storeId}/manuals` | 매뉴얼 목록 조회 |
| `GET` | `/api/v1/stores/{storeId}/manuals/{manualId}` | 매뉴얼 상세 조회 |
| `PATCH` | `/api/v1/stores/{storeId}/manuals/{manualId}` | 매뉴얼 수정 |
| `DELETE` | `/api/v1/stores/{storeId}/manuals/{manualId}` | 매뉴얼 삭제 |

매뉴얼 등록은 `multipart/form-data`이며 `manual` 파트에 JSON을 담습니다. 파일
저장소가 정해지기 전까지 `files` 파트를 보내면 `501`을 반환합니다.

## 레시피 API

레시피 API는 모두 Supabase access token이 필요합니다. 등록·수정·삭제는 매장
소유자만 할 수 있습니다. 멤버십 구현 전까지는 조회도 매장 소유자만 가능합니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/v1/stores/{storeId}/recipes` | 레시피 등록 |
| `GET` | `/api/v1/stores/{storeId}/recipes` | 레시피 목록과 카테고리 조회 |
| `GET` | `/api/v1/stores/{storeId}/recipes/{recipeId}` | 레시피 상세 조회 |
| `PATCH` | `/api/v1/stores/{storeId}/recipes/{recipeId}` | 레시피 수정 |
| `DELETE` | `/api/v1/stores/{storeId}/recipes/{recipeId}` | 레시피 삭제 |

레시피 등록은 `multipart/form-data`이며 `recipe` 파트에 JSON을 담습니다. 파일
저장소가 정해지기 전까지 `images` 파트를 보내면 `501`을 반환합니다.

## AI 사수 채팅 API

AI 사수는 현재 매장의 매뉴얼과 레시피만 근거로 답합니다. 근거가 없으면 고정 안내문을
반환하고, LLM 호출에 실패하면 `503`을 반환합니다. 실행하려면 `.env`에
`GEMINI_API_KEY`가 필요합니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/v1/stores/{storeId}/assistant-chats` | 채팅방 생성 |
| `GET` | `/api/v1/stores/{storeId}/assistant-chats` | 내 채팅방 목록 조회 |
| `DELETE` | `/api/v1/stores/{storeId}/assistant-chats/{chatId}` | 채팅방 삭제 |
| `POST` | `/api/v1/stores/{storeId}/assistant-chats/{chatId}/messages` | 질문 전송과 답변 |
| `GET` | `/api/v1/stores/{storeId}/assistant-chats/{chatId}/messages` | 메시지 내역 조회 |

## 인수인계 API

인수인계 API는 모두 Supabase access token이 필요합니다. AI 초안은 저장되지 않고,
사용자가 확인한 내용만 등록 API로 저장합니다. 수정·삭제는 작성자나 사장님만 할 수
있습니다. `date`를 생략하면 한국 시간 기준 오늘을 조회합니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/v1/stores/{storeId}/handover-drafts` | AI 체크리스트 초안 생성 |
| `POST` | `/api/v1/stores/{storeId}/handover-notes` | 인수인계 등록 |
| `GET` | `/api/v1/stores/{storeId}/handover-notes` | 날짜별 목록 조회 |
| `GET` | `/api/v1/stores/{storeId}/handover-notes/{noteId}` | 상세 조회 |
| `PATCH` | `/api/v1/stores/{storeId}/handover-notes/{noteId}` | 수정 |
| `DELETE` | `/api/v1/stores/{storeId}/handover-notes/{noteId}` | 삭제 |
| `POST` | `/api/v1/stores/{storeId}/handover-notes/{noteId}/confirmations` | 항목 또는 노트 전체 체크 |
