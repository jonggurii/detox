"""OCR 후보만 추출한다. 미정 금액·총액은 계산해서 채우지 않는다."""
import math
import re
import unicodedata

MAX_AMOUNT = 2**53 - 1
MONEY = re.compile(r"(?:0|[1-9][0-9]*|[1-9][0-9]{0,2}(?:,[0-9]{3})+)(?:\s*원)?\Z")
TOTAL_LABELS = ("합계금액", "총결제금액", "총결제", "총합계", "결제금액", "받을금액", "승인금액", "청구금액", "합계", "총액")
TOTAL = re.compile(r"^(?:(?:신용카드|카드|현금)\s*)?(" + "|".join(r"\s*".join(label) for label in TOTAL_LABELS) + r")\s*[:：]?\s*(.*)$")
IGNORE = re.compile(r"사업자|등록번호|대표|전화|TEL|주소|가맹점|승인번호|카드번호|할부|부가세|과세|면세|공급가|받은돈|거스름돈|단말기|전표|바코드|상품코드", re.I)
PAYMENT = re.compile(r"^(?:신용카드|체크카드|카드|현금|간편결제|CASH|CREDIT|VISA|MASTER|VAT|TAX|SUBTOTAL|소계|중간합계|총수량|합계수량)", re.I)
FOREIGN = re.compile(r"\b(?:USD|EUR|JPY|CNY|RMB)\b|[$€¥]|달러|엔화|위안", re.I)
NOISE = re.compile(r"[0-9]{2,4}[-./년][ ]*[0-9]{1,2}[-./월][ ]*[0-9]{1,2}|[0-9]{2,3}-[0-9]{2,4}-[0-9]{4,5}|[0-9]{4}[-*]+[0-9]{4}")
ADJUSTMENT = re.compile(r"할인|환불|취소|반품|쿠폰|적립|포인트|[−-][ ]*[0-9]|[0-9]+\.[0-9]+|[0-9]+%")
HEADER = re.compile(r"품목명|상품명|메뉴명|품명|품목|상품|메뉴|단가|수량|금액")


def parse_amount(value):
    text = value.strip()
    if text.startswith("₩"):
        text = text[1:].strip()
    if not MONEY.fullmatch(text):
        return None
    digits = text.removesuffix("원").strip().replace(",", "")
    if len(digits) > 16:
        return None
    amount = int(digits)
    return amount if amount <= MAX_AMOUNT else None


def _box(block):
    value = block.get("box")
    if value is None:
        value = block.get("bbox")
    try:
        if not isinstance(value, (list, tuple)) or len(value) != 4:
            return None
        if isinstance(value[0], (list, tuple)):
            xs, ys = zip(*value)
            value = [min(xs), min(ys), max(xs), max(ys)]
        value = [float(v) for v in value]
        x1, y1, x2, y2 = value
        if not all(math.isfinite(v) for v in value) or x2 <= x1 or y2 <= y1:
            return None
        return value
    except (TypeError, ValueError):
        return None


def _lines(output):
    raw = output.get("text")
    raw = raw if isinstance(raw, str) else ""
    blocks = output.get("blocks")
    blocks = blocks if isinstance(blocks, list) else []
    blocks = [b for b in blocks if isinstance(b, dict) and isinstance(b.get("text"), str) and b["text"].strip()]
    positioned = [(b["text"].strip(), _box(b)) for b in blocks]
    if not positioned or any(box is None for _, box in positioned):
        return raw.splitlines() if raw.strip() else [text for text, _ in positioned]
    rows = []
    for text, box in sorted(positioned, key=lambda p: ((p[1][1] + p[1][3]) / 2, p[1][0])):
        center, height = (box[1] + box[3]) / 2, box[3] - box[1]
        if rows and abs(rows[-1]["y"] - center) <= 0.4 * min(height, rows[-1]["h"]):
            rows[-1]["parts"].append((box[0], text))
        else:
            rows.append({"y": center, "h": height, "parts": [(box[0], text)]})
    return [" ".join(text for _, text in sorted(row["parts"])) for row in rows]


def extract_receipt_fields(ocr_output):
    lines = [re.sub(r"\s+", " ", unicodedata.normalize("NFKC", line)).strip()
             for line in _lines(ocr_output)]
    items, totals, unparsed, warnings = [], [], [], []
    columns, pending_total = None, None
    for line in filter(None, lines):
        compact = line.replace(" ", "")
        if pending_total:
            amount = parse_amount(line)
            if amount is not None:
                totals.append({"amount": amount, "source": pending_total + " / " + line})
                pending_total = None
                continue
            unparsed.append(pending_total)
            pending_total = None
        if ADJUSTMENT.search(line) or FOREIGN.search(line):
            unparsed.append(line)
            warnings.append("할인·환불·소수·외화 등 자동 적용하지 않은 줄이 있습니다.")
            continue
        match = TOTAL.fullmatch(line)
        if match:
            tail = match.group(2)
            if not tail:
                pending_total = line
            else:
                amount = parse_amount(tail)
                if amount is None:
                    unparsed.append(line)
                else:
                    totals.append({"amount": amount, "source": line})
            continue
        if IGNORE.search(compact) or NOISE.search(line) or PAYMENT.search(compact):
            continue
        header = HEADER.findall(compact)
        if header and header[0] not in {"단가", "수량", "금액"} and "금액" in header and not re.search(r"[0-9]", line):
            columns = header[1:]
            continue
        tokens = line.split()
        if len(tokens) >= 2 and tokens[-1] == "원":
            tokens[-2:] = [tokens[-2] + "원"]
        numeric = []
        while tokens and parse_amount(tokens[-1]) is not None:
            numeric.insert(0, tokens.pop())
        name = " ".join(tokens).strip()
        if not name or not re.search(r"[가-힣A-Za-z]", name) or not numeric:
            unparsed.append(line)
            continue
        if any(re.fullmatch(r"[0-9OolI,./+−-]+(?:원|개)?", token) for token in tokens):
            unparsed.append(line)
            continue
        if len(numeric) == 1 and (columns is None or columns == ["금액"]):
            amount = parse_amount(numeric[0])
        elif columns and len(numeric) == len(columns) and columns.count("금액") == 1 and set(columns) <= {"단가", "수량", "금액"}:
            amount = parse_amount(numeric[columns.index("금액")])
        else:
            unparsed.append(line)
            warnings.append("단가·수량·항목 금액의 구분이 불명확한 줄은 직접 입력해 주세요.")
            continue
        items.append({"name": name, "amount": amount, "source": line})
    if pending_total:
        unparsed.append(pending_total)
    unique = {candidate["amount"] for candidate in totals}
    total = next(iter(unique)) if len(unique) == 1 else None
    if len(unique) > 1:
        warnings.append("서로 다른 총액 후보가 있습니다. 사진에서 최종 금액을 확인해 주세요.")
    if total is None:
        warnings.append("영수증 총액을 자동 확정하지 않았습니다. 품목 합계로 대신 채우지 않습니다.")
    return {"items": items, "total_amount": total, "total_candidates": totals,
            "unparsed_lines": unparsed, "warnings": list(dict.fromkeys(warnings))}
