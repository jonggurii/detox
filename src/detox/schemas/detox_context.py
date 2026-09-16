from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ReminderTone(str, Enum):
    POLITE_FORMAL = "polite_formal"
    FRIENDLY_CASUAL = "friendly_casual"
    HUMOROUS = "humorous"


class RoundInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    round: int = Field(ge=1, description="차수 번호")
    cost: int = Field(ge=0, description="해당 차수의 총 결제 금액(원)")
    excluded_members: list[str] = Field(
        default_factory=list,
        description="해당 차수에 참석하지 않거나 늦게 온 사람 이름",
    )


class SettlementRequestContext(BaseModel):
    """Structured output contract for an N-bbang settlement request."""

    model_config = ConfigDict(extra="forbid")

    total_rounds: int | None = Field(
        default=None,
        ge=1,
        description="전체 차수 수. 발화에서 확인할 수 없으면 null.",
    )
    payer_name: str | None = Field(
        default=None,
        description="선결제자 이름. 발화에서 확인할 수 없으면 null.",
    )
    rounds_info: list[RoundInfo] = Field(
        default_factory=list,
        description="차수별 비용과 제외 인원 정보",
    )
    reminder_tone: ReminderTone | None = Field(
        default=None,
        description="독촉 메시지 톤. 명시되지 않으면 null.",
    )