"""Download helper for keyless data.go.kr bulk files.

It follows exactly what the portal's own download buttons do and nothing more:

* file data    : dataset page → `selectFileDataDownload.do` (metadata) → `check-limit.json` →
  `fileDownload.do`
* standard data: `columList.json` (header) → `standard.json` pages (10 000 rows each) → CSV
* localdata    : the 인허가 / 생활편의 files that moved from localdata.go.kr to the portal in 2026 are
  "downloaded at the provider": dataset page → `file.localdata.go.kr/file/<slug>/info` →
  `validate/download-count` (the site's own rate limit — a 429 stops us) → `download/<slug>/info`

If the portal asks for a captcha (or anything else interactive) we stop with
`ManualDownloadRequiredError` — never work around it. Every loader accepts a local `--path`, so a
manual download always works.
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

from app.core.config import API_ROOT

PORTAL = "https://www.data.go.kr"
SOURCES_FILE = API_ROOT / "data" / "bulk" / "sources.json"
USER_AGENT = "Mozilla/5.0 (compatible; bulk-file-download)"  # generic; never carries personal info
STD_PAGE_SIZE = 10_000
PAGE_DELAY_S = 0.3
LOCALDATA = "https://file.localdata.go.kr"
_DETAIL_PK_RE = re.compile(r"fn_fileDataDown\('(\d+)',\s*'([^']+)',\s*'[^']*',\s*'(\d+)'")


class ManualDownloadRequiredError(RuntimeError):
    """The portal wants a human (captcha / login). Carries the steps the operator has to follow."""


@dataclass(frozen=True, slots=True)
class BulkSource:
    key: str
    kind: Literal["file", "standard", "localdata"]
    public_data_pk: str
    title: str
    filename: str
    slug: str = ""  # kind=localdata: the dataset name in file.localdata.go.kr/file/<slug>/info

    @property
    def page_url(self) -> str:
        if self.kind == "localdata":
            return f"{LOCALDATA}/file/{self.slug}/info"
        suffix = "fileData.do" if self.kind == "file" else "standard.do"
        return f"{PORTAL}/data/{self.public_data_pk}/{suffix}"


def default_data_dir() -> Path:
    """Bulk data lives outside the (OneDrive-synced) repository."""
    base = os.environ.get("NAEGAJJANDAY_DATA_DIR")
    if base:
        return Path(base)
    local = os.environ.get("LOCALAPPDATA")
    root = Path(local) if local else Path.home() / ".local" / "share"
    return root / "naegajjanday"


def default_raw_dir() -> Path:
    return default_data_dir() / "raw"


def load_sources(path: Path = SOURCES_FILE) -> dict[str, BulkSource]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        key: BulkSource(
            key=key,
            kind=row["kind"],
            public_data_pk=str(row.get("public_data_pk", "")),
            title=row["title"],
            filename=row["filename"],
            slug=str(row.get("slug", "")),
        )
        for key, row in data["sources"].items()
    }


def manual_steps(source: BulkSource, target: Path) -> str:
    button = {
        "file": "'다운로드' 버튼",
        "standard": "'CSV' 행의 '다운로드' 버튼",
        "localdata": "'전국 파일 다운로드' 버튼",
    }[source.kind]
    return (
        f"자동 다운로드 불가: {source.title}\n"
        f"  1) 브라우저로 {source.page_url} 접속\n"
        f"  2) {button} 클릭 (보안문자가 나오면 입력)\n"
        f"  3) 받은 파일을 {target} 로 저장\n"
        f"  4) 해당 ingest-bulk 명령을 --path 로 다시 실행"
    )


def parse_detail_pk(html: str, public_data_pk: str) -> tuple[str, str] | None:
    """(publicDataDetailPk, fileDetailSn) of the current file, read from the dataset page."""
    for pk, detail_pk, file_sn in _DETAIL_PK_RE.findall(html):
        if pk == public_data_pk:
            return detail_pk, file_sn
    return None


def rows_to_csv(
    path: Path, header: list[str], codes: list[str], pages: Iterable[list[dict[str, Any]]]
) -> int:
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        for page in pages:
            for row in page:
                writer.writerow(["" if row.get(c) is None else row.get(c) for c in codes])
                count += 1
    return count


async def _download_file(client: httpx.AsyncClient, source: BulkSource, target: Path) -> None:
    page = await client.get(source.page_url)
    page.raise_for_status()
    found = parse_detail_pk(page.text, source.public_data_pk)
    if found is None:
        raise ManualDownloadRequiredError(manual_steps(source, target))
    detail_pk, file_sn = found
    meta_resp = await client.get(
        f"{PORTAL}/tcs/dss/selectFileDataDownload.do",
        params={
            "publicDataPk": source.public_data_pk,
            "publicDataDetailPk": detail_pk,
            "fileDetailSn": file_sn,
        },
    )
    meta_resp.raise_for_status()
    meta = json.loads(meta_resp.text)
    if meta.get("status") is not True or not meta.get("atchFileId"):
        raise ManualDownloadRequiredError(manual_steps(source, target))
    form = {"atchFileId": str(meta["atchFileId"]), "fileDetailSn": str(meta["fileDetailSn"])}
    limit = await client.post(f"{PORTAL}/cmm/cmm/check-limit.json", data=form)
    if limit.status_code != 200 or limit.json().get("needCaptcha"):
        raise ManualDownloadRequiredError(manual_steps(source, target))
    tmp = target.with_suffix(target.suffix + ".part")
    async with client.stream(
        "GET", f"{PORTAL}/cmm/cmm/fileDownload.do", params={**form, "dataNm": source.key}
    ) as resp:
        resp.raise_for_status()
        if "html" in resp.headers.get("content-type", ""):
            raise ManualDownloadRequiredError(manual_steps(source, target))
        with tmp.open("wb") as fh:
            async for chunk in resp.aiter_bytes(1 << 20):
                fh.write(chunk)
    tmp.replace(target)


async def _download_standard(client: httpx.AsyncClient, source: BulkSource, target: Path) -> None:
    head = await client.get(
        f"{PORTAL}/download/columList.json", params={"pk": source.public_data_pk, "ext": "CSV"}
    )
    head.raise_for_status()
    info = head.json()
    columns = info.get("columList") or []
    total = int(info.get("totalCount") or 0)
    table = info.get("tableVO") or {}
    if not columns or not total or not table.get("svcTableNm"):
        raise ManualDownloadRequiredError(manual_steps(source, target))
    pages: list[list[dict[str, Any]]] = []
    for page_no in range(1, -(-total // STD_PAGE_SIZE) + 1):
        resp = await client.get(
            f"{PORTAL}/download/standard.json",
            params={
                "publicDataPk": source.public_data_pk,
                "colNmList": table.get("colNmList") or [],
                "totalCount": total,
                "svcTableNm": table["svcTableNm"],
                "perPage": STD_PAGE_SIZE,
                "page": page_no,
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        if not isinstance(rows, list):
            raise ManualDownloadRequiredError(manual_steps(source, target))
        pages.append(rows)
        await asyncio.sleep(PAGE_DELAY_S)
    tmp = target.with_suffix(target.suffix + ".part")
    rows_to_csv(tmp, [str(c["columNm"]) for c in columns], [str(c["columCode"]) for c in columns], pages)
    tmp.replace(target)


async def _download_localdata(client: httpx.AsyncClient, source: BulkSource, target: Path) -> None:
    """What the '전국 파일 다운로드' button does: open the page, ask the site whether another download
    is allowed right now, then fetch the file. A refusal is final — we do not retry around it."""
    if not source.slug:
        raise ManualDownloadRequiredError(manual_steps(source, target))
    referer = {"Referer": source.page_url}
    page = await client.get(source.page_url, headers={"Referer": PORTAL + "/"})
    page.raise_for_status()
    if f"/file/download/{source.slug}/info" not in page.text:
        raise ManualDownloadRequiredError(manual_steps(source, target))
    allowed = await client.get(f"{LOCALDATA}/file/validate/download-count", headers=referer)
    if allowed.status_code != 200:
        raise ManualDownloadRequiredError(manual_steps(source, target))
    tmp = target.with_suffix(target.suffix + ".part")
    async with client.stream(
        "GET", f"{LOCALDATA}/file/download/{source.slug}/info", headers=referer
    ) as resp:
        resp.raise_for_status()
        if "html" in resp.headers.get("content-type", ""):
            raise ManualDownloadRequiredError(manual_steps(source, target))
        with tmp.open("wb") as fh:
            async for chunk in resp.aiter_bytes(1 << 20):
                fh.write(chunk)
    tmp.replace(target)


def target_path(source: BulkSource, raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    return raw_dir / source.filename


async def download(source: BulkSource, target: Path, client: httpx.AsyncClient | None = None) -> Path:
    owned = (
        httpx.AsyncClient(
            timeout=httpx.Timeout(600.0, connect=15.0),
            follow_redirects=True,
            headers={
                "User-Agent": USER_AGENT,
                "Referer": source.page_url,
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        if client is None
        else None
    )
    http = client or owned
    assert http is not None
    try:
        if source.kind == "file":
            await _download_file(http, source, target)
        elif source.kind == "localdata":
            await _download_localdata(http, source, target)
        else:
            await _download_standard(http, source, target)
    finally:
        if owned is not None:
            await owned.aclose()
    return target
