# HorizonMini

每日自动抓取 [Horizon](https://github.com/Thysrael/Horizon) 每日科技摘要，并通过邮件推送，保留完整 HTML 格式。

## 功能

- 定时任务：GitHub Actions 每天 7:00 (北京时间) 自动触发
- 内容抓取：获取前一天的中文版摘要 `summary-zh.html`
- 格式保留：邮件 HTML 格式与原网页风格一致
- 本地测试：支持 `--dry-run` 模式保存 HTML 到本地预览

## 项目结构

```
HorizonMini/
├── .github/workflows/
│   └── daily-email.yml       # GitHub Actions 工作流
├── scripts/
│   └── send_email.py         # 主脚本
├── .env.example              # 本地配置模板
├── .gitignore
├── requirements.txt
└── README.md
```

## 配置

### 1. 本地测试

```bash
# 安装依赖
pip install -r requirements.txt

# 创建本地配置
cp .env.example .env
# 编辑 .env 填写 SMTP 凭据
```

**.env 文件内容：**
```
SMTP_HOST=smtp.163.com
SMTP_PORT=465
SMTP_USER=yourname@163.com
SMTP_PASS=your-smtp-authorization-code
TO_EMAIL=recipient@example.com
```

**163 邮箱获取授权码：** 设置 → POP3/SMTP/IMAP → 开启 SMTP → 新增授权码

### 2. GitHub Actions (线上部署)

推送代码到 GitHub 后，需要在仓库中添加 Secrets：

**操作路径：** Repository → Settings → Secrets and variables → Actions → New repository secret

| Secret 名称 | 说明 | 示例值 |
|-------------|------|--------|
| `SMTP_HOST` | SMTP 服务器地址 | `smtp.163.com` |
| `SMTP_PORT` | SMTP 端口 | `465` |
| `SMTP_USER` | 发件邮箱 | `yourname@163.com` |
| `SMTP_PASS` | SMTP 授权码（非登录密码） | `xxxxxxxx` |
| `FROM_EMAIL` | 发件人地址（可选，默认同 SMTP_USER） | `yourname@163.com` |
| `FROM_NAME` | 发件人名称（可选） | `HorizonMini` |
| `TO_EMAIL` | 收件邮箱 | `recipient@example.com` |

## 使用

### 本地测试

```bash
# 仅保存 HTML 到本地（不发送邮件）
python scripts/send_email.py --dry-run

# 指定日期测试
python scripts/send_email.py --dry-run --date 2026-07-02

# 真正发送邮件
python scripts/send_email.py
```

浏览器打开 `output-YYYY-MM-DD.html` 可预览邮件效果。

### 自动推送

代码推送到 GitHub 后，Actions 会自动在每天 23:00 UTC（北京时间 07:00）执行邮件推送。

**手动触发：** Actions → 每日邮件推送 → Run workflow

## 技术说明

- 从 Horizon 页面提取 `<main>` 区域内容
- 目录 `<ol>` 保留，便于快速浏览
- `<details>` 折叠块转为始终可见内容（邮件客户端兼容）
- 相对路径转绝对路径，确保链接可点击
- 使用 `smtplib` + `requests` 标准实现，依赖极少
