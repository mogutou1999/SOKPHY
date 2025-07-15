🧱 骨架结构保护脚本：
    ✅ 检查改动：python check_code_integrity.py
    ⚠️ 刷新基准：python check_code_integrity.py --init



# Telegram Inline 电商机器人

## 项目说明
这是一个使用 Python 和 Flask 构建的 Telegram inline 模式电商机器人，支持用户通过关键词搜索商品。

## 快速开始

```bash
bash run.sh
```

## 依赖项
- python-telegram-bot==20.7
- Flask==3.0.3

## 环境变量
请设置 `TELEGRAM_BOT_TOKEN` 为你的 Telegram Bot Token。

project-root/
│
├── main.py
├── requirements.txt
├── .env.dev
├── config/
│   ├── __init__.py
│   ├── settings.py
│   ├── settings_schema.py
│   ├── loader.py
├── db/
│   ├── __init__.py
│   ├── base.py
│   ├── models.py
├── handlers/
│   ├── __init__.py
│   ├── auth.py
│   ├── menu.py
│   ├── admin.py
│   ├── carts.py
│   ├── profile.py
│   ├── order.py
├── services/
│   ├── __init__.py
│   ├── payment.py
│   ├── start.py
│   ├── order.py
├── logging_config.py