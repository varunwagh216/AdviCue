"""release verification. Live inference is explicit and never mocked."""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from app.scripts.release_preflight import preflight
from app.ai.local_models import local_llm_json, transcribe_audio_locally, LocalModelError
from app.ai.fact_templates import render_fact_template


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live-ai',action='store_true',help='Require actual llama.cpp inference on the configured loopback endpoint')
    parser.add_argument('--audio',type=Path,help='Optional consented local speech sample for real Whisper inference')
    parser.add_argument('--recording-consent',action='store_true')
    parser.add_argument('--json',type=Path,default=Path('release-verification.json'))
    args=parser.parse_args()
    checks=preflight()['checks']
    if args.live_ai:
        try:
            reply=local_llm_json('Return JSON with summary. Write a short review sentence using only the placeholder [[EQUITY_PCT]] for the supplied equity percentage. Do not invent figures.',{'equity_pct':'20.00'})
            text=render_fact_template(reply.get('summary',''),{'EQUITY_PCT':'20.00'})
            if not text or '20.00' not in text:raise ValueError('Model did not use the supplied fact placeholder')
            checks.append({'check':'Real llama.cpp phrasing','passed':True,'detail':'Actual model response validated; client facts not used.'})
        except Exception as exc:checks.append({'check':'Real llama.cpp phrasing','passed':False,'detail':str(exc)})
    else:checks.append({'check':'Real llama.cpp phrasing','passed':None,'detail':'Not run. Supply --live-ai after installing model/runtime.'})
    if args.audio:
        if not args.recording_consent:parser.error('--audio requires --recording-consent')
        try:
            data=args.audio.read_bytes()
            if len(data)>12*1024*1024:raise ValueError('Use an audio sample smaller than 12 MB')
            transcript=transcribe_audio_locally(data,args.audio.suffix)
            checks.append({'check':'Real Whisper transcription','passed':bool(transcript),'detail':'Speech recognized locally. Transcript content is not written to the report.'})
        except Exception as exc:checks.append({'check':'Real Whisper transcription','passed':False,'detail':str(exc)})
    else:checks.append({'check':'Real Whisper transcription','passed':None,'detail':'Not run. Supply a consented speech sample with --audio and --recording-consent.'})
    report={'generated_at':datetime.now(timezone.utc).isoformat(),'checks':checks,
        'all_requested_checks_pass':all(c['passed'] is not False for c in checks),
        'full_live_ai_certified':all(c['passed'] is True for c in checks)}
    args.json.write_text(json.dumps(report,indent=2),encoding='utf-8')
    for c in checks:print(('PASS' if c['passed'] is True else 'FAIL' if c['passed'] is False else 'NOT RUN')+'  '+c['check']+': '+c['detail'])
    return 0 if report['all_requested_checks_pass'] else 1

if __name__=='__main__':raise SystemExit(main())
