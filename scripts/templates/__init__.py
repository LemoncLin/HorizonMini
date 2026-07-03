"""邮件模板加载器 — 从外部文件读取 HTML 和 CSS"""

import os
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

    策略：
    1. 用 %s 占位符先注入 CSS（避开 Python .format() 对 {} 的解析冲突）
    2. 将剩余模板占位符 {{ }} 转义为 {{{{ }}}}，再格式化
    """
    # 第一步：把 {{ css }} 替换为 CSS 原文（用 %s 定位，避免 .format() 解析花括号）
    placeholder = "{{ css }}"
    if placeholder in html_template:
        html = html_template.replace(placeholder, "%s")
        html = html % css
    else:
        html = html_template

    # 第二步：将模板中的单 { } 转义为 {{ }}，再执行 .format()
    # 先临时替换 {{ }} 为唯一标记
    ESC_A = "\x00ESCOPEN\x00"
    ESC_B = "\x00ESCCLOSE\x00"
    html = html.replace("{{", ESC_A).replace("}}", ESC_B)
    # 剩下的单 { } 是模板变量占位符，转义为 {{ }}
    html = html.replace("{", "{{").replace("}", "}}")
    # 还原之前的转义标记
    html = html.replace(ESC_A, "{{").replace(ESC_B, "}}")

    return html.format(**kwargs)
