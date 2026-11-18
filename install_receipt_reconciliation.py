#!/usr/bin/env python3
"""Install conservative receipt reconciliation without replacing current project files."""
from pathlib import Path
from datetime import datetime
import shutil
import sys
ROOT=Path.cwd()
PARSER=ROOT/'src/settlements/parser.py'
MODULE=ROOT/'src/settlements/receipt_reconciliation.py'
SOURCE=Path(__file__).resolve().with_name('receipt_reconciliation.py')
IMPORT='from .receipt_reconciliation import reconcile_reviewed_receipts'
ANCHOR='        def normalize_explicit_amount_rules(context):'
INSERT='        # Preserve reviewed receipt items and reconcile only explicitly scoped equal rules.\n        reconciled = reconcile_reviewed_receipts(\n            context.model_dump(exclude_unset=True), supplied_evidence, text\n        )\n        context = validate_context_data(reconciled, schema=schema)\n\n'
def main():
    if not PARSER.is_file() or not SOURCE.is_file():
        raise RuntimeError('parser.py or receipt_reconciliation.py is missing')
    original=PARSER.read_text(encoding='utf-8-sig')
    if IMPORT in original or MODULE.exists():
        raise RuntimeError('Already installed or module exists; no changes made')
    if original.count(ANCHOR)!=1:
        raise RuntimeError('parser.py normalization anchor differs; no changes made')
    if 'from .gemini_client import get_client, get_model' not in original:
        raise RuntimeError('Unknown parser.py import structure; no changes made')
    updated=original.replace('from .gemini_client import get_client, get_model', 'from .gemini_client import get_client, get_model\n'+IMPORT,1)
    updated=updated.replace(ANCHOR,INSERT+ANCHOR,1)
    compile(updated,str(PARSER),'exec')
    compile(SOURCE.read_text(encoding='utf-8'),str(MODULE),'exec')
    backup=ROOT/('_backup_receipt_reconciliation_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
    backup.mkdir(parents=True,exist_ok=False)
    shutil.copy2(PARSER,backup/'parser.py')
    try:
        shutil.copy2(SOURCE,MODULE)
        PARSER.write_text(updated,encoding='utf-8')
    except Exception:
        shutil.copy2(backup/'parser.py',PARSER)
        if MODULE.exists(): MODULE.unlink()
        raise
    print('[OK] Reviewed-receipt reconciliation installed')
    print('[BACKUP]',backup)
    print('Next: $env:PYTHONPATH="src"; python -m pytest tests -q')
if __name__=='__main__':
    try: main()
    except Exception as exc:
        print('[STOP]',exc,file=sys.stderr)
        sys.exit(1)
