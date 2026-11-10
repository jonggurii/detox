"""확인한 OCR 입력의 형식·원문·정산 초안을 한곳에서 만든다."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

MAX_AMOUNT = 2**53 - 1
Amount = Annotated[int, Field(strict=True, ge=0, le=MAX_AMOUNT)]
Name = Annotated[str, Field(strict=True, min_length=1, max_length=100)]


class ReceiptItemInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, max_length=200)
    amount: Amount | None = None

    @field_validator("name")
    @classmethod
    def trim_name(cls, value):
        return (value.strip() or None) if value is not None else None


class ReceiptDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_review_revision: int = Field(default=0, ge=0, strict=True)
    reviewed_by: Name
    image_checked: StrictBool
    items: list[ReceiptItemInput] = Field(max_length=300)
    total_amount: Amount | None = None
    receipt_total_amount: Amount | None = None
    participants: list[Name] = Field(default_factory=list, max_length=100)
    payer_name: Name | None = None
    split_method: Literal["equal", "explicit_amount"] | None = None
    note: str = Field(default="", max_length=2000)

    @field_validator("reviewed_by", "payer_name")
    @classmethod
    def validate_name(cls, value):
        if value is None:
            return None
        if not value.strip():
            raise ValueError("이름을 공백으로 입력할 수 없습니다.")
        return value.strip()

    @field_validator("participants")
    @classmethod
    def validate_people(cls, values):
        values = [v.strip() for v in values]
        if any(not v for v in values) or len(values) != len(set(values)):
            raise ValueError("분담 대상자의 빈 이름·중복 이름을 확인해 주세요.")
        return values

    @model_validator(mode="after")
    def validate_review(self):
        if not self.image_checked:
            raise ValueError("사진과 입력값을 대조한 뒤 확인해 주세요.")
        if sum(i.amount or 0 for i in self.items) > MAX_AMOUNT:
            raise ValueError("품목 합계가 정확히 다룰 수 있는 정수 범위를 넘습니다.")
        return self

    def content(self):
        return self.model_dump(exclude={"expected_review_revision"})


def manual_context(body):
    names = list(body.participants)
    # 결제자는 관련 인물에만 등록한다. 분담 대상으로 추가하지 않는다.
    if body.payer_name and body.payer_name not in names:
        names.append(body.payer_name)
    return {
        "participants": names,
        "expenses": [{"payer_name": body.payer_name, "total_amount": body.total_amount,
            "receipt_total_amount": body.receipt_total_amount,
            "items": [item.model_dump() for item in body.items]}],
        "split_rules": [{"expense_index": 0, "item_index": index,
            "method": body.split_method, "participant_names": body.participants or None}
            for index in range(len(body.items))],
    }


def reviewed_evidence(body):
    def money(value):
        return "미정" if value is None else f"{value:,}원"
    lines = ["[사용자가 대조한 영수증 입력]"]
    lines.extend(f"품목 {index + 1}: {item.name or '품목명 미정'} / 항목 전체 금액: {money(item.amount)}"
                 for index, item in enumerate(body.items))
    lines.extend([f"영수증에 표시된 총액: {money(body.receipt_total_amount)}",
                  f"사용자가 입력한 실제 결제 총액: {money(body.total_amount)}"])
    if body.note.strip():
        lines.append("추가 확인 메모: " + body.note.strip())
    evidence = "\n".join(lines)
    if len(evidence) > 24000:
        raise ValueError("영수증 근거가 24,000자를 넘습니다. 품목명과 메모를 줄여 주세요.")
    return evidence


def condition_text(body):
    lines = []
    if body.participants:
        lines.append("비용 분담 대상: " + ", ".join(body.participants))
    if body.payer_name:
        lines.append("먼저 결제한 사람: " + body.payer_name)
    if body.split_method == "equal":
        lines.append("입력한 분담 대상자가 각 품목을 균등 분담하기로 선택함.")
    elif body.split_method == "explicit_amount":
        lines.append("개인별 금액 지정 방식. 구체적인 개인별 금액은 추가 확인 필요.")
    return "\n".join(lines) or "영수증에서 직접 입력한 정산. 결제자와 분담 조건은 추가 확인 필요."
