"""Explicit, local-demo-only operations for the single-advisor hackathon experience.

Do not grant every advisor organization-wide import permissions in real deployments.
The operator account is an exact email match, not a role-wide bypass.
"""
from __future__ import annotations
from app.core.config import settings
from app.models import User


def is_demo_operator(user: User) -> bool:
    return (
        settings.app_env.lower() in {"development", "demo", "local"}
        and settings.advisor_demo_operations_enabled
        and user.role == "ADVISOR"
        and user.is_active
        and user.email.lower() == settings.advisor_demo_operator_email.lower()
    )


def may_import(user: User) -> bool:
    return user.role == "SUPERVISOR" or is_demo_operator(user)


def may_run_org_scan(user: User) -> bool:
    return user.role == "SUPERVISOR" or is_demo_operator(user)
