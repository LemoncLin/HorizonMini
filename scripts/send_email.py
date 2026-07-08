"""HorizonMini — 每日抓取 Horizon 汇总页并通过 SMTP 发送邮件

用法:
  # 发送邮件（需配置 GitHub Actions Secrets）
  python scripts/send_email.py

  # 仅保存 HTML 到本地（不发送邮件，用于测试预览）
  python scripts/send_email.py --dry-run

  # 指定日期抓取
  python scripts/send_email.py --date 2026-07-02
"""

import argparse
import json
import os
import re
import time
import smtplib
import sys
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from email.utils import formataddr

import requests

# 动态加载同目录下的 templates 模块
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
from templates import load_css, load_html_template, render_email

BASE_URL = "https://thysrael.github.io/Horizon"

# 预加载模板
_CSS = load_css()
_HTML_TEMPLATE = load_html_template()

# 加载非敏感配置（优先级：环境变量 > settings.json > 硬编码默认值）
_CONFIG_PATH = os.path.join(os.path.dirname(_script_dir), "config", "settings.json")
with open(_CONFIG_PATH, encoding="utf-8") as f:
    _SETTINGS = json.load(f)


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
    parser.add_argument(
        "--auto-date",
        action="store_true",
        help="自动查找最新可用的 Horizon 摘要日期（重试模式，间隔3小时）",
    )
    return parser.parse_args()


def find_latest_available_date() -> str | None:
    """向前扫描最近 7 天，找到第一个可访问的日期

    从昨天开始往前找，最多回退 7 天。
    返回 YYYY-MM-DD 字符串，都不可达则返回 None。
    """
    today = datetime.now(timezone.utc)
    for offset in range(1, 8):
        date = (today - timedelta(days=offset)).strftime("%Y-%m-%d")
        url = build_url(date)
        try:
            resp = requests.head(url, timeout=10)
            if resp.status_code == 200:
                print(f"[INFO] 找到可用日期: {date}")
                return date
        except requests.RequestException:
            pass
    return None


def find_latest_available_date_with_retries(max_hours: int = 24) -> str:
    """带重试机制查找最新可用日期，每隔 3 小时重试一次

    首次立即尝试，之后每隔 3 小时重试，最多等待 max_hours 小时。
    返回找到的日期字符串，超时后抛出异常。
    """
    today = datetime.now(timezone.utc)
    deadline = today + timedelta(hours=max_hours)
    retry_count = 0

    while today <= deadline:
        date_str = find_latest_available_date()
        if date_str:
            return date_str
        retry_count += 1
        wait_minutes = 3 * 60
        print(f"[INFO] 暂无可用日期，{wait_minutes // 60} 小时后重试 ({retry_count}/{max_hours // 3})")
        time.sleep(wait_minutes * 60)
        today = datetime.now(timezone.utc)

    raise TimeoutError(
        f"在 {max_hours} 小时内未找到可用的 Horizon 摘要页面，已放弃"
    )


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
    """移除内容中的第一个 <blockquote>（统计信息已在 header 展示）"""
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
    """将 <details><summary> 转为始终可见的 div，兼容邮件客户端"""

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
    """用 .toc 容器包裹目录 <ol>"""
    content = re.sub(r"(<ol>)", r'<div class="toc">\1', content, count=1)
    content = re.sub(r"(</ol>)", r"\1</div>", content, count=1)
    return content


def extract_stats(content: str) -> str:
    """从 blockquote 中提取统计信息"""
    m = re.search(r"<blockquote>\s*<p>(.*?)</p>\s*</blockquote>", content, re.DOTALL)
    if m:
        return re.sub(r"<[^>]+>", "", m.group(1)).strip()
    return ""


def get_config(key_path: str, env_name: str | None = None, default: str = "") -> str:
    """统一配置获取：环境变量 > settings.json > 默认值

    Args:
        key_path: settings.json 中的键路径，如 "smtp.host"
        env_name: 对应的环境变量名，None 则不查环境变量
        default: 最终兜底默认值
    """
    # 1. 环境变量（最高优先级）
    if env_name and env_name in os.environ:
        return os.environ[env_name]
    # 2. settings.json
    keys = key_path.split(".")
    val = _SETTINGS
    for k in keys:
        if isinstance(val, dict) and k in val:
            val = val[k]
        else:
            val = None
            break
    if val is not None:
        return str(val)
    # 3. 硬编码默认值
    return default


def build_email_body(date_str: str, content: str, stats_text: str) -> str:
    archive_url = f"{BASE_URL}/{date_str.replace('-', '/')}/summary-zh.html"
    return render_email(
        css=_CSS,
        html_template=_HTML_TEMPLATE,
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
    # 非敏感配置从 settings.json 读取
    smtp_host = get_config("smtp.host", "SMTP_HOST")
    smtp_port = int(get_config("smtp.port", "SMTP_PORT", "465"))
    from_name = get_config("sender.name", "FROM_NAME", "HorizonMini")

    # 敏感配置只从环境变量/Secrets 读取
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    to_email = os.environ["TO_EMAIL"]
    from_email = os.environ.get("FROM_EMAIL", smtp_user)

    msg = MIMEText(html_body, "html", "utf-8")
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email
    msg["Subject"] = f"Horizon 每日摘要 — {date_str}"
    # 标记为自动生成的批量邮件，降低被风控误判的概率
    msg["Auto-Submitted"] = "auto-generated"
    msg["Precedence"] = "bulk"
    # 固定 Message-ID 前缀，便于服务端识别同一客户端
    msg["Message-ID"] = f"<horizonmini-{date_str}@{smtp_host}>"

    def _do_send(host: str, port: int) -> None:
        """内部发送函数，固定 EHLO 主机名以减少 IP 变动特征"""
        with smtplib.SMTP_SSL(
            host, port,
            timeout=30,
            # 固定 EHLO/HELO 主机名，避免每次运行暴露不同的系统主机名
            local_hostname="horizon-mini",
        ) as server:
            server.login(smtp_user, smtp_pass)
            server.sendmail(from_email, [to_email], msg.as_string())

    try:
        _do_send(smtp_host, smtp_port)
        print(f"[OK] 邮件已发送至 {to_email}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        # 认证失败（可能触发了异地登录检测）→ 等待 60s 重试一次
        print(f"[WARN] SMTP 认证失败，60 秒后重试: {e}", file=sys.stderr)
        time.sleep(60)
        try:
            _do_send(smtp_host, smtp_port)
            print(f"[OK] 重试成功，邮件已发送至 {to_email}")
            return True
        except smtplib.SMTPException as e2:
            print(f"[ERROR] 重试仍然失败: {e2}", file=sys.stderr)
            return False
    except smtplib.SMTPException as e:
        print(f"[ERROR] 发送邮件失败: {e}", file=sys.stderr)
        return False


def main():
    args = parse_args()

    # 确定要抓取的日期
    if args.date:
        date_str = args.date
    elif args.auto_date:
        print("[INFO] 正在查找最新可用的 Horizon 摘要页面...")
        date_str = find_latest_available_date_with_retries(max_hours=24)
        print(f"[INFO] 找到可用日期: {date_str}")
    else:
        date_str = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

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
            f"[ERROR] 缺少环境变量 {e}，请在 GitHub Actions Secrets 中配置",
            file=sys.stderr,
        )
        print(
            "      本地测试请使用 --dry-run 参数仅生成 HTML 文件",
            file=sys.stderr,
        )
        sys.exit(1)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
