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

사장님은 초대 코드 발급 이력과 공유 정보를 조회할 수 있습니다. 같은 매장과
직원 이름으로 사용 가능한 코드는 하나만 유지되며, 사용 또는 취소된 뒤에는 새
코드를 발급할 수 있습니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `GET` | `/api/v1/stores/{storeId}/invitations` | 초대 코드 목록 조회 |
| `GET` | `/api/v1/stores/{storeId}/invitations/{invitationId}/share-info` | 코드와 FE 입장 링크 조회 |
| `DELETE` | `/api/v1/stores/{storeId}/invitations/{invitationId}` | 미사용 초대 코드 취소 |
| `GET` | `/api/v1/stores/{storeId}/members` | 구성원 목록 조회 |
| `GET` | `/api/v1/stores/{storeId}/members/{memberId}` | 구성원 상세 조회 |
| `DELETE` | `/api/v1/stores/{storeId}/members/{memberId}` | 구성원 퇴사 처리 |

퇴사 처리는 멤버십을 삭제하지 않고 `LEFT` 상태로 보존합니다. 같은 사용자가 새
초대 코드로 다시 가입하면 기존 멤버십을 활성화하고 직원명과 시급을 새 초대
조건으로 갱신합니다.

## 근무 가능 시간 API

재직 중인 알바생은 다음 근무 대상 월의 날짜를 `available` 또는 `unavailable`로
표시하고 메모와 함께 제출할 수 있습니다. 기본 접수 대상은 다음 달이며 전월
25일에 마감합니다. 25일이 지나면 그다음 달 접수로 넘어갑니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `GET` | `/api/v1/stores/{storeId}/availabilities/me` | 현재 접수 월과 내 제출 조회 |
| `POST` | `/api/v1/stores/{storeId}/availabilities` | 근무 가능 시간 최초 제출 |
| `PATCH` | `/api/v1/stores/{storeId}/availabilities/{availabilityId}` | 마감 전 제출 수정 |
| `DELETE` | `/api/v1/stores/{storeId}/availabilities/{availabilityId}` | 내 제출 삭제 |
| `GET` | `/api/v1/stores/{storeId}/availabilities?month=YYYY-MM` | 사장님의 월별 제출 목록 조회 |
| `GET` | `/api/v1/stores/{storeId}/availability-submissions?month=YYYY-MM` | 사장님의 월별 제출 현황 조회 |

처음 제출하기 전에도 `GET .../availabilities/me`는 `availabilityId`와
`submittedAt`이 `null`인 현재 접수 정보를 반환합니다. 같은 구성원의 같은 월
중복 제출은 `409 AVAILABILITY_EXISTS`, 마감 이후 등록·수정은
`409 AVAILABILITY_CLOSED`를 반환합니다.

최초 제출 예시:

```json
{
  "month": "2026-12",
  "days": [
    { "date": "2026-12-01", "status": "available" },
    { "date": "2026-12-02", "status": "unavailable" }
  ],
  "memo": "화요일은 수업 때문에 근무가 어려워요"
}
```

## 추천 및 확정 스케줄 API

