import csv
import re
import unicodedata
from collections.abc import Callable
from datetime import date, timedelta
from io import StringIO
from typing import Annotated, Any
from urllib.parse import urljoin, urlsplit

from pydantic import Field, StringConstraints, validate_call

from ._cache import Document, Snapshot, cache_path, load_snapshot

SOURCE_URL = "https://www.mext.go.jp/b_menu/toukei/mext_01087.html"
SchoolCode = Annotated[str, StringConstraints(pattern=r"^[A-Z][0-9]{12}$")]
SearchText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


def _load_schools(fetch: Callable[[str], Document]) -> dict[str, Any]:
    page = fetch(SOURCE_URL).body.decode("utf-8-sig")
    _, current, section = page.partition("最新の学校コード一覧")
    section, archive, _ = section.partition("過去の学校コード一覧")
    release = re.search(
        r"令和([0-9元]+)年([0-9]+)月([0-9]+)日時点\s*[（(](暫定版|確定版)[）)]", section
    )
    hrefs = re.findall(r"""\bhref=["']([^"']+\.csv)["']""", section, re.IGNORECASE)
    urls = list(dict.fromkeys(urljoin(SOURCE_URL, href) for href in hrefs))
    if not current or not archive or not release or not urls:
        raise ValueError("MEXT's current school-code release could not be identified.")
    if any(
        (parsed := urlsplit(url)).netloc != "www.mext.go.jp"
        or parsed.scheme != "https"
        or not parsed.path.startswith("/content/")
        for url in urls
    ):
        raise ValueError("MEXT's school-code page contains an unexpected download URL.")
    year, month, day, edition = release.groups()
    data_as_of = date(2018 + (1 if year == "元" else int(year)), int(month), int(day))
    entries: dict[str, dict[str, str | None]] = {}
    prefecture_codes: set[str] = set()
    for url in urls:
        raw = fetch(url).body
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp932")
        rows = csv.reader(StringIO(text), strict=True)
        for header in rows:
            if header and header[0] == "学校コード":
                break
        else:
            raise ValueError("MEXT CSV has no school-code header.")
        if header[1:3] != ["学校種", "都道府県番号"] or header[5:8] != [
            "学校名",
            "学校所在地",
            "郵便番号",
        ]:
            raise ValueError("MEXT school-code CSV columns have changed.")
        for row in rows:
            if not any(row):
                continue
            prefecture = re.fullmatch(r"([0-9]{2})\(([^)]+)\)", row[2]) if len(row) >= 10 else None
            if not prefecture or not re.fullmatch(r"[A-Z][0-9]{12}", row[0]) or not row[5]:
                raise ValueError("Invalid row in the MEXT school-code CSV.")
            prefecture_code, prefecture_name = prefecture.groups()
            prefecture_codes.add(prefecture_code)
            if not prefecture_name.endswith(("都", "道", "府", "県")) or prefecture_name == "京都":
                prefecture_name += {"東京": "都", "京都": "府", "大阪": "府"}.get(
                    prefecture_name, "県"
                )
            entry = {
                "school_code": row[0],
                "school_type": row[1],
                "prefecture": prefecture_name,
                "name": row[5],
                "address": row[6] or None,
                "postal_code": row[7] or None,
                "closed_on": row[9] or None,
            }
            if row[0] in entries and entries[row[0]] != entry:
                raise ValueError("The MEXT school-code files contain conflicting records.")
            entries[row[0]] = entry
    if prefecture_codes != {f"{code:02}" for code in range(1, 48)}:
        raise ValueError("MEXT school-code release does not cover all 47 prefectures.")
    return {
        "data_as_of": data_as_of.isoformat(),
        "edition": edition,
        "source_urls": [SOURCE_URL, *urls],
        "entries": entries,
    }


async def _snapshot(*, force: bool = False) -> Snapshot:
    path = cache_path("jp-school-code-mcp", "JP_SCHOOL_CODE_CACHE_DIR")
    return await load_snapshot(path, "current", timedelta(days=7), _load_schools, force=force)


@validate_call
async def search_schools(
    name: SearchText,
    prefecture: SearchText | None = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
    offset: Annotated[int, Field(ge=0)] = 0,
) -> dict[str, Any]:
    """Find schools by partial name and optional exact prefecture. Use next_offset for more."""
    snapshot = await _snapshot()
    query = unicodedata.normalize("NFKC", name).casefold()
    entries = [
        item
        for item in snapshot.data["entries"].values()
        if (prefecture is None or item["prefecture"] == prefecture)
        and query in unicodedata.normalize("NFKC", item["name"]).casefold()
    ]
    end = offset + limit
    return {
        "items": entries[offset:end],
        "total": len(entries),
        "next_offset": end if end < len(entries) else None,
        "edition": snapshot.data["edition"],
        **snapshot.metadata(),
    }


@validate_call
async def get_school(school_code: SchoolCode) -> dict[str, Any]:
    """Read one school record from the latest MEXT release by its 13-character school code."""
    snapshot = await _snapshot()
    return {
        "school": snapshot.data["entries"].get(school_code),
        "edition": snapshot.data["edition"],
        **snapshot.metadata(),
    }


async def refresh_cache() -> dict[str, Any]:
    """Check the current MEXT release immediately."""
    snapshot = await _snapshot(force=True)
    return {
        "schools": len(snapshot.data["entries"]),
        "edition": snapshot.data["edition"],
        **snapshot.metadata(),
    }
