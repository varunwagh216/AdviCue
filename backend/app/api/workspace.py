"""Advisor-scoped home search. Local AI routes intent; records own every fact."""
from datetime import date
import re
from fastapi import APIRouter,Depends,Request,HTTPException
from pydantic import BaseModel,Field
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import current_user,csrf_protected,require_same_origin
from app.models import User
from app.api.dashboard import list_investors
from app.api.workflow import list_attention,list_tasks,list_advice
from app.ai.local_models import local_llm_json,LocalModelError

router=APIRouter(tags=['Advisor home'])


def home_data(user,db):
    clients=list_investors(user,db)['items'];reviews=list_attention(user=user,db=db)['items'];tasks=list_tasks(user,db)['items']
    active=[c for c in reviews if c['status']!='RESOLVED' and not c['superseded_by_id']]
    return clients,active,tasks


@router.get('/home')
def home(user:User=Depends(current_user),db:Session=Depends(get_db)):
    clients,reviews,tasks=home_data(user,db)
    return {'assigned_clients':len(clients),'clients_with_open_reviews':len({c['investor_id'] for c in reviews}),
        'high_priority_clients':len({c['investor_id'] for c in reviews if c['priority']=='P1'}),
        'due_follow_ups':sum(t['status'] in ('OPEN','IN_PROGRESS') and t['due_date']<=date.today().isoformat() for t in tasks),
        'as_of':date.today().isoformat()}


class SearchInput(BaseModel):
    query:str=Field(min_length=3,max_length=1200)


@router.post('/assistant/transcribe')
async def transcribe_search(request:Request,user:User=Depends(csrf_protected)):
    require_same_origin(request)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Advisor search required')
    from starlette.concurrency import run_in_threadpool
    from app.ai.local_models import transcribe_audio_locally
    # Upload is temporary; a search recording does not become a meeting note.
    async with request.form(max_files=1,max_fields=0,max_part_size=2*1024*1024) as form:
        audio=form.get('audio')
        if audio is None or not hasattr(audio,'read'):raise HTTPException(status_code=422,detail='A WAV recording is required')
        raw=await audio.read(2*1024*1024+1)
        if not raw or len(raw)>2*1024*1024:raise HTTPException(status_code=413,detail='Search recording must be under 2 MB')
        import io,wave
        try:
            with wave.open(io.BytesIO(raw),'rb') as w:
                if w.getnchannels()!=1 or w.getframerate()!=16000 or w.getsampwidth()!=2 or w.getnframes()/16000>46:raise ValueError()
        except (wave.Error,EOFError,ValueError):raise HTTPException(status_code=415,detail='Use a mono 16 kHz PCM WAV recording of at most 45 seconds')
        try:text=await run_in_threadpool(transcribe_audio_locally,raw,'.wav')
        except LocalModelError as exc:raise HTTPException(status_code=503,detail=str(exc)) from exc
    if len(text)>1200:raise HTTPException(status_code=422,detail='Please use a shorter spoken question')
    return {'transcript':text,'provider':'whisper.cpp','note':'Review the transcript, then press Search. Audio was deleted after transcription.'}


