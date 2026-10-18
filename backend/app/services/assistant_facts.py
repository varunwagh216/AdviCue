"""Read-only, advisor-scoped search calculations. Never execute model-supplied SQL."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
import re
from sqlalchemy import select
from app.models import Investor, Holding, InvestmentTransaction
from app.engines.financial import allocation_for_holdings


def query_facts(query, user, db):
    q=query.casefold()
    clients=db.scalars(select(Investor).where(Investor.organization_id==user.organization_id,Investor.advisor_id==user.id).order_by(Investor.display_name)).all()
    named=[c for c in clients if c.id.casefold() in q or c.display_name.casefold() in q or re.search(r'\b'+re.escape(c.display_name.split()[0].casefold())+r'\b',q)]
    selected=named or clients
    # Filters are literals in the user's question, never invented by inference.
    for risk in ('conservative','moderate','aggressive'):
        if re.search(r'\b'+risk+r'\b',q):selected=[c for c in selected if risk in (c.risk_profile or '').casefold()]
    for goal in ('retirement','education','wealth','house','home','tax'):
        if re.search(r'\b'+goal+r'\b',q):selected=[c for c in selected if goal in (c.primary_goal or '').casefold()]
    for city in sorted({c.city for c in clients if c.city}):
        if re.search(r'\b'+re.escape(city.casefold())+r'\b',q):selected=[c for c in selected if c.city==city]
    aggregate=bool(re.search(r'\b(how many|how much|number of|count|total|aum|list|which|show|who|profiles|all clients|all investors|my clients|my investors|highest|largest|lowest|smallest|top)\b',q))
    sip=bool(re.search(r'\bsips?\b|systematic investment',q))
    explicit_ids=re.findall(r'\b(?:inv\d+|[a-z]-\d{3})\b',q)
    person=re.search(r'\b(?:does|about|for)\s+([a-z][a-z-]+)',q)
    generic={'any','my','the','all','our','a','an','today','tomorrow','retirement','education','wealth','house','home','tax','conservative','moderate','aggressive','clients','investors','profiles','sips','sip'}
    if explicit_ids and not any(c.id.casefold() in explicit_ids for c in clients):
        return {'intent':'CLARIFY','answer':'No assigned client matches that reference. Use an assigned client name or remove the client reference to search your book.','items':[],'note':'No book-wide total was substituted for an unmatched client.'}
    if sip and person and person[1] not in generic and not named:
        references=[c for c in selected if person[1] in c.display_name.casefold().split()]
        if not references:return {'intent':'CLARIFY','answer':'No assigned client matches that name. Use the client’s recorded name to check their SIP history.','items':[],'note':'No book-wide count was substituted for an unmatched person.'}
        selected=references
    if not sip and re.search(r'\b(attention|urgent|reviews?|follow|followups?|follow-ups?|advice|recommendations?|patterns?|today)\b',q):return None
    portfolio=bool(re.search(r'\b(aum|holdings|allocation|equity|debt|gold|cash|fixed deposit|mutual funds?|portfolio value)\b',q))
    if named and not sip and not portfolio and not re.search(r'\b(count|total|how many|how much)\b',q):return None
    filter_present=selected!=clients and not named
    book=aggregate and bool(re.search(r'\b(clients?|investors?|profiles?|aum|holdings|portfolio|equity)\b',q))
    if not (sip or (portfolio and aggregate) or (filter_present and aggregate) or book):return None
    if re.search(r'\b(insurance|email|phone|address|pan|salary|income|tax returns?|stocks? to buy)\b',q):
        return {'intent':'CLARIFY','answer':'That field is not supported in search. Try a client name, SIP history, a risk profile, a goal or an allocation category.','items':[],'note':'No unrelated client count was returned.'}
    if book and not (sip or portfolio or filter_present or named):
        plain=re.sub(r'[^\w\s]','',q)
        words=set(plain.split())-{'how','many','number','of','count','total','list','which','show','who','profiles','profile','clients','client','investors','investor','all','my','assigned','do','i','have','are','there','in','the','book','workspace','please','me'}
        if words:return {'intent':'CLARIFY','answer':'I could not identify a supported record filter. Try “How many clients have SIPs?”, “Show moderate-risk clients” or “Which clients have equity above 60%?”','items':[],'note':'No unrelated answer was substituted.'}
    # Arbitrary time windows and unsupported conjunctions must not silently turn
    # into an all-time count. Supported query examples stay visible in the UI.
    temporal=re.search(r'\b(last|this|next|since|before|after|between|during|january|february|march|april|may|june|july|august|september|october|november|december|20\d\d)\b',q)
    if temporal and (sip or portfolio):
        return {'intent':'CLARIFY','answer':'Please ask for recorded SIP history or latest recorded holdings. Date-filtered search is not available yet.','items':[],'note':'No all-time count was substituted for the requested time window.'}
    if re.search(r'\b(and|or)\b',q) and len(re.findall(r'\b(conservative|moderate|aggressive|retirement|education|wealth|house|tax)\b',q))>1:
        return {'intent':'CLARIFY','answer':'Please use one risk profile and one goal per question. Separate combined alternatives into two searches.','items':[],'note':'No ambiguous combined filter was applied.'}
    ids=[c.id for c in selected];cards=[]
    if sip:
        if re.search(r'\b(monthly|paused|stopped|cancelled|missed|highest|lowest|largest|smallest|top|above|below|over|under|more than|less than|at least)\b',q):
            return {'intent':'CLARIFY','answer':'I can count clients with recorded SIP contributions and total those transactions. Active mandates, monthly obligations and amount filters need additional confirmed records.','items':[],'note':'Recorded transactions alone do not establish a current SIP instruction.'}
        rows=db.scalars(select(InvestmentTransaction).where(InvestmentTransaction.organization_id==user.organization_id,InvestmentTransaction.investor_id.in_(ids),InvestmentTransaction.possible_duplicate.is_(False),InvestmentTransaction.date_confidence!='QUARANTINED_AMBIGUOUS',InvestmentTransaction.date<=date.today())).all() if ids else []
        by_client=defaultdict(list)
        for t in rows:
            if t.type.strip().casefold()=='sip' and t.amount>0:by_client[t.investor_id].append(t)
        negative=bool(re.search(r'\b(no|without|not|zero)\b',q))
        matches=[c for c in selected if bool(by_client[c.id])!=negative]
        total=sum((t.amount for c in matches for t in by_client[c.id]),Decimal(0))
        for c in matches:
            tx=by_client[c.id];dates=[t.date for t in tx]
            cards.append({'id':c.id,'kind':'SIP','client_name':c.display_name,'title':'No qualifying SIP transactions recorded' if negative else f'{len(tx)} recorded SIP contributions',
                'detail':f'INR {sum((t.amount for t in tx),Decimal(0)):,.2f} across recorded history.' if tx else 'Absence of a recorded transaction does not prove that no SIP exists.',
                'date':max(dates).isoformat() if dates else None,'href':'/investors?selected='+c.id})
        answer=f'{len(matches)} of {len(selected)} matching assigned clients have '+('no qualifying SIP transactions recorded.' if negative else f'recorded SIP contributions, totalling INR {total:,.2f}.')
        return {'intent':'SIPS','answer':answer,'items':cards,'matched_count':len(matches),'population_count':len(selected),'total_recorded_sip':str(total),'note':'Counts use distinct assigned clients with positive SIP transactions, excluding possible duplicates, ambiguous dates and future dates. Recorded history does not confirm an active mandate or future monthly SIP.'}
    grouped=defaultdict(list)
    if ids:
        for h in db.scalars(select(Holding).where(Holding.organization_id==user.organization_id,Holding.investor_id.in_(ids),Holding.as_of_date<=date.today())).all():grouped[h.investor_id].append(h)
    asset=next((key for word,key in [('equity','equity'),('fixed deposit','fixed'),('mutual fund','mutual'),('debt','debt'),('gold','gold'),('cash','cash')] if word in q),None)
    threshold=re.search(r'\b(above|over|more than|below|under|less than|at least)\s*(\d+(?:\.\d+)?)\s*%',q)
    if re.search(r'\d',q) and re.search(r'\b(above|below|over|under|more than|less than|at least)\b',q) and not threshold:
        return {'intent':'CLARIFY','answer':'Use an allocation percentage, for example “Which clients have equity above 60%?” Amount-based filters are not available yet.','items':[],'note':'No approximate amount filter was applied.'}
    facts=[]
    for c in selected:
        a=allocation_for_holdings(grouped[c.id]);total=Decimal(a['total_value'] or '0')
        classes=a.get('asset_classes',[])
        value=sum((Decimal(x['value']) for x in classes if asset and asset in x['asset_class'].casefold()),Decimal(0))
        weight=value/total*100 if total else Decimal(0)
        if asset and not value:continue
        if threshold:
            if not asset:return {'intent':'CLARIFY','answer':'Which allocation category should I filter? For example, equity above 60%.','items':[],'note':'A category is needed for a percentage comparison.'}
            op,n=threshold.groups();n=Decimal(n)
            if not (weight>=n if op=='at least' else weight>n if op in ('above','over','more than') else weight<n):continue
        facts.append((c,a,total,weight))
    if any(w in q for w in ('highest','largest','top','lowest','smallest')):
        facts.sort(key=lambda x:x[3] if asset else x[2],reverse=not any(w in q for w in ('lowest','smallest')))
        limit=re.search(r'\btop\s+(\d+)\b',q);facts=facts[:min(int(limit[1]),100) if limit else 1]
    for c,a,total,weight in facts:
        cards.append({'id':c.id,'kind':'PORTFOLIO','client_name':c.display_name,'title':c.primary_goal or 'Client profile','detail':f'{c.risk_profile or "Risk profile unrecorded"} · '+(f'Latest recorded holdings INR {total:,.2f}'+(f'; {asset} {weight:.2f}%.' if asset else '.') if a['as_of_date'] else 'No dated holdings recorded.'),'date':a['as_of_date'],'href':'/investors?selected='+c.id})
    total=sum((x[2] for x in facts),Decimal(0));dates=sorted({x[1]['as_of_date'] for x in facts if x[1]['as_of_date']})
    return {'intent':'BOOK','answer':f'{len(facts)} matching assigned client'+('s' if len(facts)!=1 else '')+f'. Latest recorded holdings total INR {total:,.2f}.','items':cards,'matched_count':len(facts),'recorded_holdings_total':str(total),'note':f'Each client uses their latest available holdings snapshot. Snapshot dates: {", ".join(dates) or "none"}. Missing records are not zero economic wealth. Holdings totals are not investment returns or verified current AUM.'}