추천 스케줄은 LLM이 아니라 제출된 가능 일자, 주 최대 근무시간, 중복 근무와
최소 휴식시간을 계산하는 규칙 엔진으로 생성합니다. 같은 시간대에 배정 가능한
직원이 여러 명이면 우선순위를 순환하여 최대 3개의 서로 다른 후보를 반환합니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/v1/stores/{storeId}/schedule-recommendations` | 추천 후보 생성 |
| `GET` | `/api/v1/stores/{storeId}/schedule-recommendations` | 추천 후보 목록 조회 |
| `GET` | `/api/v1/stores/{storeId}/schedule-recommendations/{recommendationId}` | 추천 후보 상세 조회 |
| `POST` | `/api/v1/stores/{storeId}/schedules` | 후보를 실제 스케줄로 등록 |
| `GET` | `/api/v1/stores/{storeId}/schedules` | 매장 스케줄 조회 |
| `PATCH` | `/api/v1/stores/{storeId}/schedules/{scheduleId}` | 배정 조정 및 공개 상태 변경 |
| `GET` | `/api/v1/stores/{storeId}/schedules/me` | 공개된 내 근무표 조회 |

추천 생성 요청의 `shifts`에는 사장님이 필요한 날짜·시간대·인원을 입력합니다.
근무 가능 시간을 제출하지 않은 직원, `unavailable`로 표시한 날짜, 아무 상태도
표시하지 않은 날짜에는 배정하지 않습니다. 인원이 부족해도 후보를 저장하고 상세
응답의 `warnings`로 알려 줍니다.

```json
{
  "startDate": "2026-12-01",
  "endDate": "2026-12-07",
  "recommendationCount": 3,
  "shifts": [
    {
      "date": "2026-12-01",
      "start": "09:00",
      "end": "15:00",
      "role": "오픈",
      "requiredStaff": 2
    }
  ],
  "rules": {
    "maximumWeeklyHours": 40,
    "minimumRestMinutes": 30
  }
}
```

## 고정 스케줄과 하루 단위 근무 조정 API

고정 스케줄은 매주 반복되고, 사장님은 특정 날짜의 근무 목록만 별도로 바꿀 수
있습니다. 하루 단위 조정은 해당 날짜의 전체 근무 목록을 한 번에 교체하므로 변경,
추가, 삭제를 하나의 요청으로 처리합니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `GET` | `/api/v1/stores/{storeId}/schedule-calendar?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD` | 고정·대타·하루 조정을 합친 달력 조회 |
| `PUT` | `/api/v1/stores/{storeId}/schedule-calendar/{workDate}` | 해당 날짜의 근무 목록 전체 교체 (사장님) |
| `DELETE` | `/api/v1/stores/{storeId}/schedule-calendar/{workDate}` | 하루 조정을 제거하고 고정 스케줄로 복원 (사장님) |

`PUT`에는 그날 최종적으로 남길 근무를 모두 보냅니다. 한 건을 지우려면 그 근무만
제외하고 보내고, 그날 근무를 모두 지우려면 `shifts`를 빈 배열로 보냅니다.

```http
PUT /api/v1/stores/{storeId}/schedule-calendar/2026-11-12
Authorization: Bearer <SUPABASE_ACCESS_TOKEN>
Content-Type: application/json

{
  "shifts": [
    {
      "templateId": "<SHIFT_TEMPLATE_ID>",
      "assigneeUserId": "<USER_ID>",
      "start": "11:30",
      "end": "16:30"
    }
  ]
}
```

직접 조정한 근무는 달력 응답에서 `manuallyAdjusted: true`, `assignmentId: null`,
`dailyShiftId: "..."`로 구분됩니다. 하루 조정은 정기 휴무일이나 공휴일에도 우선하며,
예상 급여에도 반영됩니다. 같은 직원에게 시간이 겹치는 템플릿을 보내면
`409 DAILY_SCHEDULE_TIME_CONFLICT`를 반환합니다. 해당 날짜의 대기 중인 대타 요청은
하루 조정을 저장할 때 취소되고, 조정된 날짜에는 새 대타 요청을 만들 수 없습니다.
`start`와 `end`는 둘 다 선택값이며 `HH:MM` 형식으로 함께 보내야 합니다. 생략하면 해당
근무 템플릿의 시간을 사용하고, 값을 보내면 그 날짜의 달력과 예상 급여에만 적용됩니다.

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

사업자등록정보 인증은 공공데이터포털의 국세청 상태조회 API를 사용합니다.
`.env`의 `NTS_BUSINESS_API_KEY`에 발급받은 서비스 키를 설정합니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/v1/stores/business-verifications` | 사업자등록번호 상태조회 |
| `GET` | `/api/v1/stores/business-verifications/{verificationId}` | 본인의 인증 결과 조회 |

매장 등록에는 로그인한 사용자가 요청해 `VERIFIED` 결과를 받은
`businessVerificationId`가 반드시 필요합니다. 다른 사용자의 인증 결과나
`INVALID` 결과로는 매장을 등록하거나 인증 정보를 변경할 수 없습니다.
매장 대표 이미지는 `photoUrl`로 등록하거나 수정할 수 있습니다.

상태조회 요청은 하이픈 포함 여부와 관계없이 10자리 `businessRegistrationNumber`만
받습니다. 국세청 응답이 계속사업자(`b_stt_cd=01`)이면 `VERIFIED`, 휴업·폐업·미등록
번호이면 `INVALID`로 저장합니다. 시연·테스트에서는 `000-00-00000`을 보내면 외부 API를
호출하지 않고 `VERIFIED` 결과를 받을 수 있습니다.

### 매장 사진 업로드

