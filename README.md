# jp-school-code-mcp

文部科学省が公表する学校コードを、学校名や都道府県から調べられます。学校コードが分かっていれば、所在地などの情報を直接取得できます。

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
| `search_schools` | 学校名の部分一致で検索。都道府県名で絞り込み可能 |
| `get_school` | 学校コードを指定して1件を照会 |

## CLIで使う

結果は標準出力にUTF-8のJSONで返ります。

```sh
uvx --python 3.12 --from git+https://github.com/koizumikento/jp-school-code-mcp.git@main jp-school-code-mcp search-schools --name "東京大学" --prefecture "東京都"
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

from jp_school_code_mcp import search_schools

print(asyncio.run(search_schools(name="東京大学", prefecture="東京都")))
```

## データの更新

MCP・CLI・Pythonは同じローカルキャッシュを使います。初回は複数の公式CSVを取得するため、時間がかかることがあります。MCPクライアントでタイムアウトする場合は、下のコマンドを先に実行してキャッシュを作成してください。確認間隔は7日で、期限を過ぎた最初の照会時に更新を確認します。更新に失敗した場合は直前の正常な版を返し、`cache.refresh_failed` と `cache.checked_at` で失敗の有無と最後に確認できた日時を判別できます。初回取得に失敗した場合はエラーになります。

すぐに更新したいときは次を実行します。

```sh
uvx --python 3.12 --from git+https://github.com/koizumikento/jp-school-code-mcp.git@main jp-school-code-mcp refresh
```

キャッシュはWindowsでは `%LOCALAPPDATA%/jp-school-code-mcp`、その他では `$XDG_CACHE_HOME/jp-school-code-mcp` または `~/.cache/jp-school-code-mcp` に保存されます。`JP_SCHOOL_CODE_CACHE_DIR` で保存先を指定できます。

## データの出典と利用条件

結果には公表版の基準日と暫定・確定の区分が付きます。利用する際は文部科学省の出典を示し、加工した場合はその旨を明記してください。[学校コードの配布ページ](https://www.mext.go.jp/b_menu/toukei/mext_01087.html)・[文部科学省ウェブサイト利用規約](https://www.mext.go.jp/b_menu/1351168.htm)

MIT Licenseはこのリポジトリのコードに適用します。
