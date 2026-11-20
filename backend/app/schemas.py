import re
from datetime import date as date_type
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9&\-_.^]{0,19}$")
FORMULA_CHARS = ("=", "+", "-", "@")


def _clean_text(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    if v.startswith(FORMULA_CHARS):
        raise ValueError("Text cannot start with = + - or @")
    return v or None


# ---------- auth ----------
class Credentials(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def valid_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v) or len(v) > 255:
            raise ValueError("Invalid email")
        return v


class ChangePassword(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)

    @field_validator("display_name")
    @classmethod
    def clean(cls, v):
        return _clean_text(v)


# ---------- transactions ----------
class TransactionIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    company_name: str | None = Field(default=None, max_length=120)
    sector: str | None = Field(default=None, max_length=50)
    type: Literal["BUY", "SELL"]
    quantity: float = Field(gt=0, lt=1e12)
    price: float = Field(gt=0, lt=1e9)
    fees: float = Field(default=0, ge=0, lt=1e9)
    date: date_type
    note: str | None = Field(default=None, max_length=255)

    @field_validator("symbol")
    @classmethod
    def symbol_ok(cls, v: str) -> str:
        v = v.strip().upper()
        if not SYMBOL_RE.match(v):
            raise ValueError("Symbol may contain letters, digits and & - _ . ^ only (max 20)")
        return v

    @field_validator("company_name", "sector", "note")
    @classmethod
    def text_ok(cls, v):
        return _clean_text(v)

    @field_validator("date")
    @classmethod
    def not_future(cls, v: date_type) -> date_type:
        if v > date_type.today():
            raise ValueError("Transaction date cannot be in the future")
        if v.year < 1990:
            raise ValueError("Transaction date is too old")
        return v


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    symbol: str
    company_name: str | None
    type: str
    quantity: float
    price: float
    fees: float
    date: date_type
    note: str | None
    source: str
    realized_pnl: float | None = None


# ---------- legacy holdings API (kept so older clients keep working) ----------
class HoldingIn(BaseModel):
    symbol: str = Field(min_length=1, max_length=20)
    sector: str = Field(default="Other", max_length=50)
    quantity: float = Field(gt=0)
    buy_price: float = Field(gt=0)
    current_price: float = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def upper(cls, v: str) -> str:
        v = v.strip().upper()
        if not SYMBOL_RE.match(v):
            raise ValueError("Invalid symbol")
        return v

    @field_validator("sector")
    @classmethod
    def sector_ok(cls, v):
        return _clean_text(v) or "Other"


class PositionPatch(BaseModel):
    sector: str | None = Field(default=None, max_length=50)
    company_name: str | None = Field(default=None, max_length=120)
    current_price: float | None = Field(default=None, gt=0, lt=1e9)

    @field_validator("sector", "company_name")
    @classmethod
    def text_ok(cls, v):
        return _clean_text(v)


# ---------- goals ----------
class GoalIn(BaseModel):
    target: float = Field(gt=0, lt=1e13)
    years: int = Field(ge=1, le=50)
    monthly_sip: float = Field(ge=0, lt=1e9, default=0)
    annual_return_pct: float = Field(ge=0, le=30, default=10)
    starting_amount: float | None = Field(default=None, ge=0, lt=1e13)  # None = your current portfolio value


class GoalSave(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    target_amount: float = Field(gt=0, lt=1e13)
    years: int = Field(ge=1, le=50)
    expected_return_pct: float = Field(ge=0, le=30, default=10)
    monthly_sip: float = Field(ge=0, lt=1e9, default=0)
    starting_amount: float | None = Field(default=None, ge=0, lt=1e13)

    @field_validator("name")
    @classmethod
    def name_ok(cls, v):
        v = _clean_text(v)
        if not v:
            raise ValueError("Name is required")
        return v


class Scenario(BaseModel):
    name: str | None = Field(default=None, max_length=40)
    years: int = Field(ge=1, le=50)
    annual_return_pct: float = Field(ge=0, le=30)
    monthly_sip: float | None = Field(default=None, ge=0, lt=1e9)  # None = solve the SIP needed for the target


class CompareIn(BaseModel):
    target: float = Field(gt=0, lt=1e13)
    starting_amount: float | None = Field(default=None, ge=0, lt=1e13)
    scenarios: list[Scenario] = Field(min_length=1, max_length=6)


# ---------- misc ----------
class Question(BaseModel):
    question: str = Field(min_length=3, max_length=300)


class Preferences(BaseModel):
    theme: Literal["light", "dark", "system"] = "system"
    default_period: Literal["1W", "1M", "3M", "6M", "1Y", "ALL"] = "ALL"
    benchmark_symbol: str | None = Field(default=None, max_length=20)


class ImportConfirm(BaseModel):
    import_valid_only: bool = False
