"""HorizonMini — 每日抓取 Horizon 汇总页并通过 SMTP 发送邮件

用法:
  # 发送邮件（需配置环境变量或 .env 文件）
  python scripts/send_email.py

  # 仅保存 HTML 到本地（不发送邮件，用于测试预览）
  python scripts/send_email.py --dry-run

  # 指定日期抓取（不传该参数默认使用前一日）
  python scripts/send_email.py --date 2026-07-02
"""

import argparse
import os
import re
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.utils import formataddr

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_URL = "https://thysrael.github.io/Horizon"

# 邮件 HTML 模板（参考 Horizon 项目的邮件风格）
EMAIL_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
      "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
    line-height: 1.8;
    color: #333;
    max-width: 680px;
    margin: 0 auto;
    padding: 20px;
    background: #fff;
  }}
  .header {{
    text-align: center;
    padding: 24px 0 20px;
    margin-bottom: 20px;
    border-bottom: 2px solid #2c3e50;
  }}
  .header h1 {{
    margin: 0;
    font-size: 24px;
    font-weight: 700;
    color: #1a1a2e;
  }}
  .header .sub {{
    color: #888;
    font-size: 14px;
    margin-top: 6px;
  }}
  .header .stats {{
    color: #e67e22;
    font-size: 14px;
    font-weight: 600;
    margin-top: 4px;
  }}

  /* 目录列表 */
  .toc ol {{
    padding-left: 24px;
    font-size: 14px;
    line-height: 2.2;
    margin: 16px 0 24px;
  }}
  .toc ol a {{
    color: #2c3e50;
    font-weight: 500;
    text-decoration: none;
  }}

  /* 新闻标题 */
  h2 {{
    font-size: 19px;
    font-weight: 700;
    color: #1a1a2e;
    margin: 0 0 8px;
    line-height: 1.5;
  }}
  h2 a {{
    color: #1a1a2e;
    text-decoration: none;
  }}
  .score {{
    color: #e67e22;
    font-weight: 700;
    font-size: 14px;
    white-space: nowrap;
  }}
  .meta {{
    font-size: 12px;
    color: #999;
    margin: 2px 0 10px;
  }}
  .meta a {{
    color: #3498db;
    text-decoration: none;
  }}

  /* 正文 */
  p {{
    margin: 6px 0;
    font-size: 15px;
    color: #444;
    line-height: 1.8;
  }}
  strong {{
    color: #1a1a2e;
    font-size: 15px;
  }}
  .label {{
    font-weight: 700;
    color: #2c3e50;
    font-size: 15px;
  }}
  blockquote {{
    border-left: 4px solid #d0d7de;
    padding: 8px 18px;
    margin: 14px 0;
    color: #555;
    font-size: 14px;
    line-height: 1.8;
    background: #f8f9fa;
  }}
  code {{
    background: #f0f0f0;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 13px;
    font-family: "SF Mono", "Fira Code", "Consolas", monospace;
  }}
  pre {{
    background: #f5f5f5;
    padding: 12px 16px;
    border-radius: 4px;
    overflow-x: auto;
    font-size: 13px;
    line-height: 1.6;
  }}
  .ref-links {{
    border-left: 3px solid #d0d7de;
    padding: 6px 0 6px 14px;
    margin: 10px 0;
    font-size: 13px;
    line-height: 1.8;
  }}
  .ref-links p {{
    margin: 2px 0;
    font-size: 13px;
  }}
  .ref-links a {{
    color: #3498db;
    word-break: break-all;
  }}
  .ref-links ul {{
    margin: 4px 0;
    padding-left: 20px;
  }}
  .ref-links li {{
    margin: 2px 0;
  }}
  .tags {{
    margin: 8px 0 4px;
  }}
  .tag {{
    display: inline-block;
    background: #eef2f7;
    color: #4a5568;
    padding: 1px 8px;
    border-radius: 3px;
    font-size: 11px;
    margin: 2px 3px 2px 0;
  }}
  hr {{
    border: none;
    border-top: 1px solid #e6e6e6;
    margin: 28px 0;
  }}
  .footer {{
    margin-top: 36px;
    padding-top: 18px;
    border-top: 1px solid #eee;
    text-align: center;
    font-size: 12px;
    color: #aaa;
  }}
  .footer a {{
    color: #888;
    text-decoration: none;
  }}
</style>
</head>
<body>
  <div class="header">
    <h1>Horizon 每日摘要</h1>
    <div class="sub">{date_str}</div>
    <div class="stats">{stats_text}</div>
  </div>
  {content}
  <div class="footer">
    <p>由 HorizonMini · 每日自动推送</p>
    <p><a href="{archive_url}">查看网页版</a></p>
  </div>
</body>
</html>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="HorizonMini 邮件推送工具")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅保存 HTML 到本地 output.html，不发送邮件",
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="指定日期 YYYY-MM-DD，默认取前一日",
    )
    return parser.parse_args()


