from datetime import date

import httpx
import pytest
import respx

from jp_school_code_mcp import compare_school_records, get_school, search_schools
from jp_school_code_mcp.client import SOURCE_URL

SCHOOL_CODE = "F113110000000"


def _csv(tokyo_address: str) -> str:
    rows = ["学校コード,学校種,都道府県番号,設置区分,本分校,学校名,学校所在地,郵便番号,設定,廃止"]
    for number in range(1, 48):
        prefecture = "東京" if number == 13 else "テスト"
        operator = "1" if number == 13 else "3"
        address = tokyo_address if number == 13 else "住所"
        rows.append(
            f"F1{number:02}{operator}10000000,F1(大学),{number:02}({prefecture}),{operator},1,"
            f"試験大学,{address},1234567,,"
        )
    return "\n".join(rows)


@pytest.mark.asyncio
@respx.mock
async def test_complete_release_is_shared_by_search_and_get(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JP_SCHOOL_CODE_CACHE_DIR", str(tmp_path))
    respx.get(SOURCE_URL).respond(
        text="最新の学校コード一覧 令和8年5月1日時点（暫定版） "
        '<a href="/content/current.csv">CSV</a> 過去の学校コード一覧',
    )
    route = respx.get("https://www.mext.go.jp/content/current.csv").mock(
        return_value=httpx.Response(200, text=_csv("新住所")),
    )
    search = await search_schools("試験", prefecture="東京都")
    assert search["total"] == 1
    assert search["edition"] == "暫定版"
    assert search["data_as_of"] == "2026-05-01"
    assert (await get_school(SCHOOL_CODE))["school"] == search["items"][0]
    filtered = await search_schools(school_type="F1", operator_category="1")
    assert filtered["items"] == search["items"]
    assert filtered["items"][0]["operator_category"] == "1"
    assert (await search_schools("試験", prefecture="東京都", school_type="B1"))["total"] == 0
    assert route.call_count == 1


@pytest.mark.asyncio
@respx.mock
async def test_compare_same_school_in_two_published_versions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JP_SCHOOL_CODE_CACHE_DIR", str(tmp_path))
    respx.get(SOURCE_URL).respond(
        text="最新の学校コード一覧 令和8年5月1日時点（暫定版） "
        '<a href="/content/current.csv">CSV</a> 過去の学校コード一覧 '
        '令和7年5月1日時点（確定版） <a href="/content/old.csv">CSV</a>'
        '令和6年5月1日時点（確定版） <a href="/content/unused.csv">CSV</a>',
    )
    current = respx.get("https://www.mext.go.jp/content/current.csv").respond(text=_csv("新住所"))
    old = respx.get("https://www.mext.go.jp/content/old.csv").respond(
        content=_csv("旧住所").encode("cp932"),
    )
    start, end = date(2025, 5, 1), date(2026, 5, 1)
    result = await compare_school_records(SCHOOL_CODE, start, end)
    assert result["changed_fields"] == ["address"]
    assert result["before"]["school"]["address"] == "旧住所"
    assert result["before"]["source_urls"][-1].endswith("/old.csv")
    assert result["before"]["edition"] == "確定版"
    assert result["after"]["data_as_of"] == "2026-05-01"
    assert (await get_school(SCHOOL_CODE, as_of=start)) == result["before"]
    missing = await compare_school_records("F113110000001", start, end)
    assert missing["before"]["school"] is None
    assert missing["changed_fields"] is None
    assert old.call_count == current.call_count == 1
    with pytest.raises(ValueError, match="does not list"):
        await get_school(SCHOOL_CODE, as_of=date(2025, 1, 1))
