<div align="center">

<img src="docs/images/crewbean-cover.jpeg" width="100%" alt="crewBean — 혼자 막막했던 근무를 함께하는 크루로" />

<br />

개인 카페 신입 알바생에게 **우리 매장 매뉴얼 · 레시피로 답하고**,<br />
모르는 건 **사장님께 넘기는** AI 사수의 백엔드

<sub>2026 AI 우왕톤 · 13팀 F4 · 주제 “AI는 동료가 될 수 있는가”</sub>

<br />

[서비스 열기](https://woowangthon-team-13-fe.vercel.app) &nbsp;·&nbsp;
[시연 영상](https://www.youtube.com/watch?v=tNBlgXNmUDY) &nbsp;·&nbsp;
[Frontend 저장소](https://github.com/woowangthon/WOOWANGTHON_TEAM_13_FE)

</div>

---

## 한눈에 보기

| | |
| --- | --- |
| **누구의 문제?** | 계속 묻기 어려운 개인 카페 **신입 알바생**, 같은 질문에 반복해서 답하는 **사장님** |
| **crewBean은?** | 매장 문서를 근거로 답하고 **출처를 표시**, 찾지 못하면 사장님께 질문 전달 |
| **BE의 역할** | 매장별 권한·데이터 관리, AI 응답·출처 검증, 근무·예상 급여 계산, 알림 |
| **사람이 하는 일** | 매장 지식 등록, AI 초안 검토, 미해결 질문 답변과 매뉴얼 저장 결정 |

→ 자세히: [문제 · 해법 · 주요 기능](docs/problem-and-solution.md)

## 주요 기능

| 영역 | 백엔드에서 하는 일 |
| --- | --- |
| **인증 · 매장 · 구성원** | Supabase JWT 검증, 사업자 상태조회, 직원 초대·가입·퇴사 처리 |
| **AI 사수 · 사장님께 물어보기** | 문서 기반 답변과 출처 확인, 질문 전달, 답변의 매뉴얼 등록 |
| **레시피 · 매뉴얼** | 매장별 문서 CRUD, 이미지 관리, 사진 스캔 초안 |
| **인수인계** | 체크리스트 초안, 기록·체크, 하루 AI 요약 |
| **근무 · 예상 급여** | 고정 근무·대타·하루 조정, 근무표 기반 급여 계산 |
| **알림 · 통계** | 앱 내 알림, 질문·답변 Web Push, 주간 AI 사수 답변 통계 |

## 기술 설계

```text
React · PWA ──Bearer 토큰──▶ FastAPI ──▶ PostgreSQL · Storage (Supabase)
     │                         ├─▶ Gemini (답변 · 초안 · 요약 · 사진 해석)
     └─ Supabase Auth          ├─▶ 국세청 사업자 상태조회
                               └─▶ Web Push
```

**AI 사수** — 질문 + 현재 매장 문서 → Gemini의 구조화된 응답 → 서버의 출처 ID 검사 → 답변 또는 `not_found` → 사용자가 사장님께 전달.

| API · 검증 | DB · 인증 | AI · 연동 | 품질 · 배포 |
| --- | --- | --- | --- |
| Python 3.12 · FastAPI · Pydantic | SQLAlchemy Async · PostgreSQL · Alembic · Supabase Auth | Gemini · HTTPX · Supabase Storage · Web Push | pytest · Ruff · mypy · Render |

→ 자세히: [아키텍처 · 프로젝트 구조](docs/architecture.md) · [기술 선택과 트레이드오프 (ADR)](docs/adr.md)

## 실행 · 확인 방법

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# .env에 DB·Supabase 인증 설정 입력 (AI 등은 사용할 기능에 맞춰 추가)
alembic upgrade head
uvicorn app.app:app --reload
```

**API 문서:** [localhost:8000/docs](http://localhost:8000/docs) · **서버 확인:** `GET /api/v1/health/live` → `{"status":"ok"}`.

보호된 API에는 Supabase 세션의 access token이 필요합니다. Health Check는 DB·AI 연결까지 검사하지 않습니다.

→ 자세히: [환경변수 · 실행 방법](docs/getting-started.md) · [인증 · 핵심 기능 확인 · 한계](docs/verification.md)

## 문서

| 문서 | 내용 |
| --- | --- |
| [문제 · 해법 · 주요 기능](docs/problem-and-solution.md) | 사용자 문제, 핵심 흐름, 사람과 AI의 역할 |
| [기술 설계](docs/architecture.md) | 전체 구성도, AI 처리 흐름, 계층·프로젝트 구조 |
| [ADR](docs/adr.md) | 선택한 기술과 대안, 선택 이유, 트레이드오프 |
| [실행 방법](docs/getting-started.md) | 설치, 환경변수, 마이그레이션, 서버 실행 |
| [확인 방법과 한계](docs/verification.md) | 인증·권한·기능 검증 시나리오, 테스트 명령, 미지원 범위 |

## 팀 F4

| 백엔드 | 담당 |
| --- | --- |
| [이은교 · @euungyo](https://github.com/euungyo) | 인증 · 매장 · 구성원 · 근무 · 푸시 |
| [남연서 · @yeontteo](https://github.com/yeontteo) | AI · 매뉴얼 · 레시피 · 인수인계 · 급여 |

프론트엔드: [류민지](https://github.com/ryu-min-ji) · [최나현](https://github.com/nahyun2). [팀과 협업 방식](https://github.com/woowangthon/WOOWANGTHON_TEAM_13_FE/blob/main/docs/team.md)
