import httpx
import pytest
import respx

from jp_school_code_mcp import get_school, search_schools
from jp_school_code_mcp.client import SOURCE_URL


@pytest.mark.asyncio
@respx.mock
async def test_complete_release_is_shared_by_search_and_get(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("JP_SCHOOL_CODE_CACHE_DIR", str(tmp_path))
    respx.get(SOURCE_URL).respond(
        text="最新の学校コード一覧 令和8年5月1日時点（暫定版） "
        '<a href="/content/current.csv">CSV</a> 過去の学校コード一覧',
    )
    rows = ["学校コード,学校種,都道府県番号,設置区分,本分校,学校名,学校所在地,郵便番号,設定,廃止"]
    for number in range(1, 48):
        prefecture = "東京" if number == 13 else "テスト"
        rows.append(f"A{number:012},F1,{number:02}({prefecture}),1,1,試験大学,住所,1234567,,")
    route = respx.get("https://www.mext.go.jp/content/current.csv").mock(
        return_value=httpx.Response(200, text="\n".join(rows)),
    )
    search = await search_schools("試験", prefecture="東京都")
    assert search["total"] == 1
    assert search["edition"] == "暫定版"
    assert search["data_as_of"] == "2026-05-01"
    code = search["items"][0]["school_code"]
    assert (await get_school(code))["school"] == search["items"][0]
    assert route.call_count == 1
