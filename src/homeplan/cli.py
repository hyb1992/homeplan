"""한국어 CLI. 데이터 변경은 영향 미리보기 후 확인·백업·원자적 저장."""

import copy
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from .checks import evaluate as evaluate_engine
from .dates import parse_user_date
from .importer import extract_excel, merge_import
from .models import FundEvent, Household, ParentSupport, Result
from .money import parse_money
from .solver import max_price as solve
from .storage import dumps, load_rules, read_json, save_json

app = typer.Typer(
    help="일별 잔고로 검토하는 신혼집 매수계획",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
fund_app = typer.Typer(help="자금 항목 추가·수정·제외", no_args_is_help=True)
support_app = typer.Typer(help="부모님 증여·차입 일정", no_args_is_help=True)
app.add_typer(fund_app, name="fund")
app.add_typer(support_app, name="support")
console = Console(highlight=False)


@dataclass
class Context:
    data: Path
    rules: Path | None
    as_of: date


def today_korea() -> date:
    return datetime.now(timezone(timedelta(hours=9))).date()


@app.callback()
def main(
    ctx: typer.Context,
    data: Path = typer.Option(Path("data/household.local.json"), help="가구 JSON 파일"),
    rules: Path | None = typer.Option(None, help="규칙 폴더"),
    as_of: str | None = typer.Option(None, help="지금·상담 경과일의 계산 날짜 YYYY-MM-DD"),
) -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ctx.obj = Context(data, rules, date.fromisoformat(as_of) if as_of else today_korea())


def configuration(ctx: typer.Context) -> Context:
    obj = ctx.obj
    if not isinstance(obj, Context):
        raise RuntimeError("CLI 초기화 오류")
    return obj


def fail(message: str) -> None:
    console.print(f"오류: {message}", style="red", markup=False)
    raise typer.Exit(2)


def load(ctx: typer.Context) -> tuple[Context, dict[str, Any], Household]:
    c = configuration(ctx)
    try:
        raw = read_json(c.data)
        return c, raw, Household.model_validate(raw)
    except (ValueError, OSError) as exc:
        fail(str(exc))
        raise AssertionError("unreachable") from exc


def overrides(values: list[str] | None) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for value in values or []:
        if "=" not in value:
            raise ValueError("--set은 key=value 형식입니다")
        key, text = value.split("=", 1)
        changes[key] = text
    return changes


def render(result: Result) -> None:
    console.print(f"판정: {result.status}", markup=False)
    table = Table("조건", "결과", "근거")
    for check in result.checks:
        table.add_row(check.name, "충족" if check.ok else "미충족", check.reason)
    console.print(table)
    k = result.kpis
    console.print(
        f"일별 최저: {k['min_balance_overall']:,}원 ({k['min_balance_date']}) / 월말 최저: {k['month_end_min_balance']:,}원"
    )
    for warning in result.warnings:
        console.print(f"전제: {warning}", markup=False)
    for assumption in result.assumptions:
        if "label" in assumption:
            console.print(
                f"미확정: {assumption['id']} {assumption['label']} / 제외 시 {assumption.get('without', {})}",
                markup=False,
            )


@app.command("evaluate")
def evaluate_cmd(
    ctx: typer.Context,
    listing: str | None = None,
    sets: list[str] | None = typer.Option(None, "--set"),
    confirmed_only: bool = typer.Option(False, "--확정만", "--confirmed-only"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    c, _, h = load(ctx)
    try:
        result = evaluate_engine(
            h,
            listing,
            load_rules(c.rules),
            overrides(sets),
            confirmed_only=confirmed_only,
            as_of=c.as_of,
        )
    except (ValueError, OSError) as exc:
        fail(str(exc))
        return
    if json_output:
        typer.echo(dumps(result))
    else:
        render(result)


@app.command("max-price")
def max_price_cmd(
    ctx: typer.Context,
    listing: str | None = None,
    sets: list[str] | None = typer.Option(None, "--set"),
    mode: str = "general",
    minimum: int = 100000,
    maximum: int = 3000000000,
    precision: int = 100000,
    confirmed_only: bool = typer.Option(False, "--확정만", "--confirmed-only"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    c, _, h = load(ctx)
    try:
        result = solve(
            h,
            listing,
            load_rules(c.rules),
            overrides(sets),
            mode=mode,
            minimum=minimum,
            maximum=maximum,
            precision=precision,
            confirmed_only=confirmed_only,
            as_of=c.as_of,
        )
    except (ValueError, OSError) as exc:
        fail(str(exc))
        return
    if json_output:
        typer.echo(dumps(result))
    else:
        price = result["price"]
        console.print(f"최대 매수가: {price:,}원" if price is not None else "가능한 가격 없음")
        console.print(f"제한 조건: {result['binding_check']}", markup=False)
        if result["gate_failures"]:
            console.print(
                f"일정 관문 제외 참고 한도: {result['conditional_price']}원 / {result['conditional_binding_check']}"
            )
        console.print(
            f"모드: {mode} / 정밀도: {precision:,}원 / 은행·가구 전제 확인 필요: {result['conditional']}"
        )


@app.command("ledger")
def ledger_cmd(
    ctx: typer.Context,
    listing: str | None = None,
    sets: list[str] | None = typer.Option(None, "--set"),
    start: str | None = typer.Option(None, "--from"),
    end: str | None = typer.Option(None, "--to"),
    monthly: bool = False,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    c, _, h = load(ctx)
    try:
        result = evaluate_engine(
            h,
            listing,
            load_rules(c.rules),
            overrides(sets),
            analyze_assumptions=False,
            as_of=c.as_of,
        )
        rows = [
            row.model_dump(mode="json")
            for row in result.ledger
            if (not start or row.date >= date.fromisoformat(start))
            and (not end or row.date <= date.fromisoformat(end))
        ]
    except (ValueError, OSError) as exc:
        fail(str(exc))
        return
    if json_output:
        typer.echo(dumps(result.kpis["month_end_balance"] if monthly else rows))
    elif monthly:
        table = Table("월", "월말 잔고(원)")
        for month, balance in result.kpis["month_end_balance"].items():
            table.add_row(month, f"{balance:,}")
        console.print(table)
    else:
        table = Table("날짜", "항목", "유입·유출(원)", "잔고(원)")
        for row in rows:
            table.add_row(row["date"], row["label"], f"{row['amount']:,}", f"{row['balance']:,}")
        console.print(table)


@app.command("check-data")
def check_data(ctx: typer.Context, json_output: bool = typer.Option(False, "--json")) -> None:
    c, raw, h = load(ctx)
    try:
        result = evaluate_engine(
            h, None, load_rules(c.rules), analyze_assumptions=False, as_of=c.as_of
        )
    except (ValueError, OSError) as exc:
        fail(str(exc))
        return
    report = {
        "valid": result.status != "입력 미완료",
        "status": result.status,
        "fund_count": len(h.fund_events),
        "support_count": len(h.parent_support),
        "missing_labels": raw.get("_missing_labels", []),
        "import_warnings": raw.get("_import_warnings", []),
        "warnings": result.warnings,
        "assumptions": result.assumptions,
    }
    typer.echo(dumps(report)) if json_output else console.print(report)
    if not report["valid"]:
        raise typer.Exit(1)


def preview_save(c: Context, before: dict[str, Any], after: dict[str, Any], yes: bool) -> None:
    try:
        h = Household.model_validate(after)
        h.resolved(as_of=c.as_of)
        rules = load_rules(c.rules)
        old = (
            evaluate_engine(
                Household.model_validate(before),
                None,
                rules,
                analyze_assumptions=False,
                as_of=c.as_of,
            )
            if before
            else None
        )
        new = evaluate_engine(h, None, rules, analyze_assumptions=False, as_of=c.as_of)
        if old:
            delta = new.kpis["closing_cash_available"] - old.kpis["closing_cash_available"]
            console.print(f"저장 미리보기: 잔금일 가용 {delta:+,}원 / {old.status} → {new.status}")
        else:
            console.print(f"신규 입력 미리보기: {len(h.fund_events)}개 자금 / {new.status}")
        if yes or typer.confirm("저장할까요?", default=False):
            backup = save_json(c.data, after)
            console.print(f"저장 완료: {c.data}\n백업: {backup or '신규 파일'}", markup=False)
        else:
            console.print("저장하지 않았습니다.")
    except (ValueError, OSError) as exc:
        fail(str(exc))


@app.command("import-excel")
def import_cmd(
    ctx: typer.Context,
    source: Path,
    yes: bool = typer.Option(False, "--yes", "-y"),
    refresh_imported: bool = typer.Option(
        False, help="기존 Excel 출처 항목·설정도 갱신(기본은 앱 값 보존)"
    ),
) -> None:
    c = configuration(ctx)
    try:
        before = read_json(c.data) if c.data.exists() else {}
        incoming = extract_excel(source, c.as_of)
        after = merge_import(before, incoming, refresh_imported=refresh_imported)
        console.print("엑셀을 입력 자료로 가져옵니다. 앱 저장 데이터가 기준입니다.")
        console.print(
            "기존 Excel 출처 데이터도 갱신합니다."
            if refresh_imported
            else "기존 값은 보존하고 새 항목만 추가합니다."
        )
        for warning in incoming.get("_import_warnings", []):
            console.print(warning, markup=False)
        preview_save(c, before, after, yes)
    except (ValueError, OSError, KeyError) as exc:
        fail(str(exc))


def next_id(rows: list[dict[str, Any]], prefix: str) -> str:
    existing = {row.get("id") for row in rows}
    n = 1
    while f"{prefix}{n:02}" in existing:
        n += 1
    return f"{prefix}{n:02}"


FUND_TYPES = [
    "현금·예금",
    "적금·청년도약계좌",
    "투자자산",
    "성과급·환급금",
    "퇴직 관련 수령금",
    "전세보증금",
    "부모님 증여",
    "부모님 차입",
    "기타 들어올 돈",
    "기타 나갈 돈",
]


@fund_app.command("add")
def fund_add(
    ctx: typer.Context,
    amount: str | None = None,
    name: str | None = None,
    kind: str | None = typer.Option(None, "--type"),
    when: str | None = typer.Option(None, "--date"),
    owner: str = "공동",
    status: str | None = None,
    sale_amount: str | None = None,
    cost: str | None = None,
    use_for_purchase: bool = True,
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    c, before, h = load(ctx)
    interactive = amount is None or kind is None or when is None
    try:
        if kind is None:
            for i, label in enumerate(FUND_TYPES, 1):
                console.print(f"{i}. {label}")
            choice = typer.prompt("무슨 돈인가요? 번호", type=int)
            if not 1 <= choice <= len(FUND_TYPES):
                raise ValueError("항목 번호를 확인하세요")
            kind = FUND_TYPES[choice - 1]
        if kind not in FUND_TYPES:
            raise ValueError("지원 유형: " + ", ".join(FUND_TYPES))
        name = name or (typer.prompt("이름", default=kind) if interactive else kind)
        if interactive:
            owner = typer.prompt("누구 돈인가요? 남편/아내/공동", default=owner)
        amount = amount or typer.prompt("금액(예: 3600만, 1억 2천만)")
        when = when or typer.prompt("언제 쓸 수 있나요? 지금/날짜/잔금일-1", default="지금")
        base = h.resolved().day("asset_base_date")
        when = parse_user_date(when, base)
        status = status or (
            typer.prompt("확정 여부", default="미확정") if interactive else "미확정"
        )
        if interactive:
            use_for_purchase = typer.confirm("매수에 쓸 돈인가요?", default=True)
            if kind == "투자자산":
                sale_amount = sale_amount or typer.prompt("매도 예상액", default=amount)
                cost = cost or typer.prompt("세금·수수료", default="0")
        after = copy.deepcopy(before)
        if kind.startswith("부모님"):
            key = next_id(after["parent_support"], "P")
            row = ParentSupport(
                id=key,
                to=owner,
                kind="차입" if "차입" in kind else "증여",
                amount=parse_money(amount),
                date=when,
                status=status,
                origin="app",
            ).model_dump(mode="json")
            after["parent_support"].append(row)
        else:
            key = next_id(after["fund_events"], "A")
            event = FundEvent(
                id=key,
                owner=owner,
                type=kind,
                name=name,
                value=parse_money(amount),
                cash_out_amount=parse_money(sale_amount) if sale_amount else None,
                cost=parse_money(cost) if cost else None,
                available_date=when,
                status=status,
                use_for_purchase=use_for_purchase,
                origin="app",
            )
            after["fund_events"].append(event.model_dump(mode="json"))
        console.print(f"추가: {key} {name} / {parse_money(amount):,}원 / {when}", markup=False)
        preview_save(c, before, after, yes)
    except (ValueError, OSError) as exc:
        fail(str(exc))


def list_rows(ctx: typer.Context, section: str) -> None:
    _, raw, _ = load(ctx)
    table = Table("ID", "유형", "이름·수신", "금액(원)", "날짜", "상태")
    for i, row in enumerate(raw.get(section, []), 1):
        amount = row.get(
            "amount",
            row.get("cash_out_amount")
            if row.get("cash_out_amount") is not None
            else row.get("value"),
        )
        table.add_row(
            row.get("id") or f"P{i:02}",
            str(row.get("type", row.get("kind", ""))),
            str(row.get("name", row.get("to", ""))),
            f"{amount:,}" if amount is not None else "미입력",
            str(row.get("available_date", row.get("date", "지금"))),
            str(row.get("status", "미확정")),
        )
    console.print(table)


@fund_app.command("list")
def fund_list(ctx: typer.Context) -> None:
    list_rows(ctx, "fund_events")


@support_app.command("list")
def support_list(ctx: typer.Context) -> None:
    list_rows(ctx, "parent_support")


def change_row(
    ctx: typer.Context,
    section: str,
    key: str,
    sets: list[str] | None,
    remove: bool,
    hard: bool,
    yes: bool,
) -> None:
    c, before, h = load(ctx)
    after = copy.deepcopy(before)
    rows = after[section]
    try:
        row = next((r for i, r in enumerate(rows, 1) if (r.get("id") or f"P{i:02}") == key), None)
        if row is None:
            raise ValueError(f"항목을 찾지 못했습니다: {key}")
        if remove:
            rows.remove(row) if hard else row.update({"status": "제외", "origin": "app"})
        else:
            changes = overrides(sets)
            if not changes:
                field = typer.prompt("바꿀 항목(value/available_date/status/name)")
                changes[field] = typer.prompt("새 값")
            model = FundEvent if section == "fund_events" else ParentSupport
            if set(changes) - set(model.model_fields):
                raise ValueError(
                    "알 수 없는 항목: " + ", ".join(set(changes) - set(model.model_fields))
                )
            for field, value in changes.items():
                if field in {"value", "cash_out_amount", "cost", "amount"}:
                    value = parse_money(value)
                if field in {"available_date", "date"}:
                    value = parse_user_date(value, h.resolved().day("asset_base_date"))
                row[field] = value
            row["origin"] = "app"
        console.print(f"{'영구 삭제' if hard else '제외' if remove else '수정'}: {key}")
        preview_save(c, before, after, yes)
    except (ValueError, OSError) as exc:
        fail(str(exc))


@fund_app.command("edit")
def fund_edit(
    ctx: typer.Context,
    key: str,
    sets: list[str] | None = typer.Option(None, "--set"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    change_row(ctx, "fund_events", key, sets, False, False, yes)


@fund_app.command("remove")
def fund_remove(
    ctx: typer.Context, key: str, hard: bool = False, yes: bool = typer.Option(False, "--yes", "-y")
) -> None:
    change_row(ctx, "fund_events", key, None, True, hard, yes)


@support_app.command("add")
def support_add(
    ctx: typer.Context,
    amount: str | None = None,
    when: str | None = typer.Option(None, "--date"),
    kind: str = "증여",
    owner: str = "공동",
    status: str = "미확정",
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    if kind not in {"증여", "차입"}:
        fail("지원 유형은 증여 / 차입입니다")
    fund_add(
        ctx,
        amount=amount,
        name=f"부모님 {kind}",
        kind=f"부모님 {kind}",
        when=when,
        owner=owner,
        status=status,
        sale_amount=None,
        cost=None,
        use_for_purchase=True,
        yes=yes,
    )


@support_app.command("edit")
def support_edit(
    ctx: typer.Context,
    key: str,
    sets: list[str] | None = typer.Option(None, "--set"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    change_row(ctx, "parent_support", key, sets, False, False, yes)


@support_app.command("remove")
def support_remove(
    ctx: typer.Context, key: str, hard: bool = False, yes: bool = typer.Option(False, "--yes", "-y")
) -> None:
    change_row(ctx, "parent_support", key, None, True, hard, yes)