def resolve_date(date_str: str | None) -> str:
    if date_str:
        return date_str
    return (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")


def build_url(date_str: str) -> str:
    parts = date_str.split("-")
    return f"{BASE_URL}/{parts[0]}/{parts[1]}/{parts[2]}/summary-zh.html"


def fetch_html(url: str) -> str | None:
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        resp.encoding = "utf-8"
        return resp.text
    except requests.RequestException as e:
        print(f"[ERROR] 抓取失败: {e}", file=sys.stderr)
        return None


def fix_relative_urls(html: str) -> str:
    html = re.sub(
        r'href="(?!https?://|data:|mailto:|#|/)([^"]*)"',
        lambda m: f'href="{BASE_URL}/{m.group(1)}"',
        html,
    )
    html = re.sub(
        r'src="(?!https?://|data:|/)([^"]*)"',
        lambda m: f'src="{BASE_URL}/{m.group(1)}"',
        html,
    )
    html = html.replace('href="/Horizon/', f'href="{BASE_URL}/')
    html = html.replace('src="/Horizon/', f'src="{BASE_URL}/')
    return html


def extract_main_content(html: str) -> str | None:
    """提取 <main id="content"> 内部的 HTML"""
    m = re.search(
        r'<main[^>]*id="content"[^>]*>\s*(.*?)\s*</main>',
        html,
        re.DOTALL,
    )
    if m:
        return m.group(1)
    return None


def clean_anchor_tags(content: str) -> str:
    """移除空锚点标签 <a id="item-N"></a>"""
    return re.sub(r'<p>\s*<a\s+id="[^"]*"></a>\s*</p>', "", content)


def remove_first_blockquote(content: str) -> str:
    """移除内容中的第一个 <blockquote>（统计信息已在 header 展示，避免重复）"""
    return re.sub(r"<blockquote>.*?</blockquote>\s*", "", content, count=1, flags=re.DOTALL)


def remove_site_footer(content: str) -> str:
    """移除页面底部 <footer class="site-footer"> 区块"""
    return re.sub(
        r'<footer\s+class="site-footer">.*?</footer>',
        "",
        content,
        flags=re.DOTALL,
    )


def convert_details(content: str) -> str:
    """将 <details><summary> 块转为始终可见的内容，兼容邮件客户端"""

    def replace_details(m: re.Match) -> str:
        inner = m.group(0)
        summary_match = re.search(r"<summary>(.*?)</summary>", inner, re.DOTALL)
        summary_text = summary_match.group(1) if summary_match else "参考链接"

        body = re.sub(r"</?details>", "", inner)
        body = re.sub(r"<summary>.*?</summary>", "", body, count=1, flags=re.DOTALL)
        body = body.strip()

        return f'<div class="ref-links"><p><strong>{summary_text}</strong></p>{body}</div>'

    return re.sub(r"<details>.*?</details>", replace_details, content, flags=re.DOTALL)


def wrap_toc(content: str) -> str:
    """用 .toc 容器包裹目录 <ol>（第一个 <hr> 后的 <ol>）"""
    content = re.sub(
        r"(<ol>)",
        r'<div class="toc">\1',
        content,
        count=1,
    )
    content = re.sub(
        r"(</ol>)",
        r"\1</div>",
        content,
        count=1,
    )
    return content


def extract_stats(content: str) -> str:
    """从 blockquote 中提取统计信息"""
    m = re.search(r"<blockquote>\s*<p>(.*?)</p>\s*</blockquote>", content, re.DOTALL)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return ""


def build_email_body(date_str: str, content: str, stats_text: str) -> str:
    archive_url = f"{BASE_URL}/{date_str.replace('-', '/')}/summary-zh.html"
    return EMAIL_TEMPLATE.format(
        date_str=date_str,
        stats_text=stats_text,
        content=content,
        archive_url=archive_url,
    )


def save_local(html_body: str, date_str: str):
    path = f"output-{date_str}.html"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_body)
    print(f"[OK] HTML 已保存至 {path}")


def send_email(html_body: str, date_str: str) -> bool:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.163.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "465"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    from_email = os.environ.get("FROM_EMAIL", smtp_user)
    from_name = os.environ.get("FROM_NAME", "HorizonMini")
    to_email = os.environ["TO_EMAIL"]

    msg = MIMEText(html_body, "html", "utf-8")
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email
    msg["Subject"] = f"Horizon 每日摘要 — {date_str}"

    try:
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, [to_email], msg.as_string())
        print(f"[OK] 邮件已发送至 {to_email}")
        return True
    except smtplib.SMTPException as e:
        print(f"[ERROR] 发送邮件失败: {e}", file=sys.stderr)
        return False


def main():
    args = parse_args()
    date_str = resolve_date(args.date)
    url = build_url(date_str)
    print(f"[INFO] 目标 URL: {url}")

    raw_html = fetch_html(url)
    if raw_html is None:
        print("[WARN] 页面可能尚未生成，跳过")
        sys.exit(1)

    content = extract_main_content(raw_html)
    if content is None:
        print("[WARN] 无法提取主内容区域，使用原始 HTML")
        content = raw_html

    stats_text = extract_stats(content)

    content = remove_first_blockquote(content)
    content = remove_site_footer(content)
    content = clean_anchor_tags(content)
    content = wrap_toc(content)
    content = convert_details(content)
    content = fix_relative_urls(content)

    email_html = build_email_body(date_str, content, stats_text)

    if args.dry_run:
        save_local(email_html, date_str)
        sys.exit(0)

    try:
        success = send_email(email_html, date_str)
    except KeyError as e:
        print(
            f"[ERROR] 缺少环境变量 {e}，请配置 .env 文件或设置环境变量",
            file=sys.stderr,
        )
        print("      参考 .env.example 填写 SMTP 凭据", file=sys.stderr)
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
