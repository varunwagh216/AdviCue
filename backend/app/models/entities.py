from __future__ import annotations
from datetime import datetime, timezone, date
from uuid import uuid4
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Date, Integer, Numeric, JSON, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("role IN ('ADVISOR','SUPERVISOR')", name="ck_user_role"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="ADVISOR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    external_advisor_code: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    organization: Mapped[Organization] = relationship()


class LoginSession(Base):
    __tablename__ = "login_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    user: Mapped[User] = relationship()


class Investor(Base):
    """Phase 1 skeleton only. Full investor schema and import arrive in Phase 2."""
    __tablename__ = "investors"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    advisor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    risk_profile: Mapped[str | None] = mapped_column(String(32))
    source_advisor_code: Mapped[str | None] = mapped_column(String(32))
    age: Mapped[int | None] = mapped_column(Integer)
    primary_goal: Mapped[str | None] = mapped_column(String(120))
    goal_target_amount: Mapped[Decimal | None] = mapped_column(Numeric(22, 2))
    goal_target_date: Mapped[date | None] = mapped_column(Date)
    onboarding_date: Mapped[date | None] = mapped_column(Date)
    effective_date: Mapped[date | None] = mapped_column(Date)
    city: Mapped[str | None] = mapped_column(String(100))
    advisor_preferences: Mapped[dict | None] = mapped_column(JSON)
    source_row_id: Mapped[str | None] = mapped_column(ForeignKey('source_rows.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    advisor: Mapped[User] = relationship()


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40))
    entity_id: Mapped[str | None] = mapped_column(String(60))
    detail: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

Index("ix_audit_org_date", AuditEvent.organization_id, AuditEvent.created_at)

# Phase 2 source-preserving import and normalized investment records.


class ImportBatch(Base):
    __tablename__ = 'import_batches'
    __table_args__ = (
        UniqueConstraint('organization_id', 'file_sha256', name='uq_batch_org_hash'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False, index=True)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    filename: Mapped[str] = mapped_column(String(240), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='STAGED')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_rows: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    warning_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sheet_counts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)


class SourceRow(Base):
    __tablename__ = 'source_rows'
    __table_args__ = (UniqueConstraint('batch_id','sheet_name','row_number', name='uq_source_row_position'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey('import_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    sheet_name: Mapped[str] = mapped_column(String(40), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    normalized_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DataQualityIssue(Base):
    __tablename__ = 'data_quality_issues'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey('import_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    source_row_id: Mapped[str | None] = mapped_column(ForeignKey('source_rows.id', ondelete='CASCADE'))
    sheet_name: Mapped[str] = mapped_column(String(40), nullable=False)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    field_name: Mapped[str | None] = mapped_column(String(64))
    severity: Mapped[str] = mapped_column(String(8), nullable=False)
    code: Mapped[str] = mapped_column(String(48), nullable=False)
    message: Mapped[str] = mapped_column(String(350), nullable=False)


class Holding(Base):
    __tablename__ = 'holdings'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False, index=True)
    investor_id: Mapped[str] = mapped_column(ForeignKey('investors.id'), nullable=False, index=True)
    source_row_id: Mapped[str] = mapped_column(ForeignKey('source_rows.id'), nullable=False, unique=True)
    external_holding_id: Mapped[str] = mapped_column(String(40), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    asset_class: Mapped[str] = mapped_column(String(80), nullable=False)
    instrument_name: Mapped[str] = mapped_column(String(200), nullable=False)
    units: Mapped[Decimal | None] = mapped_column(Numeric(22, 6))
    average_purchase_price: Mapped[Decimal | None] = mapped_column(Numeric(22, 6))
    purchase_date: Mapped[date | None] = mapped_column(Date)
    purchase_date_confidence: Mapped[str] = mapped_column(String(25),nullable=False,default='SOURCE_UNVERIFIED')
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(22, 6))
    current_value: Mapped[Decimal] = mapped_column(Numeric(22, 2), nullable=False)


class InvestmentTransaction(Base):
    __tablename__ = 'investment_transactions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False, index=True)
    investor_id: Mapped[str] = mapped_column(ForeignKey('investors.id'), nullable=False, index=True)
    source_row_id: Mapped[str] = mapped_column(ForeignKey('source_rows.id'), nullable=False, unique=True)
    external_transaction_id: Mapped[str] = mapped_column(String(40), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    type: Mapped[str] = mapped_column(String(60), nullable=False)
    instrument_name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(80), nullable=False)
    units: Mapped[Decimal | None] = mapped_column(Numeric(22, 6))
    price_per_unit: Mapped[Decimal | None] = mapped_column(Numeric(22, 6))
    amount: Mapped[Decimal] = mapped_column(Numeric(22, 2), nullable=False)
    possible_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    date_confidence: Mapped[str] = mapped_column(String(25),nullable=False,default='SOURCE_UNVERIFIED')
    unit_price_confidence: Mapped[str] = mapped_column(String(25),nullable=False,default='UNKNOWN')
    external_flow_status: Mapped[str] = mapped_column(String(28), default='UNKNOWN', nullable=False)


class PerformanceSnapshot(Base):
    __tablename__ = 'performance_snapshots'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False, index=True)
    investor_id: Mapped[str] = mapped_column(ForeignKey('investors.id'), nullable=False, index=True)
    source_row_id: Mapped[str] = mapped_column(ForeignKey('source_rows.id'), nullable=False, unique=True)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    portfolio_value: Mapped[Decimal] = mapped_column(Numeric(22, 2), nullable=False)
    benchmark_index_value: Mapped[Decimal | None] = mapped_column(Numeric(22, 6))
    source_reported_portfolio_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    source_reported_benchmark_return_pct: Mapped[Decimal | None] = mapped_column(Numeric(10, 4))
    return_verification_status: Mapped[str] = mapped_column(String(30), nullable=False, default='NOT_ASSESSABLE')


# Phase 4: explainable, versioned group detection. No suitability conclusions.
class PatternRun(Base):
    __tablename__ = 'pattern_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(20), nullable=False)
    as_of_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class DetectedPattern(Base):
    __tablename__ = 'detected_patterns'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey('pattern_runs.id'), nullable=False, index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False, index=True)
    rule_id: Mapped[str] = mapped_column(String(60), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(20), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    member_count: Mapped[int] = mapped_column(Integer, nullable=False)
    advisor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    recorded_value_total: Mapped[Decimal] = mapped_column(Numeric(22,2), nullable=False)
    evidence_summary: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


class PatternMember(Base):
    __tablename__ = 'pattern_members'
    __table_args__ = (UniqueConstraint('pattern_id','investor_id',name='uq_pattern_member'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    pattern_id: Mapped[str] = mapped_column(ForeignKey('detected_patterns.id'), nullable=False, index=True)
    investor_id: Mapped[str] = mapped_column(ForeignKey('investors.id'), nullable=False, index=True)
    advisor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    equity_pct: Mapped[Decimal] = mapped_column(Numeric(7,2), nullable=False)
    fixed_deposit_pct: Mapped[Decimal] = mapped_column(Numeric(7,2), nullable=False)
    recorded_value: Mapped[Decimal] = mapped_column(Numeric(22,2), nullable=False)
    evidence_source_row_ids: Mapped[list] = mapped_column(JSON, nullable=False)


# Phase 5 - persistent, evidence-backed advisor review cases.
class AttentionCase(Base):
    __tablename__ = 'attention_cases'
    __table_args__ = (
        UniqueConstraint('organization_id', 'investor_id', 'rule_id', 'source_date', name='uq_attention_unique_finding'),
        CheckConstraint("priority IN ('P1','P2','P3','V_VERIFY')", name='ck_attention_priority'),
        CheckConstraint("status IN ('OPEN','IN_REVIEW','NEEDS_DATA','RESOLVED')", name='ck_attention_status'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True, nullable=False)
    investor_id: Mapped[str] = mapped_column(ForeignKey('investors.id'), index=True, nullable=False)
    advisor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    pattern_id: Mapped[str | None] = mapped_column(ForeignKey('detected_patterns.id'), nullable=True)
    rule_id: Mapped[str] = mapped_column(String(60), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(20), nullable=False)
    source_date: Mapped[date] = mapped_column(Date, nullable=False)
    priority: Mapped[str] = mapped_column(String(10), nullable=False, default='P2')
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='OPEN')
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_action: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_source_row_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_note: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    # Historical duplicate/replaced signals stay available to advice/auditing, never in the active queue.
    superseded_by_id: Mapped[str | None] = mapped_column(ForeignKey('attention_cases.id'), nullable=True)


# Phase 6 - reviewed recommendations and independently verified tasks.
class AdviceRecord(Base):
    __tablename__ = 'advice_records'
    __table_args__ = (CheckConstraint("status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED')", name='ck_advice_status'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True, nullable=False)
    investor_id: Mapped[str] = mapped_column(ForeignKey('investors.id'), index=True, nullable=False)
    advisor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    alert_id: Mapped[str] = mapped_column(ForeignKey('attention_cases.id'), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='DRAFT')
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    assumptions: Mapped[str | None] = mapped_column(Text)
    evidence_source_row_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))
    decision_note: Mapped[str | None] = mapped_column(Text)
    supersedes_id: Mapped[str | None] = mapped_column(ForeignKey('advice_records.id'))
    source_meeting_id: Mapped[str | None] = mapped_column(ForeignKey('meeting_notes.id'))
    expected_outcome: Mapped[str | None] = mapped_column(Text)
    review_date: Mapped[date | None] = mapped_column(Date)
    review_trigger: Mapped[str | None] = mapped_column(String(300))
    outcome_rule: Mapped[dict | None] = mapped_column(JSON)


class FollowUpTask(Base):
    __tablename__ = 'follow_up_tasks'
    __table_args__ = (CheckConstraint("status IN ('OPEN','IN_PROGRESS','DONE','CANNOT_VERIFY')", name='ck_follow_up_status'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), index=True, nullable=False)
    investor_id: Mapped[str] = mapped_column(ForeignKey('investors.id'), index=True, nullable=False)
    advice_id: Mapped[str | None] = mapped_column(ForeignKey('advice_records.id'), index=True, nullable=True)
    source_meeting_id: Mapped[str | None] = mapped_column(ForeignKey('meeting_notes.id'))
    owner_id: Mapped[str] = mapped_column(ForeignKey('users.id'), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='OPEN')
    completion_note: Mapped[str | None] = mapped_column(Text)
    evidence_type: Mapped[str | None] = mapped_column(String(32))
    evidence_reference: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# Phase 7: optional, evidence-grounded local AI briefs.
class LocalAIBrief(Base):
    __tablename__ = 'local_ai_briefs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False, index=True)
    investor_id: Mapped[str] = mapped_column(ForeignKey('investors.id'), nullable=False, index=True)
    created_by: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    review_questions: Mapped[list] = mapped_column(JSON, nullable=False)
    cited_fact_ids: Mapped[list] = mapped_column(JSON, nullable=False)
    fact_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)


# Phase 7: no persistent raw audio. Notes are unapproved until explicitly approved.
class MeetingNote(Base):
    __tablename__ = 'meeting_notes'
    __table_args__ = (CheckConstraint("status IN ('DRAFT','APPROVED')", name='ck_meeting_note_status'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False, index=True)
    investor_id: Mapped[str] = mapped_column(ForeignKey('investors.id'), nullable=False, index=True)
    advisor_id: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    input_method: Mapped[str] = mapped_column(String(20), nullable=False)  # TEXT or LOCAL_AUDIO
    recording_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audio_sha256: Mapped[str | None] = mapped_column(String(64))
    transcript: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='DRAFT')
    extracted_draft: Mapped[dict | None] = mapped_column(JSON)
    approved_summary: Mapped[str | None] = mapped_column(Text)
    approved_commitments: Mapped[list | None] = mapped_column(JSON)
    approved_preferences: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[str | None] = mapped_column(ForeignKey('users.id'))


class CommitmentCheck(Base):
    """Human-authored measurable promise. Status is recomputed against dated holdings."""
    __tablename__ = 'commitment_checks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'),nullable=False,index=True)
    investor_id: Mapped[str] = mapped_column(ForeignKey('investors.id'),nullable=False,index=True)
    advisor_id: Mapped[str] = mapped_column(ForeignKey('users.id'),nullable=False)
    meeting_id: Mapped[str] = mapped_column(ForeignKey('meeting_notes.id'),nullable=False,index=True)
    metric: Mapped[str] = mapped_column(String(36),nullable=False)
    comparator: Mapped[str] = mapped_column(String(3),nullable=False)
    target_pct: Mapped[Decimal] = mapped_column(Numeric(7,2),nullable=False)
    due_date: Mapped[date] = mapped_column(Date,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),nullable=False,default=utcnow)


