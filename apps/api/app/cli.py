"""Operations CLI.

python -m app.cli db init
python -m app.cli seed-config [--dir data/seed]
python -m app.cli ingest --provider file --all
python -m app.cli ingest --provider file --path places.json --region <slug>
python -m app.cli ingest --provider kakao_local --region <slug>
python -m app.cli ingest-job 12
python -m app.cli ingest-bulk download --source all          # keyless public files → %LOCALAPPDATA%
python -m app.cli ingest-bulk semas [--path store.zip] [--sido 서울 --sido 부산]
python -m app.cli ingest-bulk goodprice [--path goodprice.csv] [--store-path store.zip]
python -m app.cli ingest-bulk std --kind parks|museums|tourist|markets|festivals [--path file.csv]
python -m app.cli ingest-bulk tourapi [--force]              # TourAPI nationwide (TOURAPI_SERVICE_KEY)
python -m app.cli ingest-bulk all                            # semas → goodprice → every std kind
python -m app.cli ingest-bulk stats
python -m app.cli create-admin --email me@example.com [--print-token]
python -m app.cli purge-courses [--dry-run]                  # never-saved courses older than 24 h
python -m app.cli purge-accounts [--dry-run]                 # accounts 30 d after DELETE /v1/me
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Annotated

import typer

from app.core import security
from app.core.config import API_ROOT, Settings, get_settings
from app.infra.db.session import Database
from app.infra.ingestion.base import ProviderNotConfiguredError
from app.infra.ingestion.bulk import download as bulk_download
from app.infra.ingestion.bulk import runner as bulk
from app.infra.ingestion.bulk.std_datasets import KINDS as STD_KINDS
from app.infra.ingestion.config_loader import ConfigFormatError, load_config
from app.infra.ingestion.registry import UnknownProviderError
from app.repositories.user_repo import SqlUserRepository
from app.services import retention_service as retention
from app.services.ingestion_runner import IngestionError, ingest, run_job

cli = typer.Typer(no_args_is_help=True, add_completion=False, help="내가짠데이 API operations")
db_cli = typer.Typer(no_args_is_help=True, help="Database commands")
cli.add_typer(db_cli, name="db")
bulk_cli = typer.Typer(no_args_is_help=True, help="Nationwide public bulk files (no API key needed)")
cli.add_typer(bulk_cli, name="ingest-bulk")


def _run[T](fn: Callable[[Database, Settings], Awaitable[T]]) -> T:
    async def main() -> T:
        settings = get_settings()
        db = Database(settings)
        try:
            return await fn(db, settings)
        finally:
            await db.dispose()

    return asyncio.run(main())


def _fail(message: str) -> typer.Exit:
    typer.secho(message, fg=typer.colors.RED, err=True)
    return typer.Exit(code=1)


@db_cli.command("init")
def db_init() -> None:
    """SQLite: create tables from metadata. PostgreSQL: `alembic upgrade head`."""
    settings = get_settings()
    if settings.is_sqlite:
        _run(lambda db, _s: db.create_all())
        typer.echo(f"tables created ({settings.database_url})")
        return
    result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API_ROOT, check=False)
    raise typer.Exit(code=result.returncode)


@cli.command("seed-config")
def seed_config(
    directory: Annotated[
        Path | None, typer.Option("--dir", help="regions/categories/tags/purposes JSON 위치")
    ] = None,
) -> None:
    """Upsert regions, categories, tags, purposes (templates, scoring profiles, tag affinities)."""

    async def job(db: Database, settings: Settings) -> None:
        async with db.sessionmaker() as session:
            report = await load_config(session, directory or settings.seed_dir)
            await session.commit()
        typer.echo(
            f"regions={report.regions} categories={report.categories} tags={report.tags} "
            f"purposes={report.purposes} templates={report.templates}"
        )

    try:
        _run(job)
    except (ConfigFormatError, KeyError) as exc:
        raise _fail(f"invalid seed config: {exc}") from exc


@cli.command("ingest")
def ingest_cmd(
    provider: Annotated[
        str, typer.Option(help="file | kakao_local | naver_search | google_places | tourapi | data_go_kr")
    ],
    region: Annotated[
        str | None, typer.Option(help="region slug (file provider: defaults to the file's 'region')")
    ] = None,
    path: Annotated[Path | None, typer.Option(help="JSON/CSV file for the file provider")] = None,
    all_files: Annotated[
        bool, typer.Option("--all", help="file provider: every file under <seed>/places")
    ] = False,
) -> None:
    """Run the ingestion pipeline (fetch → diff → upsert → merge → stats → outbox)."""

    async def job(db: Database, settings: Settings) -> None:
        targets: Sequence[Path | None]
        if provider == "file":
            if all_files:
                targets = sorted((settings.seed_dir / "places").glob("*.json"))
            elif path is not None:
                targets = [path]
            else:
                raise IngestionError("file provider needs --path or --all")
            if not targets:
                raise IngestionError(f"no files under {settings.seed_dir / 'places'}")
        else:
            targets = [None]
        for target in targets:
            slug, report = await ingest(db, settings, provider_name=provider, region_slug=region, path=target)
            typer.echo(
                f"[{provider}] {slug}: fetched={report.fetched} created={report.created} "
                f"updated={report.updated} skipped={report.skipped} failed={report.failed}"
            )
            for error in report.errors[:5]:
                typer.secho(f"  ! {error}", fg=typer.colors.YELLOW, err=True)

    try:
        _run(job)
    except (IngestionError, UnknownProviderError, ProviderNotConfiguredError, ValueError) as exc:
        raise _fail(str(exc)) from exc


@cli.command("ingest-job")
def ingest_job(job_id: int) -> None:
    """Execute a queued ingestion_job row (created via the admin API) without Celery."""

    async def job(db: Database, settings: Settings) -> None:
        report = await run_job(db, settings, job_id)
        typer.echo(f"job {job_id}: fetched={report.fetched} created={report.created} failed={report.failed}")

    try:
        _run(job)
    except IngestionError as exc:
        raise _fail(str(exc)) from exc


def _raw_file(source_key: str, path: Path | None) -> Path:
    """Explicit --path wins; otherwise the file `ingest-bulk download` saved."""
    target = path or bulk_download.default_raw_dir() / bulk_download.load_sources()[source_key].filename
    if not target.exists():
        raise _fail(
            f"{target} not found — run `ingest-bulk download --source {source_key}` "
            "or pass --path to a manually downloaded file"
        )
    return target


@bulk_cli.command("download")
def bulk_download_cmd(
    source: Annotated[str, typer.Option(help="all | semas | goodprice | parks | museums | …")] = "all",
    raw_dir: Annotated[Path | None, typer.Option(help="default: %LOCALAPPDATA%/naegajjanday/raw")] = None,
) -> None:
    """Download keyless data.go.kr files exactly like the portal's download button (no captcha bypass)."""
    sources = bulk_download.load_sources()
    keys = list(sources) if source == "all" else [source]
    unknown = [k for k in keys if k not in sources]
    if unknown:
        raise _fail(f"unknown source {unknown}; choose from {', '.join(sources)}")
    target_dir = raw_dir or bulk_download.default_raw_dir()
    failed = False
    for key in keys:
        try:
            target = bulk_download.target_path(sources[key], target_dir)
            saved = asyncio.run(bulk_download.download(sources[key], target))
            typer.echo(f"[{key}] {saved} ({saved.stat().st_size:,} bytes)")
        except bulk_download.ManualDownloadRequiredError as exc:
            failed = True
            typer.secho(f"[{key}] {exc}", fg=typer.colors.YELLOW, err=True)
        except Exception as exc:  # network / portal change: tell the operator how to do it by hand
            failed = True
            steps = bulk_download.manual_steps(sources[key], target_dir / sources[key].filename)
            typer.secho(f"[{key}] {type(exc).__name__}: {exc}", fg=typer.colors.YELLOW, err=True)
            typer.secho(steps, fg=typer.colors.YELLOW, err=True)
    if failed:
        raise typer.Exit(code=1)


