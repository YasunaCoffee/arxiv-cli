"""Typerアプリ・コマンド定義"""

import webbrowser
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box

from arx import __version__
from arx.utils import extract_arxiv_id, is_safe_url

app = typer.Typer(
    name="arx",
    help="arXiv論文管理CLIツール",
    add_completion=False,
)
rss_app = typer.Typer(help="RSSフィード管理")
app.add_typer(rss_app, name="rss")

console = Console()
err_console = Console(stderr=True, style="bold red")


def _get_conn():
    """DB接続を取得する。"""
    from arx.db import get_connection
    return get_connection()


def _resolve_id(value: str) -> str:
    """入力値からarXiv IDを取得する。失敗時はエラー終了。"""
    arxiv_id = extract_arxiv_id(value)
    if not arxiv_id:
        err_console.print(f"[bold red]エラー:[/] 有効なarXiv IDまたはURLではありません: {value}")
        raise typer.Exit(1)
    return arxiv_id


# --- arx add ---

@app.command()
def add(
    identifier: str = typer.Argument(..., help="arXiv IDまたはURL"),
) -> None:
    """論文を追加する。"""
    arxiv_id = _resolve_id(identifier)

    console.print(f"[cyan]取得中:[/] {arxiv_id} ...")

    try:
        from arx.api import fetch_paper
        meta = fetch_paper(arxiv_id)
    except RuntimeError as e:
        err_console.print(f"[bold red]エラー:[/] {e}")
        raise typer.Exit(1)

    from arx.db import add_paper
    with _get_conn() as conn:
        added = add_paper(
            conn,
            meta.arxiv_id,
            meta.title,
            meta.authors,
            meta.abstract,
            meta.url,
            meta.published,
        )

    if added:
        console.print(f"[green]追加しました:[/] {meta.arxiv_id}")
        console.print(f"  {meta.title}")
    else:
        console.print(f"[yellow]既に登録済みです:[/] {arxiv_id}")


# --- arx list ---

@app.command(name="list")
def list_papers(
    unread: bool = typer.Option(False, "--unread", help="未読のみ表示"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="タグでフィルタ"),
    sort: str = typer.Option("added", "--sort", "-s", help="ソート順: added/date/title"),
    limit: int = typer.Option(50, "--limit", "-n", help="表示件数"),
) -> None:
    """論文一覧を表示する。"""
    from arx.db import list_papers as db_list

    with _get_conn() as conn:
        papers = db_list(conn, unread=unread, tag=tag, sort=sort, limit=limit)

    if not papers:
        console.print("[dim]論文がありません。[/]")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("ID", style="cyan", no_wrap=True, min_width=12)
    table.add_column("タイトル", max_width=50)
    table.add_column("著者", max_width=25)
    table.add_column("日付", no_wrap=True)
    table.add_column("状態", no_wrap=True)
    table.add_column("タグ", max_width=20)

    for p in papers:
        status = "[green]既読[/]" if p["read_at"] else "[yellow]未読[/]"
        tags_str = p["tags"] or ""
        pub = p["published"] or ""
        # 著者は最初の1人 + et al.
        authors = p["authors"] or ""
        author_list = authors.split(", ")
        author_disp = author_list[0] + (" et al." if len(author_list) > 1 else "")

        table.add_row(
            p["id"],
            p["title"],
            author_disp,
            pub,
            status,
            tags_str,
        )

    console.print(table)
    console.print(f"[dim]{len(papers)}件[/]")


# --- arx show ---

@app.command()
def show(
    identifier: str = typer.Argument(..., help="arXiv IDまたはURL"),
) -> None:
    """論文の詳細を表示する。"""
    arxiv_id = _resolve_id(identifier)

    from arx.db import get_paper
    with _get_conn() as conn:
        paper = get_paper(conn, arxiv_id)

    if not paper:
        err_console.print(f"[bold red]エラー:[/] 登録されていません: {arxiv_id}")
        raise typer.Exit(1)

    status = "[green]既読[/]" if paper["read_at"] else "[yellow]未読[/]"

    console.print(f"\n[bold]{paper['title']}[/]\n")
    console.print(f"  [cyan]ID:[/]       {paper['id']}")
    console.print(f"  [cyan]著者:[/]     {paper['authors']}")
    console.print(f"  [cyan]公開日:[/]   {paper['published'] or '不明'}")
    console.print(f"  [cyan]URL:[/]      {paper['url']}")
    console.print(f"  [cyan]状態:[/]     {status}")
    if paper["read_at"]:
        console.print(f"  [cyan]既読日:[/]   {paper['read_at']}")
    console.print(f"  [cyan]登録日:[/]   {paper['added_at']}")
    if paper["tags"]:
        console.print(f"  [cyan]タグ:[/]     {paper['tags']}")

    console.print(f"\n[bold]アブスト:[/]")
    console.print(f"  {paper['abstract']}\n")

    if paper["memo"]:
        console.print(f"[bold]メモ:[/]")
        console.print(f"  {paper['memo']}\n")


