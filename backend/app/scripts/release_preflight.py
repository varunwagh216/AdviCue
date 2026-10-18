"""Offline, read-only local release preflight.

Run from backend/: python -m app.scripts.release_preflight [--json PATH] [--strict]
Does not contact a model, perform migrations or modify investor records.
"""
from __future__ import annotations
import argparse
import json
import sys
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
from sqlalchemy import inspect, select, text
from app.core.database import engine, SessionLocal
from app.core.config import settings

REQUIRED = ('organizations','users','investors','holdings','import_batches',
            'source_rows','performance_snapshots','pattern_runs','detected_patterns',
            'attention_cases','advice_records','follow_up_tasks','audit_events',
            'local_ai_briefs','meeting_notes','commitment_checks','asset_class_return_observations','goal_plans','review_evidence','pilot_sessions','monitoring_states','advice_outcome_reviews')


def preflight() -> dict:
    checks = []
    def add(key, ok, detail):
        checks.append({'check':key,'passed':bool(ok),'detail':str(detail)})
    try:
        import fastapi, sqlalchemy  # noqa: F401
        add('Python dependencies', True, f'Python {sys.version.split()[0]}; FastAPI {version("fastapi")}; SQLAlchemy {version("sqlalchemy")}')
    except (ImportError, PackageNotFoundError) as exc:
        add('Python dependencies', False, exc)
    db_ready = False
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
            tables = set(inspect(connection).get_table_names())
            missing = sorted(set(REQUIRED) - tables)
            add('Database tables', not missing, 'Application database tables present' if not missing else f'Missing: {", ".join(missing)}')
            if 'alembic_version' in tables:
                revision = connection.execute(text('SELECT version_num FROM alembic_version LIMIT 1')).scalar()
                add('Alembic migration', revision == '0014_advisor_identity', f'Current revision: {revision or "none"}')
            else:
                add('Alembic migration', False, 'alembic_version table is missing')
            if 'attention_cases' in tables and 'superseded_by_id' in {c['name'] for c in inspect(connection).get_columns('attention_cases')}:
                duplicate_currents = connection.execute(text("SELECT COUNT(*) FROM (SELECT organization_id, investor_id FROM attention_cases WHERE superseded_by_id IS NULL AND rule_id NOT LIKE 'MANUAL_%' AND rule_id NOT LIKE 'MON_%' GROUP BY organization_id, investor_id, CASE WHEN priority = 'V_VERIFY' THEN 1 ELSE 0 END HAVING COUNT(*) > 1) tmp")).scalar() or 0
                add('Canonical attention queue', duplicate_currents == 0,
                    f'{duplicate_currents} investors have multiple current review cases')
            db_ready = not missing
    except Exception as exc:
        add('Database connection', False, f'{type(exc).__name__}: {exc}')
    try:
        from app.ai.local_models import local_llama_cpp_url
        local_llama_cpp_url()
        add('Local AI endpoint safety', True, 'Configured endpoint is loopback-only (does not test model availability)')
    except Exception as exc:
        add('Local AI endpoint safety', False, str(exc))
    add('Development origin', settings.frontend_origin.startswith(('http://localhost:', 'http://127.0.0.1:')),
        f'Allowed frontend origin: {settings.frontend_origin} (local workspace)')
    result = {'generated_at':datetime.now(timezone.utc).isoformat(), 'checks':checks,
              'passed':sum(1 for x in checks if x['passed']), 'total':len(checks),
              'all_checks_pass':all(x['passed'] for x in checks),
              'record_mutations':False,
              'warning':'This checks local configuration; it is not a production security certification.'}
    return result


def main():
    parser=argparse.ArgumentParser(description='AdviCue AI database and security preflight')
    parser.add_argument('--json', dest='out', type=Path, help='Write diagnostic report to a local JSON file')
    parser.add_argument('--strict', action='store_true', help='Exit with code 1 if any check fails')
    args=parser.parse_args()
    report=preflight()
    for check in report['checks']:
        print(('PASS' if check['passed'] else 'FAIL') + '  ' + check['check'] + ': ' + check['detail'])
    print(f"{report['passed']}/{report['total']} preflight checks passed")
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2),encoding='utf-8')
        print('Saved diagnostics:',args.out)
    return 0 if report['all_checks_pass'] or not args.strict else 1

if __name__ == '__main__':
    raise SystemExit(main())