@bulk_cli.command("semas")
def bulk_semas(
    path: Annotated[Path | None, typer.Option(help="zip | directory of CSVs | one CSV")] = None,
    sido: Annotated[
        list[str] | None, typer.Option(help="only files whose name contains this (서울, 부산, …); repeatable")
    ] = None,
    skip_regions: Annotated[bool, typer.Option(help="do not (re)derive 시도/시군구/핫스팟 regions")] = False,
    close_unseen: Annotated[
        bool, typer.Option(help="mark stores missing from the new file as closed (loaded 시도 only)")
    ] = False,
) -> None:
    """소상공인 상가(상권)정보 → places (restaurants, cafes, bars, activities) + nationwide regions."""
    source = _raw_file("semas", path)

    async def job(db: Database, _settings: Settings) -> None:
        report = await bulk.load_semas(
            db, source, only=sido or (), regions=not skip_regions, close_unseen=close_unseen, log=typer.echo
        )
        typer.echo(f"[semas] {report.line()}")

    try:
        _run(job)
    except bulk.BulkIngestError as exc:
        raise _fail(str(exc)) from exc


@bulk_cli.command("goodprice")
def bulk_goodprice(
    path: Annotated[Path | None, typer.Option(help="착한가격업소 CSV")] = None,
    store_path: Annotated[Path | None, typer.Option(help="상가정보 zip/dir (address → coordinates)")] = None,
) -> None:
    """착한가격업소 → measured menu prices (address-joined with 상가정보; run `semas` first)."""
    source, stores = _raw_file("goodprice", path), _raw_file("semas", store_path)

    async def job(db: Database, _settings: Settings) -> None:
        report = await bulk.load_goodprice(db, source, stores, log=typer.echo)
        typer.echo(f"[goodprice] {report.line()}")

    _run(job)


