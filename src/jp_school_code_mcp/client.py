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
PREFECTURES = (
    "北海道 青森県 岩手県 宮城県 秋田県 山形県 福島県 茨城県 栃木県 群馬県 埼玉県 千葉県 "
    "東京都 神奈川県 新潟県 富山県 石川県 福井県 山梨県 長野県 岐阜県 静岡県 愛知県 三重県 "
    "滋賀県 京都府 大阪府 兵庫県 奈良県 和歌山県 鳥取県 島根県 岡山県 広島県 山口県 徳島県 "
    "香川県 愛媛県 高知県 福岡県 佐賀県 長崎県 "
    "熊本県 大分県 宮崎県 鹿児島県 沖縄県"
).split()


def _release_files(page: str, as_of: date | None) -> tuple[date, str, list[str], bool]:
    _, current, section = page.partition("最新の学校コード一覧")
    current_section, archive, archive_section = section.partition("過去の学校コード一覧")
    if not current or not archive:
        raise ValueError("MEXT's school-code release list could not be identified.")
    sections = [current_section]
    if as_of is not None:
        sections.append(archive_section.partition("都道府県が定める付番方針")[0])
    for section_index, section in enumerate(sections):
        releases = list(RELEASE_HEADING.finditer(section))
        for index, release in enumerate(releases):
            year, month, day, edition = release.groups()
            data_as_of = date(2018 + (1 if year == "元" else int(year)), int(month), int(day))
            if as_of is None or as_of == data_as_of:
                end = releases[index + 1].start() if index + 1 < len(releases) else len(section)
                urls = _csv_urls(section[release.end() : end])
                return data_as_of, edition, urls, section_index > 0
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
    data_as_of, edition, urls, historical = _release_files(page, as_of)
    entries: dict[str, dict[str, str | None]] = {}
    conflicts: dict[str, list[dict[str, Any]]] = {}
    original_rows: dict[str, tuple[list[str], list[str], str]] = {}
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
            prefecture = (
                re.fullmatch(r"([0-9]{1,2})(?:\(([^)]+)\))?", row[2]) if len(row) >= 10 else None
            )
            school_code = row[0].strip()
            if not prefecture or not re.fullmatch(r"[A-Z][0-9]{12}", school_code) or not row[5]:
                raise ValueError("Invalid row in the MEXT school-code CSV.")
            prefecture_code, prefecture_name = prefecture.groups()
            prefecture_code = prefecture_code.zfill(2)
            if not 1 <= int(prefecture_code) <= len(PREFECTURES):
                raise ValueError("Invalid prefecture number in the MEXT school-code CSV.")
            prefecture_codes.add(prefecture_code)
            postal_code = row[7] or None
            if prefecture_name is None:
                prefecture_name = PREFECTURES[int(prefecture_code) - 1]
                # Some archived files dropped leading zeroes from numeric columns.
                if postal_code and re.fullmatch(r"[0-9]{5,6}", postal_code):
                    postal_code = postal_code.zfill(7)
            elif (
                not prefecture_name.endswith(("都", "道", "府", "県")) or prefecture_name == "京都"
            ):
                prefecture_name += {"東京": "都", "京都": "府", "大阪": "府"}.get(
                    prefecture_name, "県"
                )
            entry = {
                "school_code": school_code,
                "school_type": row[1],
                "prefecture": prefecture_name,
                "name": row[5],
                "address": row[6] or None,
                "postal_code": postal_code,
                "closed_on": row[9] or None,
            }
            previous = entries.get(school_code)
            if previous is not None:
                if historical:
                    old_header, old_row, old_url = original_rows[school_code]
                    if row != old_row:
                        candidates = conflicts.setdefault(
                            school_code, [_source_record(previous, old_header, old_row, old_url)]
                        )
                        if all(candidate["source_values"] != row for candidate in candidates):
                            candidates.append(_source_record(entry, header, row, url))
                elif previous != entry:
                    raise ValueError("The MEXT school-code files contain conflicting records.")
                continue
            entries[school_code] = entry
            if historical:
                original_rows[school_code] = header, row, url
    if prefecture_codes != {f"{code:02}" for code in range(1, 48)}:
        raise ValueError("MEXT school-code release does not cover all 47 prefectures.")
    data = {
        "data_as_of": data_as_of.isoformat(),
        "edition": edition,
        "source_urls": [SOURCE_URL, *urls],
        "entries": entries,
    }
    if conflicts:
        data["conflicts"] = conflicts
    return data


def _source_record(
    item: dict[str, Any], header: list[str], row: list[str], url: str
) -> dict[str, Any]:
    return {
        "school": _school_record(item),
        "source_url": url,
        "source_columns": header,
        "source_values": row,
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
    conflicts = snapshot.data.get("conflicts", {}).get(school_code)
    school = None if conflicts else snapshot.data["entries"].get(school_code)
    return {
        "school": _school_record(school) if school is not None else None,
        **({"conflicting_records": conflicts} if conflicts else {}),
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
        [
            field
            for field in ("name", "address", "postal_code", "closed_on")
            if previous[field] != current[field]
        ]
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
