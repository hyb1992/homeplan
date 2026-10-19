"""입력·출력 계약. extra 필드는 import에서 보존하되 계산에 묵시적으로 쓰지 않는다."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator, model_validator

from .dates import DATE_KEYS, DateInput, resolve


def yes(value: Any) -> bool:
    if value in (True, 1, "예", "적용", "true", "True", "yes"):
        return True
    if value in (False, 0, "아니오", "미적용", "false", "False", "no", None):
        return False
    raise ValueError(f"예/아니오 값을 확인하세요: {value}")


YesNo = Annotated[bool, BeforeValidator(yes)]
Money = Annotated[int, Field(ge=0)]
Ratio = Annotated[Decimal, Field(ge=0, le=1)]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="allow", validate_assignment=True)


class Settings(InputModel):
    asset_base_date: DateInput
    start_today: YesNo = False
    contract_date: DateInput
    closing_date: DateInput
    move_in_date: DateInput
    interim_date: DateInput = None
    lease_refund_date: DateInput = "잔금일"
    lease_loan_repay_date: DateInput = "보증금반환일"
    lease_end_date: DateInput = None
    permit_date: DateInput = None
    deposit_ratio: Ratio = Decimal("0.1")
    interim_amount: Money = 0
    same_day_inflow_usable: YesNo = True
    variable_asset_mode: Literal["보수적", "공격적"] = "보수적"
    payday: int = Field(default=25, ge=1, le=31)
    expense_day: int | None = Field(default=None, ge=1, le=31)
    management_start_date: DateInput = "입주일"
    management_end_date: DateInput = None
    husband_net_pay: Money = 0
    wife_net_pay: Money = 0
    husband_gross: Money = 0
    wife_gross: Money = 0
    living_cost: Money = 0
    fixed_cost: Money = 0
    annual_cost: Money = 0
    annual_cost_month: int = Field(default=0, ge=0, le=12)
    fixed_in_living: YesNo = False
    mgmt_fee_default: Money = 0
    mgmt_in_living: YesNo = False
    childcare_cost: Money = 0
    birth_one_off: Money = 0
    property_tax_annual: Money = 0
    property_tax_month1: int = Field(default=7, ge=1, le=12)
    property_tax_month2: int = Field(default=9, ge=1, le=12)
    lease_loan_rate: Ratio = Decimal(0)
    lease_interest_in_living: YesNo = False
    monthly_saving: Money = 0
    saving_end_date: DateInput = None
    saving_in_spend_limit: YesNo = False
    monthly_repay_limit: Money = 4000000
    monthly_spend_limit: Money = 9000000
    min_emergency_cash: Money = 0
    target_cash_after_purchase: Money = 0
    mortgage_mode: str = "대출금 고정"
    mortgage_desired: Money = 0
    mortgage_cap: Money = 600000000
    mortgage_rate: Ratio = Decimal("0.04")
    mortgage_rate_type: str = "확인 필요"
    mortgage_years: int = Field(default=30, ge=1, le=50)
    mortgage_method: str = "원리금균등"
    mortgage_reset_after_months: int = Field(default=0, ge=0)
    mortgage_reset_rate: Ratio = Decimal(0)
    first_interest_adjustment: int = 0
    mortgage_round_unit: int = Field(default=1000000, ge=1)
    equal_principal_dsr_basis: str = "전체 평균"
    ltv: Ratio = Decimal("0.7")
    dsr_limit: Ratio = Decimal("0.4")
    stress_rate: Ratio = Decimal(0)
    bank_income: Money = 0
    existing_debt_annual: Money = 0
    bank_confirmed_limit: Money = 0
    loan_status: str = "미확정"
    mortgage_borrower: str = "아내"
    mortgage_quote_option: dict[str, str] = Field(default_factory=dict)
    credit_borrower: str = "남편"
    credit_use: YesNo = False
    credit_amount: Money = 0
    credit_amount_mode: Literal["기존", "자동", "직접"] = "기존"
    credit_rate: Ratio = Decimal("0.05")
    credit_method: str = "만기일시"
    credit_draw_date: DateInput = "잔금일+1"
    credit_repay_date: DateInput = None
    credit_status: str = "미확정"
    sub_loan_use: YesNo = False
    sub_principal_husband: Money = 0
    sub_principal_wife: Money = 0
    sub_ratio: Ratio = Decimal("0.9")
    sub_amount: Money = 0
    sub_amount_mode: Literal["기존", "자동", "직접"] = "기존"
    sub_savings_rate: Ratio = Decimal("0.031")
    sub_spread: Ratio = Decimal("0.013")
    sub_draw_date: DateInput = "잔금일+1"
    sub_repay_date: DateInput = None
    sub_status: str = "미확정"
    family_loan_rate: Ratio = Decimal(0)
    family_loan_monthly_principal: Money = 0
    family_loan_repay_start: DateInput = None
    ownership: str = "공동명의"
    husband_share: Ratio = Decimal("0.5")
    first_home_tax_relief: YesNo = False
    manual_tax_rate: Ratio = Decimal(0)
    card_pay_tax: YesNo = False
    card_repay_on_credit_draw: YesNo = False
    card_months: int = Field(default=3, ge=1, le=60)
    card_paid_installments: int = Field(default=0, ge=0)
    card_fee_rate: Ratio = Decimal(0)
    card_first_offset: int = Field(default=1, ge=0)
    lawyer_fee: Money = 2000000
    registry_fee: Money = 50000
    official_price_ratio: Ratio = Decimal("0.65")
    bond_buy_rate: Ratio = Decimal("0.031")
    bond_discount_rate: Ratio = Decimal("0.1")
    loan_stamp_share: Ratio = Decimal("0.5")
    brokerage_rate: Ratio = Decimal(0)
    repair_default: Money = 0
    appliances: Money = 0
    moving: Money = 0
    cleaning: Money = 0
    temp_housing: Money = 0
    comparison_area_m2: Decimal = Decimal("84.9")
    birth_date: DateInput = None
    maternity_start: DateInput = None
    maternity_months: int = Field(default=3, ge=0)
    maternity_pay_m12: Money = 0
    maternity_pay_m3: Money = 0
    wife_leave_start: DateInput = None
    wife_leave_months: int = Field(default=0, ge=0)
    return_delay_months: int = Field(default=0, ge=0)
    wife_gov_benefit_months: int = Field(default=12, ge=0)
    wife_ordinary_wage: Money = 0
    wife_company_topup: Money = 0
    wife_company_topup_months: int = Field(default=0, ge=0)
    benefit_pay_delay_months: int = Field(default=0, ge=0)
    husband_leave_use: YesNo = False
    husband_leave_start: DateInput = None
    husband_leave_months: int = Field(default=0, ge=0)
    husband_ordinary_wage: Money = 0
    husband_gov_benefit_months: int = Field(default=12, ge=0)
    husband_company_topup: Money = 0
    husband_company_topup_months: int = Field(default=0, ge=0)
    parents_6p6: YesNo = False
    land_permit_required: YesNo = True
    tenant_deferral_confirmed: YesNo = False
    setting_statuses: dict[str, str | None] = Field(default_factory=dict)

    @field_validator("mortgage_method")
    @classmethod
    def method_supported(cls, value: str) -> str:
        if value not in {"원리금균등", "원금균등"}:
            raise ValueError("지원 상환 방식: 원리금균등 / 원금균등")
        return value

    @field_validator("credit_method")
    @classmethod
    def credit_method_supported(cls, value: str) -> str:
        if value not in {"만기일시", "5년 분할", "5년분할", "원리금균등"}:
            raise ValueError("지원 신용 방식: 만기일시 / 5년 분할")
        return value


class FundEvent(InputModel):
    id: str
    data_kind: str = "실제"
    owner: str = "공동"
    type: str = "현금·예금"
    name: str = "자금"
    value: Money | None = None
    cash_out_amount: Money | None = None
    cost: Money | None = None
    is_variable: YesNo = False
    conservative_amount: Money | None = None
    aggressive_amount: Money | None = None
    available_date: DateInput = None
    use_for_purchase: YesNo = True
    status: str = "미확정"
    origin: str = "excel"
    note: Any = None

    @model_validator(mode="after")
    def valid_variable_amounts(self) -> "FundEvent":
        if self.is_variable:
            if "부채" in self.type or self.type in {"기타 나갈 돈", "가족 차입"}:
                raise ValueError("변동자산은 들어올 돈이나 투자자산에만 적용할 수 있습니다")
            if self.conservative_amount is None or self.aggressive_amount is None:
                raise ValueError("변동자산의 보수적·공격적 금액을 모두 입력하세요")
            if self.conservative_amount > self.aggressive_amount:
                raise ValueError("보수적 금액은 공격적 금액 이하여야 합니다")
        return self

    @property
    def active(self) -> bool:
        return self.data_kind != "예시" and self.status != "제외" and self.use_for_purchase

    @property
    def amount(self) -> int:
        value = self.cash_out_amount if self.cash_out_amount is not None else (self.value or 0)
        return (
            -value - (self.cost or 0)
            if "부채" in self.type or self.type == "기타 나갈 돈"
            else value - (self.cost or 0)
        )


class ParentSupport(InputModel):
    id: str = ""
    to: str = "공동"
    kind: str = "증여"
    amount: Money | None = None
    date: DateInput = None
    status: str = "미확정"
    origin: str = "excel"
    note: Any = None


class Listing(InputModel):
    id: str
    name: str = "매물"
    area_m2: Decimal = Field(default=Decimal("84.9"), gt=0)
    price: Money
    ask_price: Money = 0
    appraisal: Money | None = None
    mgmt_fee: Money | None = None
    repair: Money | None = None
    move_in_available: DateInput = None
    tenant: str = "집주인 거주"
    brokerage_amount: Money | None = None
    acquisition_tax_amount: Money | None = None


class BankOption(InputModel):
    id: str = ""
    method: str
    rate_type: str = "확인 필요"
    rate: Ratio
    limit: Money


class BankQuote(InputModel):
    id: str = ""
    date: date
    bank: str
    basis: str = ""
    options: list[BankOption]


class ExpenseItem(InputModel):
    id: str
    name: str = Field(min_length=1)
    category: Literal["생활비", "주거비", "고정비", "양육비", "기타"] = "기타"
    amount: Money
    start_date: DateInput = None
    end_date: DateInput = None
    pay_day: int | None = Field(default=None, ge=1, le=31)
    enabled: YesNo = True
    prorate: YesNo = False
    includes_lease_interest: YesNo = False
    includes_management: YesNo = False
    replaces_id: str | None = None


class LoanPrepayment(InputModel):
    id: str
    loan: Literal["mortgage", "credit", "sub"] = "credit"
    date: DateInput
    amount: Money
    fee: Money = 0
    method: Literal["납입 감소", "기간 단축"] = "납입 감소"
    enabled: YesNo = True


class Household(InputModel):
    settings: Settings
    fund_events: list[FundEvent] = Field(default_factory=list)
    parent_support: list[ParentSupport] = Field(default_factory=list)
    expense_items: list[ExpenseItem] | None = None
    loan_prepayments: list[LoanPrepayment] = Field(default_factory=list)
    listings: list[Listing] = Field(min_length=1)
    selected_listing: str = ""
    bank_quotes: list[BankQuote] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_ids(self) -> "Household":
        for ids, label in [
            ([x.id for x in self.fund_events], "자금"),
            ([x.id for x in self.listings], "매물"),
            ([x.id for x in self.expense_items or []], "지출"),
            ([x.id for x in self.loan_prepayments], "추가 상환"),
        ]:
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} ID가 중복됩니다")
        if self.selected_listing and self.selected_listing not in {row.id for row in self.listings}:
            raise ValueError("선택한 매물이 목록에 없습니다. 다른 매물을 선택하세요")
        return self

    def listing(self, listing_id: str | None = None) -> Listing:
        key = listing_id or self.selected_listing
        for item in self.listings:
            if item.id == key:
                return item.model_copy(deep=True)
        raise ValueError(f"매물을 찾지 못했습니다: {key}")

    def resolved(
        self, overrides: dict[str, Any] | None = None, *, as_of: date | None = None
    ) -> "Household":
        raw = self.model_dump()
        changes = dict(overrides or {})
        unknown = set(changes) - set(Settings.model_fields)
        if unknown:
            raise ValueError(f"알 수 없는 설정: {', '.join(sorted(unknown))}")
        raw["settings"].update(changes)
        s = raw["settings"]
        selected = s["mortgage_quote_option"].get(s["mortgage_method"])
        explicit = set(changes) | set(raw.get("calculation_override_keys", []))
        raw["calculation_override_keys"] = sorted(explicit)
        if selected:
            opts = [o for q in self.bank_quotes for o in q.options if o.id == selected]
            if len(opts) != 1:
                raise ValueError(f"은행 상담 옵션을 찾지 못했거나 중복됩니다: {selected}")
            opt = opts[0]
            if opt.method != s["mortgage_method"]:
                raise ValueError("은행 상담 옵션의 상환 방식이 다릅니다")
            for key, value in [("mortgage_rate", opt.rate), ("bank_confirmed_limit", opt.limit)]:
                if key not in explicit:
                    s[key] = value
        anchors = {key: s[key] for key in DATE_KEYS}
        for key in DATE_KEYS:
            s[key] = resolve(s[key], anchors, as_of=as_of)
        for e in raw["fund_events"]:
            e["available_date"] = resolve(e["available_date"], anchors, as_of=as_of)
        for e in raw["parent_support"]:
            e["date"] = resolve(e["date"], anchors, as_of=as_of)
        for e in raw["expense_items"] or []:
            if not e["enabled"]:
                continue
            if e["category"] == "양육비" and not e["start_date"]:
                raise ValueError(f"양육비 시작일을 입력하세요: {e['name']}")
            for key in ("start_date", "end_date"):
                e[key] = resolve(e[key], anchors, as_of=as_of)
            if e["start_date"] and e["end_date"] and e["end_date"] < e["start_date"]:
                raise ValueError(f"지출 종료일이 시작일보다 빠릅니다: {e['name']}")
        expense_map = {e["id"]: e for e in raw["expense_items"] or []}
        replaced: set[str] = set()
        for e in raw["expense_items"] or []:
            if not e["enabled"] or not e["replaces_id"]:
                continue
            previous = expense_map.get(e["replaces_id"])
            if previous is None or previous is e or previous["id"] in replaced:
                raise ValueError("교체할 지출이 없거나 중복된 교체입니다")
            cursor = previous
            visited = {e["id"]}
            while cursor:
                if cursor["id"] in visited:
                    raise ValueError("지출 교체가 순환합니다")
                visited.add(cursor["id"])
                cursor = expense_map.get(cursor["replaces_id"])
            start = e["start_date"]
            if not start or start <= (previous["start_date"] or s["asset_base_date"]):
                raise ValueError("지출 변경일은 기존 지출 시작일 이후여야 합니다")
            previous["end_date"] = min(previous["end_date"] or start, start - timedelta(days=1))
            previous["prorate"] = e["prorate"] = True
            replaced.add(previous["id"])
        for e in raw["loan_prepayments"]:
            if e["enabled"]:
                e["date"] = resolve(e["date"], anchors, as_of=as_of)
                if not e["date"] or not e["amount"]:
                    raise ValueError("추가 상환 날짜와 0원보다 큰 금액을 입력하세요")
        out = Household.model_validate(raw)
        for event in out.fund_events:
            if event.is_variable:
                event.cash_out_amount = (
                    event.conservative_amount
                    if out.settings.variable_asset_mode == "보수적"
                    else event.aggressive_amount
                )
        base, contract, closing, move = [
            out.day(k) for k in ("asset_base_date", "contract_date", "closing_date", "move_in_date")
        ]
        if not base <= contract <= closing <= move:
            raise ValueError("기준일 ≤ 계약일 ≤ 잔금일 ≤ 입주일이어야 합니다")
        interim = s["interim_date"]
        if s["interim_amount"] and (interim is None or not contract <= interim <= closing):
            raise ValueError("중도금일은 계약일과 잔금일 사이여야 합니다")
        for prefix in ("credit", "sub"):
            draw, repay = s[f"{prefix}_draw_date"], s[f"{prefix}_repay_date"]
            if draw and repay and repay < draw:
                raise ValueError("대출 상환일이 실행일보다 빠릅니다")
        return out

    def day(self, key: str) -> date:
        value = getattr(self.settings, key)
        if not isinstance(value, date):
            raise ValueError(f"필수 날짜를 입력하세요: {key}")
        return value


class LedgerEntry(BaseModel):
    date: date
    amount: int
    category: str
    label: str
    source: str
    balance: int = 0


class DailyBalance(BaseModel):
    date: date
    opening: int
    closing: int
    minimum: int
    debt_breakdown: dict[str, int] = Field(default_factory=dict)
    debt_total: int = 0
    net_cash: int = 0


class Check(BaseModel):
    name: str
    ok: bool
    reason: str
    numbers: dict[str, Any] = Field(default_factory=dict)
    assumptions: list[str] = Field(default_factory=list)


class Result(BaseModel):
    status: str
    checks: list[Check]
    kpis: dict[str, Any]
    costs: dict[str, Any]
    loans: dict[str, Any]
    ledger: list[LedgerEntry]
    daily_balances: list[DailyBalance]
    assumptions: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