| Method | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/v1/stores/{storeId}/photo` | 매장 사진 업로드 (사장님만) → `{ "photoUrl": "…" }` |

`multipart/form-data`의 `image` 파트로 JPEG, PNG, WebP 사진을 10MB까지 받습니다.
사진은 공개 버킷(`SUPABASE_STORE_PHOTO_BUCKET`, 기본 `store-photos`)에 저장하고 만료되지
않는 공개 주소를 돌려줍니다. 이 API는 매장 정보를 바꾸지 않으므로, 받은 주소를 매장
등록·수정 API의 `photoUrl`에 넣어 저장합니다. 오류 형식은 레시피 사진과 같습니다
(`413 IMAGE_TOO_LARGE`, `415 UNSUPPORTED_IMAGE_TYPE`, `503 STORAGE_UNAVAILABLE`).

## 매뉴얼 API

매뉴얼 API는 모두 Supabase access token이 필요합니다. 등록·수정·삭제와 카테고리
생성, 종류 추천은 매장 소유자만 할 수 있습니다. 조회는 재직 중인 구성원도 할 수
있습니다. 구성원이 사장님 전용 기능을 요청하면 `403`, 매장 외부 사용자는 `404`를
반환합니다.

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
소유자만 할 수 있습니다. 조회는 재직 중인 구성원도 할 수 있습니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/v1/stores/{storeId}/recipes` | 레시피 등록 |
| `GET` | `/api/v1/stores/{storeId}/recipes` | 레시피 목록과 카테고리 조회 |
| `GET` | `/api/v1/stores/{storeId}/recipes/{recipeId}` | 레시피 상세 조회 |
| `PATCH` | `/api/v1/stores/{storeId}/recipes/{recipeId}` | 레시피 수정 |
| `DELETE` | `/api/v1/stores/{storeId}/recipes/{recipeId}` | 레시피 삭제 |
| `PUT` | `/api/v1/stores/{storeId}/recipes/{recipeId}/images/{slot}` | 레시피 사진 바꾸기 |
| `DELETE` | `/api/v1/stores/{storeId}/recipes/{recipeId}/images/{slot}` | 레시피 사진 빼기 |
| `POST` | `/api/v1/stores/{storeId}/recipe-scans` | 사진으로 레시피 초안 생성 |

레시피 등록은 `multipart/form-data`이며 `recipe` 파트에 JSON을 담습니다. 사진은
선택이며 `image` 파트에 메뉴 사진, `recipeImage` 파트에 레시피 사진을 담습니다.

레시피 사진은 메뉴 사진(`slot`=`menu`)과 레시피 사진(`slot`=`recipe`) 두 장입니다.
글 수정(`PATCH`)과 별도로, 사진은 `PUT .../images/{slot}`(`image` 파트)로 바꾸고
`DELETE .../images/{slot}`로 뺍니다. 사진은 Supabase Storage의 비공개 버킷
(`SUPABASE_STORAGE_BUCKET`)에 서버 키(`SUPABASE_SECRET_KEY`)로 저장합니다. 조회 응답의
`imageUrl`(메뉴 사진)과 `recipeImageUrl`(레시피 사진)은 6시간 동안 쓸 수 있는 주소이며,
사진이 없으면 `null`입니다. 주소 발급에 실패하면 레시피는 그대로 반환하고 사진 주소만
`null`로 둡니다.

| 사진 오류 | 응답 |
| --- | --- |
| 비어 있거나 10MB 초과 | `413 IMAGE_TOO_LARGE` |
| JPEG, PNG, WebP가 아님 (파일 내용으로 판별) | `415 UNSUPPORTED_IMAGE_TYPE` |
| 저장소 오류 | `503 STORAGE_UNAVAILABLE` |

레시피 스캔은 사장님만 사용할 수 있고 `multipart/form-data`의 `image` 파트로 사진을
보냅니다. JPEG, PNG, WebP, HEIC, HEIF를 10MB까지 받습니다. 사진과 초안은 저장하지
않으며, 사장님이 확인한 내용을 레시피 등록 API로 저장합니다. 읽지 못한 값은 `null`로
반환하고, 레시피로 읽을 수 없는 사진은 `422`를 반환합니다. 사진에 레시피가 여러 개면
맨 위의 하나만 읽고 `hasMoreRecipes: true`를 함께 반환합니다. 이때 FE는 한 장에 레시피
하나씩 찍도록 안내할 수 있습니다.

## AI 사수 채팅 API

AI 사수는 현재 매장의 매뉴얼과 레시피만 근거로 답합니다. 근거가 없으면 고정 안내문을
반환합니다. Gemini가 `429`나 `503`을 주면 한 번 재시도하고, 그래도 실패하면 `503`을
반환합니다. 실행하려면 `.env`에 `GEMINI_API_KEY`가 필요합니다.

