# bb作业通知

## 简介

一个黑板通知程序，用于通知用户黑板上的新消息。

## 使用

```bash
docker-compose up -d
```

或

```bash
docker run -d --env-file .env -v ./logs:/app/logs -v ./persist:/app/persist ghcr.io/betterandbetterii/bb-notify:latest
```