@bulk_cli.command("std")
def bulk_std(
    kind: Annotated[str, typer.Option(help=" | ".join(STD_KINDS))],
    path: Annotated[Path | None, typer.Option(help="표준데이터 CSV")] = None,
) -> None:
    """전국 표준데이터 (공원·박물관/미술관·관광지·전통시장 → places, 문화축제 → events)."""
    if kind not in STD_KINDS:
        raise _fail(f"--kind must be one of {', '.join(STD_KINDS)}")
    source = _raw_file(kind, path)

    async def job(db: Database, _settings: Settings) -> None:
        report = await bulk.load_std(db, kind, source, log=typer.echo)
        typer.echo(f"[std:{kind}] {report.line()}")

    try:
        _run(job)
    except bulk.BulkIngestError as exc:
        raise _fail(str(exc)) from exc


@bulk_cli.command("tourapi")
def bulk_tourapi(
    raw_dir: Annotated[
        Path | None, typer.Option(help="default: %LOCALAPPDATA%/naegajjanday/raw/tourapi")
    ] = None,
    force: Annotated[bool, typer.Option(help="re-download even if the cache is under a week old")] = False,
) -> None:
    """한국관광공사 TourAPI 전국 적재: 실제 장소 사진 · 문화시설 · 레포츠 · 축제 (약 12회 호출, 원본 캐시)."""
    target = raw_dir or bulk_download.default_raw_dir() / "tourapi"

    async def job(db: Database, settings: Settings) -> None:
        reports = await bulk.load_tourapi(
            db, target, settings.tourapi_service_key, force=force, log=typer.echo
        )
        for label, report in reports.items():
            typer.echo(f"[tourapi:{label}] {report.line()}")

    try:
        _run(job)
    except bulk.BulkIngestError as exc:
        raise _fail(str(exc)) from exc


@bulk_cli.command("all")
def bulk_all() -> None:
    """Everything that was downloaded, in dependency order: semas → goodprice → std kinds."""
    raw_dir, sources = bulk_download.default_raw_dir(), bulk_download.load_sources()

    async def job(db: Database, _settings: Settings) -> None:
        semas = raw_dir / sources["semas"].filename
        if not semas.exists():
            raise bulk.BulkIngestError(f"{semas} not found — run `ingest-bulk download` first")
        typer.echo(f"[semas] {(await bulk.load_semas(db, semas, log=typer.echo)).line()}")
        good = raw_dir / sources["goodprice"].filename
        if good.exists():
            typer.echo(f"[goodprice] {(await bulk.load_goodprice(db, good, semas, log=typer.echo)).line()}")
        for kind in STD_KINDS:
            file = raw_dir / sources[kind].filename
            if file.exists():
                typer.echo(f"[std:{kind}] {(await bulk.load_std(db, kind, file, log=typer.echo)).line()}")
            else:
                typer.secho(f"[std:{kind}] skipped — {file} not found", fg=typer.colors.YELLOW)

    try:
        _run(job)
    except bulk.BulkIngestError as exc:
        raise _fail(str(exc)) from exc


@bulk_cli.command("regions")
def bulk_regions(
    path: Annotated[Path | None, typer.Option(help="상가정보 zip | directory | CSV")] = None,
) -> None:
    """Re-derive 시도/시군구/핫스팟 regions and move every place to its most specific region.

    Run this after editing `data/bulk/regions_kr.json` (new hotspot, changed radius): the loaders
    skip unchanged rows, so they alone never re-home a place.
    """
    source = _raw_file("semas", path)

    async def job(db: Database, _settings: Settings) -> None:
        moved = await bulk.rebuild_regions(db, source, log=typer.echo)
        typer.echo(f"[regions] moved={moved:,}")

    try:
        _run(job)
    except (bulk.BulkIngestError, ValueError) as exc:
        raise _fail(str(exc)) from exc