질문할 때 같은 채팅방의 최근 메시지 6개(안내 메시지 제외, 메시지당 300자)를 함께
보내서 "그럼 따뜻한 건?" 같은 이어지는 질문을 이해합니다. 이전 대화는 질문의 뜻을
파악하는 데만 쓰고, 답의 근거는 매장 문서만 씁니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/v1/stores/{storeId}/assistant-chats` | 채팅방 생성 |
| `GET` | `/api/v1/stores/{storeId}/assistant-chats` | 내 채팅방 목록 조회 |
| `DELETE` | `/api/v1/stores/{storeId}/assistant-chats/{chatId}` | 채팅방 삭제 |
| `POST` | `/api/v1/stores/{storeId}/assistant-chats/{chatId}/messages` | 질문 전송과 답변 |
| `GET` | `/api/v1/stores/{storeId}/assistant-chats/{chatId}/messages` | 메시지 내역 조회 |

## 사장님께 물어보기 API

AI가 매뉴얼에서 답을 찾지 못한 답변(`not_found`)만 사장님께 넘길 수 있습니다. 넘긴
답변은 메시지 응답의 `ownerQuestion`에 상태가 표시되고, 사장님이 답하면 알바생
채팅에 `sender: "owner"` 메시지로 들어갑니다. 질문 목록과 답변은 사장님만 할 수
있습니다.

답변할 때 `addToManual: true`를 보내면 답변 저장과 매뉴얼 생성을 한 트랜잭션으로
처리합니다. 하나라도 실패하면 둘 다 저장되지 않습니다. 만들어진 매뉴얼은 다음 질문부터
AI 사수의 근거 문서가 되고, 일반 매뉴얼 API로 수정·삭제할 수 있습니다.

| 요청 필드 | 설명 | 비우면 |
| --- | --- | --- |
| `manualTitle` | 매뉴얼 제목 (최대 100자) | 질문 앞 30자 |
| `manualBody` | 매뉴얼 본문 (최대 5000자) | `질문: …` / `답변: …` 형식 |
| `manualCategoryId` | 같은 매장의 카테고리 | `물건 위치` 카테고리 (없으면 새로 만듦) |

`addToManual`이 `false`이면 위 필드는 무시합니다. 답변 응답의 `manualId`는 만들어진
매뉴얼 ID이고, 매뉴얼을 만들지 않았으면 `null`입니다.

`POST .../owner-questions/{questionId}/manual-draft`에 `{ "answer": "…" }`를 보내면
Gemini가 질문과 답변을 매뉴얼 제목·본문 초안(`{ "title", "body" }`)으로 정리합니다.
초안은 저장하지 않으며, 사장님이 확인·수정한 뒤 답변 API의 `manualTitle`,
`manualBody`로 저장합니다. 질문과 답변에 없는 내용은 쓰지 않도록 지시하고, 두 값은
지시가 아닌 자료로 전달합니다. AI 호출이 실패하면 `503 AI_UNAVAILABLE`을 반환합니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/v1/stores/{storeId}/assistant-chats/{chatId}/messages/{messageId}/owner-questions` | 질문 넘기기 |
| `GET` | `/api/v1/stores/{storeId}/owner-questions?status=asked` | 사장님 질문 목록 |
| `POST` | `/api/v1/stores/{storeId}/owner-questions/{questionId}/manual-draft` | 답변을 AI 매뉴얼 초안으로 정리 (저장 안 함) |
| `POST` | `/api/v1/stores/{storeId}/owner-questions/{questionId}/answer` | 사장님 답변 |

| 상황 | 응답 |
| --- | --- |
| 이미 넘긴 답변 | `409 OWNER_QUESTION_ALREADY_SENT` |
| `not_found`가 아닌 메시지 | `422 OWNER_QUESTION_NOT_ALLOWED` |
| 이미 답한 질문 | `409 OWNER_QUESTION_ALREADY_ANSWERED` |
| 다른 매장이거나 없는 `manualCategoryId` | `422` |

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

## 알림 API

목록을 조회할 때 기존 데이터(대타 요청, 사장님께 물어보기, 인수인계)와 하루 근무 변경 기록을
모아 최근 14일 알림을 최신 순으로 최대 50개 반환합니다. 서버 예약 작업이
없어서 서버가 잠들어도 동작합니다. 휴대폰 푸시는 없고 앱 안 알림입니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `GET` | `/api/v1/stores/{storeId}/notifications` | 배너, 알림 목록, 안 읽은 개수 |
| `POST` | `/api/v1/stores/{storeId}/notifications/read` | 지금까지의 알림 모두 읽음 (204) |

