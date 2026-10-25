# 安全策略

## 支持范围

当前维护 `main` 分支与 `0.1.x` 版本线。更早的提交不保证获得安全修复。

## 报告漏洞

通过 GitHub Security 页面私下提交：

<https://github.com/diky87688973/ai-agent/security>

选择 `Report a vulnerability`，提供：

- 受影响版本或提交号
- 复现步骤与最小复现
- 影响范围
- 已采取的缓解措施

安全报告不进入公开 Issue。维护者确认后评估影响并安排修复与披露。

## 范围

重点包括：

- API 密钥、配置文件或会话数据泄露
- 命令执行、路径穿越、任意文件读写
- 插件加载与工具门控绕过
- Web API 鉴权、SSE 与文件预览越权
- 依赖供应链问题

`config.ini`、`plugins/*/plugin-config.ini`、`.env`、`data/` 属于本地运行数据，不应提交到仓库。

## 披露

修复发布后，可在公开 Issue 或 Release Notes 中说明影响与升级方式。未修复漏洞的细节不提前公开。