@router.post('/assistant/search')
def search(payload:SearchInput,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Advisor search required')
    query=payload.query.strip();q=query.casefold();mode='LOCAL_AI';warning=None
    intent='FOLLOW_UPS' if any(x in q for x in ('follow','task','call due')) else 'REVIEWS' if 'review' in q else 'ATTENTION' if any(x in q for x in ('attention','urgent','priority')) else 'ADVICE' if 'advice' in q else 'PATTERNS' if 'pattern' in q else 'TODAY' if any(x in q for x in ('today','morning','day')) else 'CLIENT'
    term=''
    try:
        result=local_llm_json('Route a search of the signed-in advisor records. Return intent and client_search only. TODAY means daily work; ATTENTION and REVIEWS mean client reviews; FOLLOW_UPS means tasks; CLIENT means a client name, ID, risk profile or goal; ADVICE means recommendations; PATTERNS means shared patterns. client_search must quote a name, ID or search phrase from the query, or be empty. Never answer financial questions or invent a client.',{'query':query},response_schema={'type':'object','additionalProperties':False,'required':['intent','client_search'],'properties':{'intent':{'type':'string','enum':['TODAY','ATTENTION','REVIEWS','FOLLOW_UPS','CLIENT','ADVICE','PATTERNS']},'client_search':{'type':'string','maxLength':120}}})
        if result.get('intent') in ('TODAY','ATTENTION','REVIEWS','FOLLOW_UPS','CLIENT','ADVICE','PATTERNS'):intent=result['intent']
        proposed=result.get('client_search','')
        if isinstance(proposed,str) and proposed.strip() and proposed.casefold() in q:term=proposed.strip().casefold()
    except LocalModelError:
        mode='RECORD_SEARCH';warning='Local AI is unavailable. These are direct matches from your assigned records.'
    from app.services.assistant_facts import query_facts
    calculated=query_facts(query,user,db)
    if calculated:
        return {'query':query,'mode':mode,'warning':warning,**calculated}
    clients,reviews,tasks=home_data(user,db);names={c['id']:c['display_name'] for c in clients}
    mentioned=[c for c in clients if c['display_name'].casefold() in q or c['id'].casefold() in q]
    if not mentioned and term:mentioned=[c for c in clients if term in f"{c['display_name']} {c['id']} {c['risk_profile'] or ''} {c['primary_goal'] or ''}".casefold()]
    if not mentioned and intent=='CLIENT':
        words=[w for w in re.findall(r'[\w-]+',q) if len(w)>=3 and w not in {'show','client','clients','about','portfolio','their','please','tell','what','which','with','have','investor','investors','does','stand','where','many','profiles','profile','how','are','the','and','for','that','need'}]
        mentioned=[c for c in clients if any(w in f"{c['display_name']} {c['id']} {c['risk_profile'] or ''} {c['primary_goal'] or ''}".casefold() for w in words)]
    ids={c['id'] for c in mentioned};cards=[]
    # Exact record references and explicit workflow words take precedence over
    # a small model's intent guess. AI output never redirects a named client to
    # an unrelated empty task/advice view.
    combined='review' in q and 'follow' in q
    if combined:intent='TODAY'
    elif any(x in q for x in ('follow-up','follow up','followup','tasks')):intent='FOLLOW_UPS'
    elif 'attention' in q or 'urgent' in q:intent='ATTENTION'
    elif 'review' in q:intent='REVIEWS'
    elif 'pattern' in q:intent='PATTERNS'
    elif 'advice' in q or 'recommendation' in q:intent='ADVICE'
    elif mentioned:intent='CLIENT'
    elif any(x in q for x in ('today','morning','my day')):intent='TODAY'
    else:intent='CLIENT'
    if intent=='CLIENT':
        from app.api.intelligence import analysis
        for c in mentioned:
            data=analysis(c['id'],user,db);a=data['allocation']
            cards.append({'id':c['id'],'kind':'CLIENT','client_name':c['display_name'],'title':c['primary_goal'] or 'Client portfolio',
                'detail':f"Recorded holdings: INR {a['total_value'] if a['total_value'] is not None else 'unavailable'}; equity: {a['equity_pct'] if a['equity_pct'] is not None else 'unavailable'}%. Performance: {data['performance']['status'].replace('_',' ').lower()}. "+('Open review: '+next(r['reason'] for r in reviews if r['investor_id']==c['id']) if any(r['investor_id']==c['id'] for r in reviews) else 'No open review recorded.'),'date':a['as_of_date'],'href':'/investors?selected='+c['id']})
    elif intent in ('ATTENTION','REVIEWS','TODAY'):
        seen=set()
        for c in reviews:
            if ids and c['investor_id'] not in ids:continue
            if intent=='ATTENTION' and any(x in q for x in ('high','urgent','priority')) and c['priority']!='P1':continue
            if c['investor_id'] in seen:continue
            seen.add(c['investor_id']);cards.append({'id':c['id'],'kind':'REVIEW','client_name':names.get(c['investor_id'],'Assigned client'),'title':c['title'],'detail':c['reason'],'date':c['source_date'],'href':'/attention?selected='+c['id']})
    if intent in ('FOLLOW_UPS','TODAY'):
        for t in tasks:
            if ids and t['investor_id'] not in ids:continue
            if intent=='TODAY' and (t['status'] not in ('OPEN','IN_PROGRESS') or (not combined and t['due_date']>date.today().isoformat())):continue
            if any(x in q for x in ('completed','finished','done')) and t['status']!='DONE':continue
            if 'open' in q and t['status'] not in ('OPEN','IN_PROGRESS'):continue
            if 'overdue' in q and not (t['status'] in ('OPEN','IN_PROGRESS') and t['due_date']<date.today().isoformat()):continue
            cards.append({'id':t['id'],'kind':'FOLLOW_UP','client_name':names.get(t['investor_id'],'Assigned client'),'title':t['title'],'detail':'Due '+t['due_date']+' · '+t['display_status'].replace('_',' ').lower(),'date':t['due_date'],'href':'/advice/follow-ups/'+t['id']})
    if intent=='ADVICE':
        for a in list_advice(user,db)['items']:
            if ids and a['investor_id'] not in ids:continue
            cards.append({'id':a['id'],'kind':'ADVICE','client_name':names.get(a['investor_id'],'Assigned client'),'title':a['recommendation'],'detail':a['expected_outcome'] or a['rationale'],'date':a['review_date'],'href':'/advice/'+a['id']})
    if intent=='PATTERNS':cards=[{'id':'patterns','kind':'PATTERNS','client_name':None,'title':'Open pattern detection','detail':'Review the dated patterns and supporting evidence for your assigned clients.','date':None,'href':'/patterns'}]
    count=len(cards)
    return {'query':query,'intent':intent,'mode':mode,'warning':warning,'answer':f"Found {count} recorded result{'s' if count!=1 else ''} in your assigned workspace." if cards else 'No assigned records matched this request. Try a client name, a goal, reviews or follow-ups.',
        'matched_count':count,'items':cards[:30],'note':('Showing the first 30 matches. Narrow your question to see others. ' if count>30 else '')+'AI interprets the request; names, dates, amounts and links come from scoped records. Results are review prompts, not investment recommendations.'}
