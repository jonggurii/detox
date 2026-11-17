# Evals 실행 결과

`*.json`: 매 실행별 케이스 출력·오류·기대값·검사 결과·메타데이터. `history.csv`: 실행마다 한 행.

**주의** `mode=stored`, `ai_quality_measured=false`인 기록은 사람이 작성한 출력으로 수행한 평가 하니스 검증이며 **Gemini 정확도 결과가 아니다**.
실제 모델 성능은 `mode=live`, `ai_quality_measured=true`인 실행에서만 해석한다.

저장 출력 기준선은 코드의 결함 주입 검증을 재현하는 용도다. commit이 unavailable이면 ZIP에서 실행한 것으로 실제 커밋 식별자가 없다.