@bulk_cli.command("stats")
def bulk_stats() -> None:
    """Row counts per role / 시도, estimated vs measured prices, regions per level."""
    typer.echo(json.dumps(_run(lambda db, _s: bulk.stats(db)), ensure_ascii=False, indent=2))


@cli.command("create-admin")
def create_admin(
    email: Annotated[str, typer.Option(help="OAuth 로그인에 쓰는 (검증된) 이메일")],
    role: Annotated[str, typer.Option(help="admin | operator")] = "admin",
    print_token: Annotated[bool, typer.Option(help="로컬 테스트용 access token 출력 (15분)")] = False,
) -> None:
    """Grant an admin role. The account is linked on the first OAuth login with the same e-mail."""
    if role not in {"admin", "operator"}:
        raise _fail("role must be admin or operator")

    async def job(db: Database, settings: Settings) -> None:
        async with db.sessionmaker() as session:
            users = SqlUserRepository(session)
            user = await users.get_by_email(email)
            if user is None:
                user = await users.create(email=email, nickname=email.split("@")[0], role=role)
            user.role = role
            await session.commit()
            typer.echo(f"{email} → role={role} id={user.public_id}")
            if print_token:
                token, _ = security.create_access_token(settings, user_public_id=user.public_id, role=role)
                typer.echo(token)

    _run(job)


@cli.command("purge-courses")
def purge_courses(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="지우지 않고 대상 개수만 출력")] = False,
) -> None:
    """Delete never-saved courses older than UNSAVED_COURSE_TTL_HOURS (default 24). Cron-friendly."""
    report = _run(lambda db, settings: retention.purge_unsaved_courses(db, settings, dry_run=dry_run))
    if dry_run:
        typer.echo(f"[purge-courses] would delete courses={report.matched}")
        return
    typer.echo(f"[purge-courses] deleted courses={report.deleted}")


@cli.command("purge-accounts")
def purge_accounts(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="지우지 않고 대상 개수만 출력")] = False,
) -> None:
    """Hard-purge accounts whose deletion grace period (ACCOUNT_PURGE_GRACE_DAYS, default 30) is over."""
    report = _run(lambda db, settings: retention.purge_deleted_accounts(db, settings, dry_run=dry_run))
    if dry_run:
        typer.echo(f"[purge-accounts] would delete accounts={report.matched} courses={report.courses}")
        return
    typer.echo(
        f"[purge-accounts] deleted accounts={report.accounts} courses={report.courses} "
        f"logs_anonymized={report.logs_anonymized}"
    )


@cli.command("eval-courses")
def eval_courses(
    scope: Annotated[str, typer.Option(help="quick(4개 지역) | full(20개 지역)")] = "quick",
    region: Annotated[list[str] | None, typer.Option(help="이 지역만 (여러 번 가능)")] = None,
    purpose: Annotated[list[str] | None, typer.Option(help="이 목적만")] = None,
    start: Annotated[list[str] | None, typer.Option(help="이 시작 시각만, 예: 18:30")] = None,
    style: Annotated[list[str] | None, typer.Option(help="efficient | fun")] = None,
    save: Annotated[str | None, typer.Option(help="이 이름으로 기준선 저장")] = None,
    compare: Annotated[str | None, typer.Option(help="이 기준선과 전후 비교")] = None,
    show: Annotated[bool, typer.Option(help="모든 코스를 한 줄씩 출력")] = False,
) -> None:
    """추천 품질 점수표: 실제 파이프라인을 시나리오 행렬로 돌려 품질 규칙 위반을 집계한다 (DB 기록 없음)."""
    from app.evaluation import harness

    spec = harness.load_spec()
    only = {"region": region or [], "purpose": purpose or [], "start": start or [], "style": style or []}
    scenarios = harness.build_scenarios(spec, scope, only)

    async def job(db: Database, settings: Settings) -> None:
        outcomes = await harness.run(db, settings, scenarios, spec)
        summary = harness.summarize(outcomes, spec["rules"])
        if show:
            for o in outcomes:
                flags = ",".join(sorted({f.code for f in o.findings})) or "ok"
                path = " → ".join(f"{s['at']} {s['name']}" for s in o.stops) or (o.error or "-")
                typer.echo(f"{o.scenario.key:<52} [{flags}]")
                typer.echo(f"    {path}")
        typer.echo(harness.render(summary, outcomes))
        if compare:
            typer.echo("")
            typer.echo(harness.compare(compare, summary, outcomes))
        if save:
            typer.echo(f"기준선 저장: {harness.save(save, summary, outcomes)}")

    _run(job)


if __name__ == "__main__":
    cli()
