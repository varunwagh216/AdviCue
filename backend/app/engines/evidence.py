"""Evidence-gated, boundary-valued TWR and arithmetic class attribution.

This verifies arithmetic and coverage attestations, not authenticity of provider documents.
All flows/rebalances must be at supplied end-of-subperiod valuation boundaries.
"""
from datetime import date
from decimal import Decimal as D, localcontext
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)

class BenchmarkPolicy(Strict):
    name:str=Field(min_length=3,max_length=160)
    rationale:str=Field(min_length=20,max_length=2000)
    source_reference:str=Field(min_length=5,max_length=500)
    client_mandate_reference:str=Field(min_length=5,max_length=500)
    effective_from:date
    effective_to:date
    suitable_for_client:Literal[True]

class Flow(Strict):
    date:date
    kind:Literal['CONTRIBUTION','WITHDRAWAL']
    amount:D=Field(gt=0,le=10**15,decimal_places=2)
    source_reference:str=Field(min_length=5,max_length=500)

class ClassPeriod(Strict):
    asset_class:str=Field(min_length=2,max_length=100)
    start_value:D=Field(ge=0,le=10**15,decimal_places=2)
    end_value:D=Field(ge=0,le=10**15,decimal_places=2)
    net_flow:D=Field(ge=-10**15,le=10**15,decimal_places=2)
    benchmark_weight_pct:D=Field(ge=0,le=100,decimal_places=6)
    benchmark_return_pct:D=Field(ge=-100,le=10000,decimal_places=6)
    valuation_reference:str=Field(min_length=5,max_length=500)
    benchmark_reference:str=Field(min_length=5,max_length=500)

class Subperiod(Strict):
    start_date:date
    end_date:date
    start_value:D=Field(gt=0,le=10**15,decimal_places=2)
    end_value:D=Field(ge=0,le=10**15,decimal_places=2)
    flows:list[Flow]=Field(default_factory=list,max_length=1000)
    classes:list[ClassPeriod]=Field(min_length=1,max_length=50)

class PerformanceEvidence(Strict):
    client_id:str=Field(min_length=1,max_length=40)
    currency:Literal['INR']='INR'
    illustrative:bool=False
    flow_statement_reference:str=Field(min_length=5,max_length=500)
    valuation_coverage_reference:str=Field(min_length=5,max_length=500)
    flows_complete:Literal[True]
    valuation_coverage_complete:Literal[True]
    boundaries_include_all_flows_and_rebalances:Literal[True]
    fees_taxes_consistent:Literal[True]
    benchmark_policy:BenchmarkPolicy
    periods:list[Subperiod]=Field(min_length=1,max_length=366)

class AllocationBand(Strict):
    asset_class:str=Field(min_length=2,max_length=100)
    min_pct:D=Field(ge=0,le=100,decimal_places=2)
    max_pct:D=Field(ge=0,le=100,decimal_places=2)

class MandateEvidence(Strict):
    client_id:str=Field(min_length=1,max_length=40)
    effective_from:date
    effective_to:date
    source_reference:str=Field(min_length=5,max_length=500)
    rationale:str=Field(min_length=12,max_length=2000)
    liquidity_context:str=Field(default='',max_length=1000)
    illustrative:bool=False
    bands:list[AllocationBand]=Field(min_length=1,max_length=30)


def validate_mandate(m):
    if m.effective_to<m.effective_from:raise ValueError('Mandate effective dates are reversed')
    names=[b.asset_class.casefold() for b in m.bands]
    if len(set(names))!=len(names):raise ValueError('Duplicate mandate asset class')
    if any(b.min_pct>b.max_pct for b in m.bands):raise ValueError('Minimum allocation exceeds maximum')
    if sum(b.min_pct for b in m.bands)>100:raise ValueError('Mandate minimum allocations exceed 100%')


def q(value):return str(D(value).quantize(D('.000001')))


