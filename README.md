# jp-school-code-mcp

文部科学省が公表する学校コードを、学校名や都道府県、学校種、設置区分から調べられます。コードが分かっていれば、所在地などを照会し、2つの公表版で同じ学校の記録を比較できます。

## 利用前に

[uv](https://docs.astral.sh/uv/) と Git が必要です。Python 3.12以上に対応しています。APIキーの設定は不要です。

## MCPクライアントに登録する

公開GitHubリポジトリから `uvx` で起動します。初回は依存関係の準備に時間がかかることがあります。

### Codex

```sh
codex mcp add jp-school-code-mcp -- uvx --python 3.12 --from git+https://github.com/koizumikento/jp-school-code-mcp.git@main jp-school-code-mcp
codex mcp list
```

`codex mcp list` で登録を確認し、Codexの新しいセッションで `/mcp` を開くと、接続状態を確認できます。[Codexの公式設定ガイド](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)

Codexのデスクトップアプリでは、設定の「MCP servers」でSTDIOサーバーを追加し、下のJSON例と同じコマンド・引数を指定する方法もあります。

### Claude Desktop / Cursor

次のファイルに設定します。

- Claude Desktop（Windows） `%APPDATA%/Claude/claude_desktop_config.json`
- Claude Desktop（macOS） `~/Library/Application Support/Claude/claude_desktop_config.json`
- Cursor `.cursor/mcp.json`（プロジェクト内）

既に `mcpServers` がある場合は、その中にサーバーの項目を追加してください。保存後にクライアントを再起動し、ツールが表示されるか確認します。[設定ファイルの場所と接続手順](https://py.sdk.modelcontextprotocol.io/get-started/real-host/)

```json
{
  "mcpServers": {
    "jp-school-code-mcp": {
      "command": "uvx",
      "args": [
        "--python",
        "3.12",
        "--from",
        "git+https://github.com/koizumikento/jp-school-code-mcp.git@main",
        "jp-school-code-mcp"
      ]
    }
  }
}
```

`uvx` が見つからない場合は、設定のコマンドに実行ファイルの絶対パスを指定してください。

登録後は、チャットで次のように聞けます。

> 東京都の東京大学を探して、学校コードとデータの基準日を教えて。

## MCPツール

| ツール | 用途 |
| --- | --- |
| `search_schools` | 学校名（部分一致）、都道府県名（完全一致）、学校種、設置区分のうち1つ以上を指定して検索 |
| `get_school` | 学校コードを指定して1件を照会。`as_of` で公表版の基準日を指定できる |
| `compare_school_records` | 同じ学校コードについて、2つの公表版の記録、変更された項目名、各版の出典を返す |

学校種には `B1`（小学校）、`C1`（中学校）、`D1`（高等学校）、`F1`（大学）などがあります。設置区分 `operator_category` は `1`（国立）、`2`（公立）、`3`（私立）です。[学校コードの構成とコード表（PDF）](https://www.mext.go.jp/content/20210128-mxt_chousa01-000011635_01.pdf)

公表版の日付には、配布ページに載っている基準日を `YYYY-MM-DD` で指定します。学校種・都道府県番号・設置区分は学校コードの一部なので、同じコードでは学校名・所在地・郵便番号・廃止年月日の変更を比較します。片方の版にコードが見つからない場合、その版の `school` と比較結果の `changed_fields` は `null` になります。コードが変更された場合は、新旧のコードをそれぞれ照会してください。

過去版で同じコードに異なる行がある場合は、`school` を `null` とし、`conflicting_records` に候補と各CSVの出典を返します。その場合も `changed_fields` は `null` になります。

## CLIで使う

結果は標準出力にUTF-8のJSONで返ります。

```sh
uvx --python 3.12 --from git+https://github.com/koizumikento/jp-school-code-mcp.git@main jp-school-code-mcp search-schools --name "東京大学" --prefecture "東京都" --school-type F1 --operator-category 1
uvx --python 3.12 --from git+https://github.com/koizumikento/jp-school-code-mcp.git@main jp-school-code-mcp compare-school-records --school-code F113310103073 --from-date 2025-05-01 --to-date 2026-05-01
```

## Pythonから呼び出す

リポジトリをクローンし、依存関係を準備します。

```sh
git clone https://github.com/koizumikento/jp-school-code-mcp.git
cd jp-school-code-mcp
uv sync --locked
```

次の例を `example.py` に保存し、クローン先で `uv run --locked python example.py` を実行します。

```python
import asyncio
from datetime import date

from jp_school_code_mcp import compare_school_records, search_schools

print(asyncio.run(search_schools(prefecture="東京都", school_type="F1", operator_category="1")))
print(asyncio.run(compare_school_records("F113310103073", date(2025, 5, 1), date(2026, 5, 1))))
```

## データの更新

MCP・CLI・Pythonは同じローカルキャッシュを使います。最新版と、基準日を指定した公表版は別々に保存します。初回は版ごとに複数の公式CSVを取得するため、時間がかかることがあります。MCPクライアントでタイムアウトする場合は、使いたい版をCLIで先に照会してキャッシュを作成してください。確認間隔は7日で、期限を過ぎた最初の照会時に更新を確認します。更新に失敗した場合は直前の正常な版を返し、`cache.refresh_failed` と `cache.checked_at` で失敗の有無と最後に確認できた日時を判別できます。初回取得に失敗した場合はエラーになります。

最新版をすぐに更新したいときは次を実行します。

```sh
uvx --python 3.12 --from git+https://github.com/koizumikento/jp-school-code-mcp.git@main jp-school-code-mcp refresh
```

キャッシュはWindowsでは `%LOCALAPPDATA%/jp-school-code-mcp`、その他では `$XDG_CACHE_HOME/jp-school-code-mcp` または `~/.cache/jp-school-code-mcp` に保存されます。`JP_SCHOOL_CODE_CACHE_DIR` で保存先を指定できます。

## データの出典と利用条件

結果には公表版の基準日と暫定・確定の区分が付きます。利用する際は文部科学省の出典を示し、加工した場合はその旨を明記してください。[学校コードの配布ページ](https://www.mext.go.jp/b_menu/toukei/mext_01087.html)・[文部科学省ウェブサイト利用規約](https://www.mext.go.jp/b_menu/1351168.htm)

MIT Licenseはこのリポジトリのコードに適用します。
