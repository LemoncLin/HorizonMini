# HorizonMini

每日自动抓取 [Horizon](https://github.com/Thysrael/Horizon) 每日科技摘要（中文版），以 HTML 邮件形式推送。

## 功能

- **定时推送** — GitHub Actions 每天 23:00 UTC（北京时间 07:00）自动触发
- **内容清洗** — 提取 Horizon 摘要页主体，保留目录、转换折叠块、修复相对路径
- **邮件兼容** — 内嵌 CSS，居中 680px 布局，适配主流邮件客户端
- **本地预览** — `--dry-run` 模式生成 HTML 文件，浏览器直接查看

## 项目结构

```
HorizonMini/
├── .github/workflows/daily-email.yml   # GitHub Actions 定时任务
├── config/settings.json                # 非敏感配置（SMTP 地址、端口等）
├── scripts/
│   ├── send_email.py                   # 主脚本：抓取 → 清洗 → 构建 → 发送
│   └── templates/
│       ├── __init__.py                 # 模板加载器
│       ├── email.html                  # 邮件 HTML 结构模板
│       └── email.css                   # 邮件 CSS 样式
├── .gitignore
├── requirements.txt
└── README.md
```

## 快速开始

### 本地测试

```bash
# 安装依赖
pip install -r requirements.txt

# 仅生成 HTML 预览（不发送邮件）
python scripts/send_email.py --dry-run --date 2026-07-02

# 浏览器打开 output-2026-07-02.html 查看效果
```

### 部署到 GitHub

1. Fork 或克隆本仓库到你的 GitHub 账号
2. 进入仓库 **Settings → Secrets and variables → Actions**，添加以下 3 个 Secret：

| Secret 名称 | 说明 | 示例 |
|-------------|------|------|
| `SMTP_USER` | 发件邮箱地址 | `yourname@163.com` |
| `SMTP_PASS` | SMTP 授权码（非登录密码） | `xxxxxxxx` |
| `TO_EMAIL` | 收件邮箱地址 | `recipient@example.com` |

> **163 邮箱获取授权码：** 设置 → POP3/SMTP/IMAP → 开启 SMTP 服务 → 生成授权码

3. 推送代码后，Actions 会自动在每天 07:00（北京时间）执行推送

### 自定义配置

非敏感配置（SMTP 服务器地址、端口、发件人名称等）在 `config/settings.json` 中修改即可：

```json
{
  "smtp": {
    "host": "smtp.163.com",
    "port": 465
  },
  "sender": {
    "name": "HorizonMini"
  }
}
```

如需覆盖，可在 GitHub Actions Secrets 中设置同名环境变量（优先级：环境变量 > settings.json）。

## 内容处理流程

1. **抓取** — 请求 `https://thysrael.github.io/Horizon/{YYYY}/{MM}/{DD}/summary-zh.html`
2. **提取** — 只取 `<main id="content">` 内部内容
3. **清洗**：
   - 移除首个 `<blockquote>` 统计区块（移至 header 展示）
   - 移除空锚点 `<a id="item-N"></a>`
   - 移除 GitHub Pages 底部 `<footer class="site-footer">`
   - `<details><summary>` → `<div class="ref-links">`（邮件兼容）
   - 相对路径 → 绝对路径
4. **构建** — 注入 CSS + 清洗后的内容到邮件模板
5. **发送** — `smtplib.SMTP_SSL` + `MIMEText(html)`

## 技术栈

- **Python** 3.11+，仅依赖 `requests` + `python-dotenv`
- **GitHub Actions** 定时调度
- **SMTP_SSL** 加密发送邮件
- **正则表达式** 内容清洗，无 HTML 解析依赖
