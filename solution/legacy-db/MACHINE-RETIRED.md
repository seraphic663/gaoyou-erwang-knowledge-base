# 旧机器解析主链已退休

正式机器字词／案例库使用 `solution/website/scripts/relation_parser.py` 与 `machine_library.py`，入口为网站 `/library`；构建／打包任务为 `machine:build`、`machine:pack`。

本目录的 `main/parser.py`、`main/importer.py`、`source.txt` 和 `dictionary.db` 保留作为旧数据的审计材料，不能据此更新当前机器库。正式机器构建不读取旧 dictionary.db；机器库缺失不回退旧库。旧候选实时重算接口和旧字词混库页面已移除。

`annotation/` 与共享 `lib/` 属于独立的人工标注流程，不随机器链退休而移除或迁移。
