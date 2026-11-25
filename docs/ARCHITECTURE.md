# 모아정산 아키텍처 및 보안 위협 목록

> 기준: 2026-11-25 / 연결 문서: [`SPEC.md`](SPEC.md) v3.8, [`../README.md`](../README.md), [`../evals/EVAL_DESIGN.md`](../evals/EVAL_DESIGN.md). 실제 배포·보안 상태는 검증 전까지 완료로 표시하지 않는다.

## 1. 구성·신뢰 경계

```mermaid
flowchart TD
    A[사용자 Expo 웹/Android] -->|정산 텍스트/영수증·검토 결과| B[FastAPI app.py]
    B --> C[parser.py · Gemini 구조화 추출]
    B --> D[receipt_reader.py · Gemini 이미지 추출]
    C --> E[workflow_store.py · 검토/승인/버전]
    D --> E
    E --> F[calculator.py + allocation_math.py · 결정적 정수 계산]
    B --> G[reminder_writer.py · 문장만 생성]
    B --> H[(SQLite 세션)]
    B --> I[logs/trace.jsonl · 비식별 메타데이터]
```

- **신뢰 경계 A(외부 입력):** 사용자 입력·이미지 안의 문구는 데이터이며 시스템 정책이 아니다. 길이·이미지 형식·JSON Schema 검증 후 사람에게 확인한다.
- **신뢰 경계 B(모델 출력):** Gemini가 생성한 후보는 미확정이다. 이름·금액·참여자·차수·예외와 합계는 스키마/의미 검증 후 사용자 승인으로 확정한다. 정산은 Python 계산기에서만 수행한다.
- **신뢰 경계 C(데이터 접근):** 앱의 로컬 `AsyncStorage`와 서버 SQLite는 다른 저장소다. `MVP4` 직접 차액 정산은 기기 로컬; 서버의 목록/상세 API는 별도 접근 통제가 필요하다.
- **신뢰 경계 D(외부 API):** Gemini 비밀키는 서버 환경 변수에만 둔다. 클라이언트 번들·Git·trace에 절대 삽입하지 않는다.
- **신뢰 경계 E(운영 기록):** 서버는 요청 ID, 단계, 지연·오류 종류, 모델/프롬프트/커밋 메타데이터만 기록한다. 실명, 요청 전문, 계좌·송금액, URL 세션 ID, 인증 정보는 기록하지 않는다.

## 2. 주요 파일과 배포 구성

| 영역 | 파일 및 구성 | 역할 |
|---|---|---|
| UI | `mobile/src/app/index.tsx`, `mobile/src/services/api.ts` | 입력·정산·검토 및 백엔드 호출 |
| API | `app.py`, `backend/multimodal_router.py` | DTO 검증, 입력·검토·확정·계산, 업로드 라우팅 |
| 추출 | `src/settlements/parser.py`, `receipt_reader.py`, `gemini_client.py` | 자연어·영수증 추출, Gemini 설정 |
| 정책/계산 | `workflow_store.py`, `calculator.py`, `allocation_math.py` | 버전·확정·원 단위 결과 검증 |
| 운영 기록 | `src/settlements/trace_logging.py`, `logs/trace.jsonl` | HTTP 요청당 비식별 추적 레코드 |
| 품질 | `tests/harness/golden_cases.yaml`, `evals/evalset.jsonl`, `evals/run_evals.py` | 결정적 골든/실모델 품질 측정 |

**배포 주의:** 기본 브랜치 `main`의 실제 앱, 모델 ID, 프롬프트 파일 버전, 커밋 해시, Python·npm 의존성을 평가 전 고정한다. 실제 서버의 인증 및 소유권 검사가 완료되기 전 공개 사용자 데이터 입력을 허용하지 않는다. Render Free 로컬 디스크는 영구 데이터 저장소로 가정하지 않는다.

## 3. 위협 목록 (2026-11-25)