class AssetClassReturnObservation(Base):
    """Optional third-party class-return evidence; never infer from client holdings."""
    __tablename__ = 'asset_class_return_observations'
    __table_args__ = (UniqueConstraint('organization_id','asset_class','month_date',name='uq_org_class_return_month'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), nullable=False, index=True)
    asset_class: Mapped[str] = mapped_column(String(100), nullable=False)
    month_date: Mapped[date] = mapped_column(Date, nullable=False)
    reported_return_pct: Mapped[Decimal] = mapped_column(Numeric(12,6), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(300), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(200), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    imported_by: Mapped[str] = mapped_column(ForeignKey('users.id'), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class GoalPlan(Base):
    __tablename__ = 'goal_plans'
    __table_args__ = (UniqueConstraint('organization_id','investor_id',name='uq_goal_plan_investor'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'),nullable=False)
    investor_id: Mapped[str] = mapped_column(ForeignKey('investors.id'),nullable=False)
    advisor_id: Mapped[str] = mapped_column(ForeignKey('users.id'),nullable=False)
    principal: Mapped[Decimal] = mapped_column(Numeric(22,2),nullable=False)
    monthly_contribution: Mapped[Decimal] = mapped_column(Numeric(22,2),nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date,nullable=False)
    annual_rates: Mapped[list] = mapped_column(JSON,nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)


class ReviewEvidence(Base):
    __tablename__='review_evidence'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id: Mapped[str]=mapped_column(ForeignKey('organizations.id'),nullable=False,index=True)
    investor_id: Mapped[str]=mapped_column(ForeignKey('investors.id'),nullable=False,index=True)
    advisor_id: Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    kind: Mapped[str]=mapped_column(String(20),nullable=False)
    status: Mapped[str]=mapped_column(String(20),nullable=False,default='DRAFT')
    payload: Mapped[dict]=mapped_column(JSON,nullable=False)
    payload_sha256: Mapped[str]=mapped_column(String(64),nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
    approved_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    approval_note: Mapped[str|None]=mapped_column(Text)


class PilotSession(Base):
    __tablename__='pilot_sessions'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id: Mapped[str]=mapped_column(ForeignKey('organizations.id'),nullable=False,index=True)
    advisor_id: Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False,index=True)
    investor_id: Mapped[str]=mapped_column(ForeignKey('investors.id'),nullable=False)
    case_id: Mapped[str|None]=mapped_column(ForeignKey('attention_cases.id'))
    started_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
    finished_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    elapsed_seconds: Mapped[int|None]=mapped_column(Integer)
    outcome: Mapped[str|None]=mapped_column(String(30))
    baseline_seconds: Mapped[int|None]=mapped_column(Integer)
    already_known: Mapped[bool|None]=mapped_column(Boolean)
    discovery_note: Mapped[str|None]=mapped_column(Text)
    sampling_method: Mapped[str]=mapped_column(String(30),default='CLIENT_REVIEW',nullable=False)
    missed_issue: Mapped[bool|None]=mapped_column(Boolean)
    voluntary_return: Mapped[bool|None]=mapped_column(Boolean)


class MonitoringState(Base):
    __tablename__='monitoring_states'
    __table_args__=(UniqueConstraint('organization_id','investor_id','stream',name='uq_monitor_state'),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id: Mapped[str]=mapped_column(ForeignKey('organizations.id'),nullable=False,index=True)
    investor_id: Mapped[str]=mapped_column(ForeignKey('investors.id'),nullable=False,index=True)
    stream: Mapped[str]=mapped_column(String(20),nullable=False)
    fingerprint: Mapped[str|None]=mapped_column(String(64))
    active: Mapped[bool]=mapped_column(Boolean,default=False,nullable=False)
    current_case_id: Mapped[str|None]=mapped_column(ForeignKey('attention_cases.id'))
    checked_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)


class AdviceOutcomeReview(Base):
    __tablename__='advice_outcome_reviews'
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    organization_id: Mapped[str]=mapped_column(ForeignKey('organizations.id'),nullable=False,index=True)
    investor_id: Mapped[str]=mapped_column(ForeignKey('investors.id'),nullable=False,index=True)
    advisor_id: Mapped[str]=mapped_column(ForeignKey('users.id'),nullable=False)
    advice_id: Mapped[str]=mapped_column(ForeignKey('advice_records.id'),nullable=False,index=True)
    evidence_id: Mapped[str|None]=mapped_column(ForeignKey('review_evidence.id'))
    result: Mapped[dict]=mapped_column(JSON,nullable=False)
    note: Mapped[str]=mapped_column(Text,nullable=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,nullable=False)
