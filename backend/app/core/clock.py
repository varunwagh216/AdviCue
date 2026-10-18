"""The current INR advisor workspace uses the India business calendar."""
from datetime import datetime,timedelta,timezone

ADVISOR_ZONE=timezone(timedelta(hours=5,minutes=30))


def utc_iso(value:datetime)->str:
    return (value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value).astimezone(timezone.utc).isoformat()


def advisor_day(value:datetime):
    aware=value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
    return aware.astimezone(ADVISOR_ZONE).date()
