# 팀 디톡스 (Team Detox)

> **2026 AI 캡스톤 디자인 프로젝트**  
> 실사용자 기반 AI 제품 전 주기 개발 (Discover → Define → Develop → Deliver)

---

## 👥 팀 소개

| 이름 | 
| **팀원 임종혁** | 
| **팀원  송건** |  
* **멘토 ** 

---

## 🛠️ 개발 및 AI 협업 환경 (과제 0 검증)

* **언어 & 프레임워크:** Python 3.11+, FastAPI, Flutter/React Native (선택)
* **LLM & Agent Framework:** OpenAI / Anthropic API, Structured Outputs
* **AI 코딩 에이전트 환경:**
  * Claude Code / OpenAI Codex CLI 설치 완료
  * 에이전트 실행 및 단위 테스트 동작 확인 완료 

## 📁 디렉토리 구조 (초안)

```text
├── docs/                     # 발견/정의 단계 산출물
│   ├── 01_interview_protocol.md  # Mom Test 인터뷰 질문지 v1
│   ├── 02_interview_logs/        # 인터뷰 전사본 (개방 코딩 태그)
│   └── 03_ontology.yaml          # 미니 도메인 온톨로지 정의서
├── src/                      # 애플리케이션 소스 코드
├── evals/                    # AI 모델 검증 및 벤치마크 테스트셋
├── AGENTS.md                 # AI 코딩 에이전트 지휘 규칙 및 제약
└── README.md
