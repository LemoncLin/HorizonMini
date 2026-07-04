"""邮件模板加载器 — 从外部文件读取 HTML 和 CSS"""

import re
from pathlib import Path


def _template_dir() -> Path:
    """返回 templates 目录的绝对路径"""
    return Path(__file__).resolve().parent


def load_css() -> str:
    """读取 email.css 文件内容"""
    css_path = _template_dir() / "email.css"
    return css_path.read_text(encoding="utf-8")


def load_html_template() -> str:
    """读取 email.html 文件内容"""
    html_path = _template_dir() / "email.html"
    return html_path.read_text(encoding="utf-8")


def render_email(css: str, html_template: str, **kwargs: object) -> str:
    """将 CSS 注入 HTML 模板，再用 kwargs 填充占位符

    模板使用 Jinja2 风格的 {{ var }} 占位符。
    由于 CSS 中包含大量 { } 花括号，不能直接交给 .format() 解析。
    策略：
      1. 将 {{ css }} 替换为唯一标记（避开 CSS 花括号干扰）
      2. 将 {{ var }} 转为 {var}（去除空格）供 .format() 使用
      3. 填充变量
      4. 将唯一标记还原为 CSS 原文
    """
    # 用唯一标记暂存 CSS 位置
    CSS_MARKER = "\x00__CSS_CONTENT__\x00"
    html = html_template.replace("{{ css }}", CSS_MARKER)

    # 将 {{ var }} 转为 {var}（去空格）
    html = re.sub(r"\{\{\s*(\w+)\s*\}\}", r"{\1}", html)

    # 填充模板变量
    html = html.format(**kwargs)

    # 将 CSS 标记替换为实际 CSS 内容
    html = html.replace(CSS_MARKER, css)

    return html
