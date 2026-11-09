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
| `POST` | `/api/v1/stores/{storeId}/recipe-scans` | 사진으로 레시피 초안 생성 |

레시피 등록은 `multipart/form-data`이며 `recipe` 파트에 JSON을 담습니다. 파일
저장소가 정해지기 전까지 `images` 파트를 보내면 `501`을 반환합니다.

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
있습니다. 답변을 매뉴얼에 추가하는 기능(`addToManual: true`)은 아직 지원하지 않아
`501`을 반환합니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `POST` | `/api/v1/stores/{storeId}/assistant-chats/{chatId}/messages/{messageId}/owner-questions` | 질문 넘기기 |
| `GET` | `/api/v1/stores/{storeId}/owner-questions?status=asked` | 사장님 질문 목록 |
| `POST` | `/api/v1/stores/{storeId}/owner-questions/{questionId}/answer` | 사장님 답변 |

| 상황 | 응답 |
| --- | --- |
| 이미 넘긴 답변 | `409 OWNER_QUESTION_ALREADY_SENT` |
| `not_found`가 아닌 메시지 | `422 OWNER_QUESTION_NOT_ALLOWED` |
| 이미 답한 질문 | `409 OWNER_QUESTION_ALREADY_ANSWERED` |
| 매뉴얼 추가 요청 | `501 ADD_TO_MANUAL_NOT_SUPPORTED` |

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

## 예상 급여 API

예상 급여는 AI가 아니라 규칙 기반 코드로 계산합니다. 사장님이 확정한(`published`)
스케줄에서 내게 배정된 근무 시간만 근거로 쓰며, 실제 출퇴근 기록이 아니므로 응답의
`isEstimate`는 항상 `true`입니다.

| Method | 경로 | 설명 |
| --- | --- | --- |
| `GET` | `/api/v1/stores/{storeId}/payroll/estimates/me?month=YYYY-MM` | 내 한 달 예상 급여 (알바생) |
| `GET` | `/api/v1/stores/{storeId}/payroll/estimates?month=YYYY-MM` | 직원별 예상 급여 목록 (사장님) |
| `GET` | `/api/v1/stores/{storeId}/payroll/estimates/{estimateId}?month=YYYY-MM` | 예상 급여 상세 |

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
