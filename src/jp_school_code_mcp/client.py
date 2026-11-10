import csv
import re
import unicodedata
from collections.abc import Callable
from datetime import date, timedelta
from io import StringIO
from typing import Annotated, Any, Literal
from urllib.parse import urljoin, urlsplit

from pydantic import Field, StringConstraints, validate_call

from ._cache import Document, Snapshot, cache_path, load_snapshot

SOURCE_URL = "https://www.mext.go.jp/b_menu/toukei/mext_01087.html"
SchoolCode = Annotated[str, StringConstraints(pattern=r"^[A-Z][0-9]{12}$")]
SearchText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
SchoolType = Literal["A1", "A2", "B1", "C1", "C2", "D1", "D2", "E1", "F1", "F2", "G1", "H1", "H2"]
OperatorCategory = Literal["1", "2", "3"]
RELEASE_HEADING = re.compile(
    r"令和([0-9元]+)年([0-9]+)月([0-9]+)日時点\s*[（(](暫定版|確定版)[）)]"
)


def _release_files(page: str, as_of: date | None) -> tuple[date, str, list[str]]:
    _, current, section = page.partition("最新の学校コード一覧")
    current_section, archive, archive_section = section.partition("過去の学校コード一覧")
    if not current or not archive:
        raise ValueError("MEXT's school-code release list could not be identified.")
    sections = [current_section]
    if as_of is not None:
        sections.append(archive_section.partition("都道府県が定める付番方針")[0])
    for section in sections:
        releases = list(RELEASE_HEADING.finditer(section))
        for index, release in enumerate(releases):
            year, month, day, edition = release.groups()
            data_as_of = date(2018 + (1 if year == "元" else int(year)), int(month), int(day))
            if as_of is None or as_of == data_as_of:
                end = releases[index + 1].start() if index + 1 < len(releases) else len(section)
                return data_as_of, edition, _csv_urls(section[release.end() : end])
    if as_of is not None:
        raise ValueError(f"MEXT does not list a school-code release for {as_of.isoformat()}.")
    raise ValueError("MEXT's current school-code release could not be identified.")


def _csv_urls(section: str) -> list[str]:
    hrefs = re.findall(r"""\bhref=["']([^"']+\.csv)["']""", section, re.IGNORECASE)
    urls = list(dict.fromkeys(urljoin(SOURCE_URL, href) for href in hrefs))
    if not urls:
        raise ValueError("MEXT's school-code release does not list CSV files.")
    if any(
        (parsed := urlsplit(url)).netloc != "www.mext.go.jp"
        or parsed.scheme != "https"
        or not parsed.path.startswith("/content/")
        for url in urls
    ):
        raise ValueError("MEXT's school-code page contains an unexpected download URL.")
    return urls


def _load_schools(fetch: Callable[[str], Document], as_of: date | None = None) -> dict[str, Any]:
    page = fetch(SOURCE_URL).body.decode("utf-8-sig")
    data_as_of, edition, urls = _release_files(page, as_of)
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


async def _snapshot(*, force: bool = False, as_of: date | None = None) -> Snapshot:
    path = cache_path("jp-school-code-mcp", "JP_SCHOOL_CODE_CACHE_DIR")
    key = "current" if as_of is None else f"release-{as_of.isoformat()}"
    return await load_snapshot(
        path, key, timedelta(days=7), lambda fetch: _load_schools(fetch, as_of), force=force
    )


def _school_record(item: dict[str, Any]) -> dict[str, Any]:
    # The first two characters identify the type, and the fifth identifies the operator.
    return {**item, "operator_category": item["school_code"][4]}


@validate_call
async def search_schools(
    name: SearchText | None = None,
    prefecture: SearchText | None = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 10,
    offset: Annotated[int, Field(ge=0)] = 0,
    *,
    school_type: SchoolType | None = None,
    operator_category: OperatorCategory | None = None,
) -> dict[str, Any]:
    """Find schools by partial name, exact prefecture, school type or operator category.

    School type codes include B1 (elementary), C1 (junior high), D1 (high) and F1 (university).
    Operator categories are 1 (national), 2 (public) and 3 (private). Use next_offset for more.
    """
    if all(value is None for value in (name, prefecture, school_type, operator_category)):
        raise ValueError("Supply at least one school search condition.")
    snapshot = await _snapshot()
    query = unicodedata.normalize("NFKC", name).casefold() if name is not None else None
    entries = [
        item
        for item in snapshot.data["entries"].values()
        if (prefecture is None or item["prefecture"] == prefecture)
        and (school_type is None or item["school_code"].startswith(school_type))
        and (operator_category is None or item["school_code"][4] == operator_category)
        and (query is None or query in unicodedata.normalize("NFKC", item["name"]).casefold())
    ]
    end = offset + limit
    return {
        "items": [_school_record(item) for item in entries[offset:end]],
        "total": len(entries),
        "next_offset": end if end < len(entries) else None,
        "edition": snapshot.data["edition"],
        **snapshot.metadata(),
    }


@validate_call
async def get_school(school_code: SchoolCode, *, as_of: date | None = None) -> dict[str, Any]:
    """Read a school record by 13-character code. Omit as_of for the latest MEXT release."""
    snapshot = await _snapshot(as_of=as_of)
    school = snapshot.data["entries"].get(school_code)
    return {
        "school": _school_record(school) if school is not None else None,
        "edition": snapshot.data["edition"],
        **snapshot.metadata(),
    }


@validate_call
async def compare_school_records(
    school_code: SchoolCode, from_date: date, to_date: date
) -> dict[str, Any]:
    """Compare a school's published records on two MEXT reference dates (YYYY-MM-DD)."""
    if from_date >= to_date:
        raise ValueError("from_date must be earlier than to_date.")
    before = await get_school(school_code, as_of=from_date)
    after = await get_school(school_code, as_of=to_date)
    previous, current = before["school"], after["school"]
    changed_fields = (
        [field for field in previous if previous[field] != current[field]]
        if previous is not None and current is not None
        else None
    )
    return {
        "school_code": school_code,
        "before": before,
        "after": after,
        "changed_fields": changed_fields,
    }


async def refresh_cache() -> dict[str, Any]:
    """Check the current MEXT release immediately."""
    snapshot = await _snapshot(force=True)
    return {
        "schools": len(snapshot.data["entries"]),
        "edition": snapshot.data["edition"],
        **snapshot.metadata(),
    }
