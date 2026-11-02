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