def reconcile(e:PerformanceEvidence):
    policy=e.benchmark_policy
    if policy.effective_to<policy.effective_from:raise ValueError('Benchmark policy dates are reversed')
    previous=None;seen_flows=set();periods=[]
    with localcontext() as ctx:
        ctx.prec=40
        for p in e.periods:
            if not p.start_date<p.end_date:raise ValueError('Each period needs increasing dates')
            if p.end_date>date.today():raise ValueError('Future valuations cannot verify actual performance')
            if p.start_date<policy.effective_from or p.end_date>policy.effective_to:raise ValueError('Benchmark policy does not cover every observation')
            names=[c.asset_class.casefold() for c in p.classes]
            if len(names)!=len(set(names)):raise ValueError('Duplicate class within a period')
            if sum(c.start_value for c in p.classes)!=p.start_value or sum(c.end_value for c in p.classes)!=p.end_value:
                raise ValueError('Class valuations must reconcile exactly to portfolio valuations')
            if sum(c.benchmark_weight_pct for c in p.classes)!=100:raise ValueError('Benchmark weights must sum to 100%')
            net=D(0)
            for flow in p.flows:
                if flow.date!=p.end_date:raise ValueError('An external flow lacks an end-boundary valuation; split the period at that flow')
                key=(flow.date,flow.kind,flow.amount,flow.source_reference)
                if key in seen_flows:raise ValueError('Duplicate cash-flow evidence')
                seen_flows.add(key)
                net+=flow.amount if flow.kind=='CONTRIBUTION' else -flow.amount
            if sum(c.net_flow for c in p.classes)!=net:raise ValueError('Class cash movements must reconcile to net external cash flow')
            if previous:
                if p.start_date!=previous.end_date or p.start_value!=previous.end_value:raise ValueError('Valuation coverage has a date or balance gap')
                before={c.asset_class.casefold():c.end_value for c in previous.classes}
                current={c.asset_class.casefold():c.start_value for c in p.classes}
                # Closed/new classes may appear with zero value only.
                if any(before.get(k,D(0))!=current.get(k,D(0)) for k in set(before)|set(current)):
                    raise ValueError('Class valuation continuity is broken')
            rp=(p.end_value-net)/p.start_value-1
            if rp<-1:raise ValueError('Flow-adjusted portfolio return is below -100%')
            rb=sum(c.benchmark_weight_pct/100*c.benchmark_return_pct/100 for c in p.classes)
            effects=[]
            for c in p.classes:
                wp=c.start_value/p.start_value;wb=c.benchmark_weight_pct/100;br=c.benchmark_return_pct/100
                if c.start_value==0:
                    if c.end_value!=c.net_flow:raise ValueError('A zero-opening class has unexplained gains; supply an earlier valuation boundary')
                    cr=br # zero-held convention; selection+interaction cancel exactly
                else:cr=(c.end_value-c.net_flow)/c.start_value-1
                if cr<-1:raise ValueError('Class return below -100%; check cash movements')
                allocation=(wp-wb)*(br-rb);selection=wb*(cr-br);interaction=(wp-wb)*(cr-br)
                effects.append({'asset_class':c.asset_class,'allocation':allocation,'selection':selection,'interaction':interaction,
                    'valuation_reference':c.valuation_reference,'benchmark_reference':c.benchmark_reference})
            active=rp-rb
            if abs(sum(x['allocation']+x['selection']+x['interaction'] for x in effects)-active)>D('.000000001'):
                raise ValueError('Class effects do not reconcile to the active return')
            periods.append({'start_date':p.start_date.isoformat(),'end_date':p.end_date.isoformat(),'rp':rp,'rb':rb,'effects':effects,'net_flow':net})
            previous=p
        pg=bg=D(1)
        for p in periods:pg*=1+p['rp'];bg*=1+p['rb']
        totals={};prefix=D(1)
        for index,p in enumerate(periods):
            suffix=D(1)
            for later in periods[index+1:]:suffix*=1+later['rb']
            factor=prefix*suffix
            for x in p['effects']:
                target=totals.setdefault(x['asset_class'],{'allocation':D(0),'selection':D(0),'interaction':D(0),'sources':[]})
                for key in ('allocation','selection','interaction'):target[key]+=x[key]*factor*100
                target['sources'].append({'period_end':p['end_date'],'valuation_reference':x['valuation_reference'],'benchmark_reference':x['benchmark_reference']})
            prefix*=1+p['rp']
        active=(pg-bg)*100
        contributions=[{'asset_class':name,'allocation_pp':q(x['allocation']),'selection_pp':q(x['selection']),'interaction_pp':q(x['interaction']),
            'total_pp':q(x['allocation']+x['selection']+x['interaction']),'sources':x['sources']} for name,x in sorted(totals.items())]
        residual=active-sum(D(x['total_pp']) for x in contributions)
        return {'status':'RECONCILED_REVIEW_REQUIRED','illustrative':e.illustrative,'start_date':e.periods[0].start_date.isoformat(),
            'end_date':e.periods[-1].end_date.isoformat(),'portfolio_twr_pct':q((pg-1)*100),'benchmark_linked_pct':q((bg-1)*100),'active_return_pp':q(active),
            'rounding_residual_pp':q(residual),'class_contributions':contributions,'period_count':len(periods),
            'periods':[{'start_date':p['start_date'],'end_date':p['end_date'],'portfolio_return_pct':q(p['rp']*100),'benchmark_return_pct':q(p['rb']*100),'net_flow':str(p['net_flow'])} for p in periods],
            'method':'Boundary-valued TWR; Brinson-Fachler allocation, selection and interaction. Multiple periods linked by chronological portfolio-prefix/benchmark-suffix wealth factors.',
            'limitations':'Arithmetic and advisor source review do not independently authenticate provider evidence, establish suitability, or prove advice caused a return. All flows and rebalances require end-boundary valuations; fees and tax basis must match.'}
