# jp-school-code-mcp

文部科学省の最新公表版を取り込み、学校名・都道府県での検索と学校コードによる照会を提供します。

Python 3.12以上と [uv](https://docs.astral.sh/uv/) を使用します。

```bash
uv sync --locked
uv run jp-school-code-mcp search-schools --name "東京大学" --prefecture 東京都
```

CLIの結果はUTF-8のJSONです。引数なしでstdio MCPサーバーが起動します。
MCPクライアントではコマンドを `uv`、引数を `--directory`、リポジトリの絶対パス、`run`、`jp-school-code-mcp` の順に設定します。

```python
import asyncio

from jp_school_code_mcp import search_schools

print(asyncio.run(search_schools(name="東京大学", prefecture="東京都")))
```

公表ページに掲載された最新データの基準日と暫定・確定の区分を返します。学校名は部分一致、都道府県名は完全一致です。確認間隔は7日です。

MCP・CLI・Pythonライブラリは同じローカルキャッシュを使います。保存先はWindowsでは `%LOCALAPPDATA%/jp-school-code-mcp`、その他では `$XDG_CACHE_HOME/jp-school-code-mcp` または `~/.cache/jp-school-code-mcp` です。`JP_SCHOOL_CODE_CACHE_DIR` で上書きできます。

期限を過ぎた最初の照会で配布元を確認し、対応している場合はHTTPの条件付き取得を使います。更新できない場合は最後に検証できた版を返し、`cache.refresh_failed` と `cache.checked_at` を確認できます。初回取得に失敗した場合はエラーになります。

```bash
uv run jp-school-code-mcp refresh
```

データ出典は [公式資料](https://www.mext.go.jp/b_menu/toukei/mext_01087.html) です。MIT Licenseはコードに適用します。

取得したデータを利用する際は文部科学省の出典を示し、加工した場合はその旨を明記してください。[文部科学省ウェブサイト利用規約](https://www.mext.go.jp/b_menu/1351168.htm)
