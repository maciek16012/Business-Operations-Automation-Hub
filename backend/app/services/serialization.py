from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy.inspection import inspect


def value_json(value: object) -> object:
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, UUID | Decimal):
        return str(value)
    return value


def row_json(row: object) -> dict:
    return {
        column.key: value_json(getattr(row, column.key))
        for column in inspect(type(row), raiseerr=True).columns
    }