# --- arx memo ---

@app.command()
def memo(
    identifier: str = typer.Argument(..., help="arXiv IDまたはURL"),
    text: Optional[str] = typer.Argument(None, help="追加するメモテキスト"),
    delete: bool = typer.Option(False, "--delete", "-d", help="メモを削除する"),
    yes: bool = typer.Option(False, "--yes", "-y", help="確認をスキップ"),
) -> None:
    """メモを管理する。テキストなしで現在のメモを表示。"""
    arxiv_id = _resolve_id(identifier)

    from arx.db import get_paper, update_memo
    with _get_conn() as conn:
        paper = get_paper(conn, arxiv_id)
        if not paper:
            err_console.print(f"[bold red]エラー:[/] 登録されていません: {arxiv_id}")
            raise typer.Exit(1)

        if delete:
            if not yes:
                typer.confirm("メモを削除しますか？", abort=True)
            update_memo(conn, arxiv_id, "")
            console.print("[green]メモを削除しました。[/]")
            return

        if text is None:
            # 現在のメモを表示
            current = paper["memo"]
            if current:
                console.print(f"[bold]メモ ({arxiv_id}):[/]")
                console.print(f"  {current}")
            else:
                console.print("[dim]メモはありません。[/]")
            return

        # メモを追加（既存メモに改行して追記）
        current = paper["memo"] or ""
        new_memo = (current + "\n" + text).strip() if current else text
        update_memo(conn, arxiv_id, new_memo)
        console.print("[green]メモを更新しました。[/]")


# --- arx read ---

@app.command()
def read(
    identifier: str = typer.Argument(..., help="arXiv IDまたはURL"),
) -> None:
    """論文を既読にする。"""
    arxiv_id = _resolve_id(identifier)

    from arx.db import get_paper, mark_read
    with _get_conn() as conn:
        paper = get_paper(conn, arxiv_id)
        if not paper:
            err_console.print(f"[bold red]エラー:[/] 登録されていません: {arxiv_id}")
            raise typer.Exit(1)

        if paper["read_at"]:
            console.print(f"[yellow]既に既読です:[/] {arxiv_id}")
            return

        mark_read(conn, arxiv_id)

    console.print(f"[green]既読にしました:[/] {arxiv_id}")


# --- arx tag ---

@app.command()
def tag(
    identifier: Optional[str] = typer.Argument(None, help="arXiv IDまたはURL"),
    tags: Optional[list[str]] = typer.Argument(None, help="追加するタグ"),
    remove: Optional[str] = typer.Option(None, "--remove", "-r", help="削除するタグ"),
    list_all: bool = typer.Option(False, "--list", "-l", help="全タグ一覧を表示"),
    yes: bool = typer.Option(False, "--yes", "-y", help="確認をスキップ"),
) -> None:
    """タグを管理する。"""
    from arx.db import add_tag, remove_tag, list_tags, get_paper

    with _get_conn() as conn:
        if list_all:
            rows = list_tags(conn)
            if not rows:
                console.print("[dim]タグがありません。[/]")
                return
            table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
            table.add_column("タグ")
            table.add_column("論文数", justify="right")
            for r in rows:
                table.add_row(r["tag"], str(r["count"]))
            console.print(table)
            return

        if identifier is None:
            err_console.print("[bold red]エラー:[/] IDを指定してください。")
            raise typer.Exit(1)

        arxiv_id = _resolve_id(identifier)
        paper = get_paper(conn, arxiv_id)
        if not paper:
            err_console.print(f"[bold red]エラー:[/] 登録されていません: {arxiv_id}")
            raise typer.Exit(1)

        if remove:
            if not yes:
                typer.confirm(f"タグ '{remove}' を削除しますか？", abort=True)
            deleted = remove_tag(conn, arxiv_id, remove)
            if deleted:
                console.print(f"[green]タグを削除しました:[/] {remove}")
            else:
                console.print(f"[yellow]タグが見つかりません:[/] {remove}")
            return

        if tags:
            for t in tags:
                add_tag(conn, arxiv_id, t)
            console.print(f"[green]タグを追加しました:[/] {', '.join(tags)}")
        else:
            # 現在のタグを表示
            current = paper["tags"]
            if current:
                console.print(f"[cyan]タグ ({arxiv_id}):[/] {current}")
            else:
                console.print("[dim]タグはありません。[/]")