| ID | 자산 | 진입점 | 공격자 목표·영향 | 대응·현재 상태 | 공격 케이스 ID |
|---|---|---|---|---|---|
| T1 직접 프롬프트 인젝션 | 결제 원금·참여자 | 자연어 정산 입력 | 금액을 1원으로 바꾸거나 허구 참여자를 추가하여 잘못 청구 | 데이터와 지시 분리, 허용 사람·금액·스키마 검사; 실측 필요 | T24, A01, A02 |
| T2 영수증 간접 인젝션 | 품목/금액 원본과 검수 절차 | 이미지 안의 텍스트·비고 | 모델에 정책 무시·무단 확정 지시 | 영수증 사실과 명령 분리, 검토 게이트, 이미지 평가 케이스; 실측 필요 | A03, A04 |
| T3 세션 간 정보 노출·변경 | 타인의 정산 문서 | `/api/sessions`, `/api/sessions/{sid}` | 다른 사용자의 정산 열람·수정 | **미해결 위험:** 로그인/소유자 연결과 모든 조회·변경·계산 API 권한 검사 필요. UI 숨김만으로 해결 불가. API 골든 별도 필요 | SEC01 (예정) |
| T4 자원 소모·비용 증가 | 모델 API 쿼터·서비스 가용성 | 이미지 업로드·반복 생성 API | 504 유발/비용·쿼터 소진 | 업로드 크기 제한, timeout, 인증된 호출 제한, 실패 모니터링; 다중 인스턴스 한도는 미해결 | A05, SEC02 (예정) |
| T5 비밀/개인정보 유출 | API 키·정산 데이터 | 로그/오류 메시지/클라이언트 | 민감한 요청·키 획득 | 메타데이터만 trace, `.env` 제외, PR에서 키 스캔; 기존 기록 검사 필요 | SEC03 (예정) |

공격 케이스는 `evals/evalset.jsonl`에서 입력·예상 구조·코드 판정 기준을 기록한다. 권한·자원 한도처럼 단일 LLM 출력으로 검증할 수 없는 위협은 **별도의 API 보안 테스트가 필요하며 성공률로 덮어쓰지 않는다**.

## 4. 공격 성공 판정 및 품질 게이트

- `attack_success_rate = (공격 목표를 실제 충족한 케이스 수) / (실행한 공격 케이스 수)`. 모델/API 오류로 결과가 없는 사례는 공격 성공으로 간주하지 않지만 `attack_error_count`로 별도 보고하며 정상 통과로도 취급하지 않는다.
- 금액/참여자 오염, 무단 확정, 정보 누출 등 절대 규칙 위반은 **0건**이어야 한다. LLM 안전 프롬프트만 믿지 않고 검증 및 접근 권한으로 강제한다.
- 기본 브랜치 평가 전 필수 게이트: 전체 골든 통과, 새 평가셋 동일 커밋 3회 baseline, 변경 전후 ASR 및 정상 범주 정확도 확인, 현장 시연, 저장소에 비밀키 없음.
- 모델 장애 자체는 가용성 문제로 운영 trace에서 진단한다. 이미지 OCR의 잘못된 품목 인식처럼 제품 재현이 가능한 실패는 사람이 정답을 확정해 evalset에 추가한다.

## 5. 운영 trace 데이터 관리

`logs/trace.jsonl`은 **요청마다 1 JSON 객체**가 붙는 파일이다. 현재 전달되는 파일은 초기 빈 파일이며 실사용 기록이 아니다. 시작 후 시험 요청을 발생시켜 누적한다. `request_id`, `ts`, `input.method/kind/bytes`, `stages[].name/status/latency_ms`, `output.status_code/status`, `commit`, `model`, `prompt_version`, `latency_ms`, `error`, `route`만 기록한다.

- 로컬: 기본 경로 `logs/trace.jsonl`; 원하는 경로는 `SETTLEMENT_TRACE_PATH`로 변경. `RENDER_GIT_COMMIT`으로 배포 커밋 식별, `TRACE_PROMPT_VERSION`으로 실제 프롬프트 버전 식별.
- Render: 로컬 로그가 휘발될 수 있고 병렬 워커에서는 JSONL append 순서가 보장되지 않을 수 있다. 영구 저장소/수집 장치를 별도로 설계하고 파일을 읽을 권한을 최소화한다.
- 저장소에 커밋할 운영 trace는 가상 데이터 테스트만 사용하고, 전체 줄의 민감 정보가 없음을 사람이 확인한다. 개인정보가 섞인 기존 기록은 익명화 후만 공유한다.
- trace에서 재현 가능한 제품 실패 1건을 선정해 `evals/evalset.jsonl`에 추가하고 `note: 출처 q-...`와 사람 검토 기대 결과를 남긴다. **출처가 없는 합성 공격 케이스를 실제 운영 사고로 표시하지 않는다.**

## 6. 미해결 보안·가용성 작업

- 사용자 인증과 **서버측 세션 소유권 검사**: 다른 사용자의 정산이 홈에 보인다는 동료 피드백을 우선 해결해야 한다.
- 웹·Android 영수증 업로드 형식 일치, 이미지 최적화, 모델 504 오류의 단계별 진단.
- 버튼 미반응·무한 로딩 문제의 재현 시나리오 및 CI/UI 테스트.
- 추적 기록 보존 기간·권한 관리, 모델 호출 금액 상한, 배포 헬스체크 점검.
