# 归档说明

本目录保存已经退出主链路的历史文件，保留目的仅是追溯和参考，不再作为当前系统正式入口。

## 子目录

- `flask-ui/`：早期 Flask 检索界面、模板、Cloudflare Tunnel 启动脚本与依赖文件
- `legacy-data/`：旧版数据库文件
- `examples/`：早期单条录入脚本和解析测试文件
- `samples/`：临时样本文本

## 原则

- 主网站入口在 [../../03-项目网站](../../03-%E9%A1%B9%E7%9B%AE%E7%BD%91%E7%AB%99)
- 主数据引擎入口在 [../README.md](../README.md)
- 本目录文件默认不再继续扩展，只做保留

## 大文件说明

`flask-ui/` 中原先的 `cloudflared.exe` 已不再保留在 Git 仓库中。
如果后续确实要重跑这套旧界面，请按旧 README 中的方法自行下载 Cloudflare Tunnel 可执行文件。