# --- arx search ---

@app.command()
def search(
    query: str = typer.Argument(..., help="検索クエリ"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="タグでフィルタ"),
) -> None:
    """全文検索する（タイトル・著者・アブスト・メモ）。"""
    from arx.db import search_papers

    with _get_conn() as conn:
        results = search_papers(conn, query)

    if tag:
        results = [r for r in results if r["tags"] and tag in r["tags"].split(", ")]

    if not results:
        console.print("[dim]該当する論文がありません。[/]")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("タイトル", max_width=55)
    table.add_column("日付", no_wrap=True)
    table.add_column("タグ", max_width=20)

    for p in results:
        table.add_row(
            p["id"],
            p["title"],
            p["published"] or "",
            p["tags"] or "",
        )

    console.print(table)
    console.print(f"[dim]{len(results)}件[/]")


# --- arx open ---

@app.command(name="open")
def open_paper(
    identifier: str = typer.Argument(..., help="arXiv IDまたはURL"),
) -> None:
    """論文をブラウザで開く。"""
    arxiv_id = _resolve_id(identifier)

    from arx.db import get_paper
    with _get_conn() as conn:
        paper = get_paper(conn, arxiv_id)

    if paper:
        url = paper["url"]
    else:
        url = f"https://arxiv.org/abs/{arxiv_id}"

    if not is_safe_url(url):
        err_console.print(f"[bold red]エラー:[/] 安全でないURLです: {url}")
        raise typer.Exit(1)

    console.print(f"[cyan]ブラウザで開きます:[/] {url}")
    webbrowser.open(url)


# --- arx rss ---

@rss_app.command(name="add")
def rss_add(
    name: str = typer.Argument(..., help="フィード名（例: cs.AI）"),
    url: str = typer.Argument(..., help="RSS URL"),
) -> None:
    """RSSフィードを登録する。"""
    if not is_safe_url(url):
        err_console.print(f"[bold red]エラー:[/] httpsのURLのみ登録できます: {url}")
        raise typer.Exit(1)

    from arx.db import add_feed
    with _get_conn() as conn:
        added = add_feed(conn, name, url)

    if added:
        console.print(f"[green]フィードを登録しました:[/] {name} → {url}")
    else:
        console.print(f"[yellow]既に登録済みです:[/] {name}")


@rss_app.command(name="list")
def rss_list() -> None:
    """登録済みRSSフィード一覧を表示する。"""
    from arx.db import list_feeds

    with _get_conn() as conn:
        feeds = list_feeds(conn)

    if not feeds:
        console.print("[dim]登録済みフィードはありません。[/]")
        return

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("名前")
    table.add_column("URL")
    table.add_column("最終取得")

    for f in feeds:
        table.add_row(f["name"], f["url"], f["last_fetched"] or "未取得")

    console.print(table)


@rss_app.command(name="fetch")
def rss_fetch() -> None:
    """全RSSフィードを取得して新着論文を追加する。"""
    import time

    from arx.db import list_feeds, add_paper, update_feed_fetched
    from arx.api import fetch_rss

    with _get_conn() as conn:
        feeds = list_feeds(conn)

        if not feeds:
            console.print("[dim]登録済みフィードはありません。arx rss add で登録してください。[/]")
            return

        total_added = 0
        total_skipped = 0

        for i, feed in enumerate(feeds):
            if i > 0:
                time.sleep(3)  # arXivレートリミット遵守

            console.print(f"[cyan]取得中:[/] {feed['name']} ...")

            try:
                papers = fetch_rss(feed["url"])
            except (RuntimeError, ValueError) as e:
                err_console.print(f"[bold red]エラー ({feed['name']}):[/] {e}")
                continue

            added_count = 0
            for meta in papers:
                added = add_paper(
                    conn,
                    meta.arxiv_id,
                    meta.title,
                    meta.authors,
                    meta.abstract,
                    meta.url,
                    meta.published,
                )
                if added:
                    added_count += 1
                else:
                    total_skipped += 1

            update_feed_fetched(conn, feed["id"])

            total_added += added_count
            console.print(f"  {added_count}件追加 ({len(papers) - added_count}件スキップ)")

        console.print(f"\n[green]完了:[/] 合計 {total_added}件追加、{total_skipped}件スキップ")


# --- バージョン ---

def version_callback(value: bool) -> None:
    if value:
        console.print(f"arx {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None, "--version", "-V", callback=version_callback, is_eager=True, help="バージョンを表示"
    ),
) -> None:
    """arXiv論文管理CLIツール"""


if __name__ == "__main__":
    app()
