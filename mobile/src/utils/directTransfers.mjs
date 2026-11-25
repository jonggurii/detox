/** Device-local direct transfer validation. No server calculation or bank transfer. */
export function validateDirectTransfers(totalText, participants, rows) {
  const parse = value => {
    const raw = typeof value === 'string' ? value.replace(/,/g, '').trim() : '';
    if (!/^\d+$/.test(raw)) return null;
    const amount = Number(raw);
    return Number.isSafeInteger(amount) ? amount : null;
  };
  const target = parse(totalText);
  const people = new Set(participants);
  const transfers = [];
  let sum = 0;
  let valid = Array.isArray(rows) && rows.length > 0 && target !== null && target > 0;
  for (const row of rows || []) {
    const amount = parse(row.amount);
    if (!row.from || !row.to || row.from === row.to || !people.has(row.from) || !people.has(row.to) || amount === null || amount <= 0) {
      valid = false;
    }
    if (amount !== null && Number.isSafeInteger(sum + amount)) sum += amount;
    else valid = false;
    transfers.push({from_participant:row.from, to_participant:row.to, amount});
  }
  return {valid:valid && sum === target, sum, total:target, transfers};
}