| 받는 사람 | `type` | 알림 | `target.kind` |
| --- | --- | --- | --- |
| 알바생 | `SUBSTITUTE_REQUESTED` | 나에게 온 대타 요청 (취소 제외) | `substitute_request` |
| 알바생 | `SUBSTITUTE_ACCEPTED` | 내가 보낸 대타 요청을 상대가 수락 | `substitute_request` |
| 알바생 | `SUBSTITUTE_REJECTED` | 내가 보낸 대타 요청을 상대가 거절 | `substitute_request` |
| 알바생 | `DAILY_SCHEDULE_CHANGED` | 사장님이 하루 근무를 바꿔 내 근무가 생기거나 빠지거나 바뀜 | `daily_schedule` |
| 알바생 | `OWNER_ANSWERED` | 사장님이 내 질문에 답함 | `assistant_chat` |
| 사장님 | `HANDOVER_CREATED` | 다른 사람이 인수인계를 남김 | `handover` |
| 사장님 | `OWNER_QUESTION_ASKED` | 알바생이 질문을 넘김 | `owner_question` |

- 읽음은 알림 화면을 연 시각 하나로 관리합니다. 그 시각 이전 알림은 `isRead: true`입니다.
- `banner`는 근무가 있는 알바생과 사장님에게 내려갑니다. 오늘(한국 시간) 근무 시작 30분 전부터 퇴근 전까지,
  최근 7일 인수인계 중 아직 체크되지 않은 항목을 담습니다. 그 밖의 시간에는 `null`입니다.
- 근무 시간은 고정 스케줄, 대타, 사장님의 하루 근무 조정, 매장 쉬는 날을 근무표 달력과 같은 규칙으로 반영합니다.
- 하루 근무 변경 알림은 `PUT`·`DELETE /schedule-calendar/{workDate}` 때 바뀌기 전후 근무를 비교해
  `schedule_change_notices`에 기록합니다. 바꾼 사장님 본인에게는 가지 않습니다.
- 사장님이나 재직 중인 구성원이 아니면 `404`입니다.

## 예상 급여 API

예상 급여는 AI가 아니라 규칙 기반 코드로 계산합니다. 사장님이 확정한(`published`)
스케줄에서 내게 배정된 근무 시간만 근거로 쓰며, 실제 출퇴근 기록이 아니므로 응답의
`isEstimate`는 항상 `true`입니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `GET` | `/api/v1/stores/{storeId}/payroll/estimates/me?month=YYYY-MM` | 내 한 달 예상 급여 (알바생) |
| `GET` | `/api/v1/stores/{storeId}/payroll/estimates?month=YYYY-MM` | 직원별 예상 급여 목록 (사장님) |
| `GET` | `/api/v1/stores/{storeId}/payroll/estimates/{estimateId}?month=YYYY-MM` | 예상 급여 상세 |

- 근무 시간은 근무표 달력과 같은 규칙으로 계산합니다. 매장 쉬는 요일과 공휴일 휴무일의 고정 근무는 빠지고,
  사장님이 그날 따로 정한 근무는 들어갑니다.
- 예상 급여는 저장하지 않고 조회할 때 계산합니다. 그래서 `estimateId`는 구성원 ID(`memberId`)와 같습니다.
- `estimates/me`는 재직 중인 알바생만 조회할 수 있고, 구성원이 아닌 사장님은 `403`을 받습니다.
- 목록은 사장님만 조회할 수 있으며 재직 중인 직원 전체를 가입 순서로, 근무가 없는 직원도 0원으로 반환합니다.
  목록 항목에는 `workDays`가 없고 상세에만 있습니다.
- 상세는 사장님은 모든 재직 직원, 알바생은 본인만 조회할 수 있습니다. 다른 직원 것을 요청한 알바생은 `403`,
  퇴사했거나 없는 구성원은 `404`입니다.

- `month`를 생략하면 한국 시간 기준 이번 달입니다.
- 기본급은 근무시간 × 시급입니다. 휴게시간은 스케줄에 없어 빼지 않습니다.
- 주휴수당은 월요일부터 일요일까지 한 주의 근무가 15시간 이상이면
  `min(주 근무시간, 40) ÷ 40 × 8 × 시급`이며 10원 단위로 반올림합니다. 월을 걸친 주는
  일요일이 속한 달에 넣습니다. 공휴일·연장·야간 가산은 계산하지 않습니다.
- 공제는 구성원의 `taxType`을 따릅니다. `none`은 0%, `3.3`은 3.3%, `ins`는 2026년
  근로자 부담 4대보험 합계 9.7174%이며 10원 단위로 반올림합니다.
- `workDays[].status`는 근무 종료 시각이 지났으면 `worked`, 아니면 `planned`입니다.
- `payday`는 매장 급여일이며 31은 말일입니다. `aiNote`는 아직 `null`입니다.
- 재가입하면 구성원의 시급이 새 값으로 바뀌므로 지난달 금액도 현재 시급으로 계산됩니다.
