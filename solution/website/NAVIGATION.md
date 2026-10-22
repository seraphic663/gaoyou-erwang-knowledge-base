# 网站导航切换

用户入口为首页、释证与审校、案例库、字词库、原典检索、训诂知识；质量报告为辅助入口。只保留一套页面。旧 HTML URL 由服务端转换为新 URL，并保留记录 ID、来源、筛选和分页参数。

| 页面 | 新 URL |
| --- | --- |
| 首页 | / |
| 案例库 | /cases?source=all 或 main/annotation/v2 |
| 案例详情 | /case?source=main&id=1 |
| 字词库 / 字词详情 | /terms、/term?id=1 |
| 释证与审校 | /audit?case=原始V2案例ID |
| 原典检索 | /corpus?q=正文、/corpus?case_id=V2案例ID |
| 训诂知识 / 质量报告 | /knowledge、/quality |

页面统一不合并数据库，也不重编 ID。main、annotation、v2 是不同身份空间；主库到 V2 的审校链接只使用 legacy_term_case_links，并保留多映射；人工标注材料未核实映射时不生成审校链接。原文定位展示已关联段落及额外检索结果，并区分来源状态。

审校暂存使用 sessionStorage，按当前浏览器标签页及 case_id 隔离；恢复不会自动授权保存，服务端仍校验来源指纹。已提交历史保存在原 V2 数据库。历史 GET 使用 SQLite 只读连接，不隐式补列。写入保留原有追加版本、删除/恢复与幂等语义。

本次不修改模型、推理配置或提示词内容。生成端既有 v8 提示词版本与存储端只接受 v1 的不一致已修复；存储允许 v1 历史格式及生成端现有 v4–v8 格式。

上线前在 Railway 持久卷 /app/v2/data/site-navigation-backups/20261022 保存 annotation_v2.db、两份 JSON 快照及 baseline.json。通过 SQLite backup API 创建一致备份，验证恢复副本的完整性、外键和各表全内容摘要。上线后与线上基线比较；不将本地数据库覆盖到线上。应用回滚可回退代码版本，数据保持原卷；只有确认真实数据损坏时才考虑停写并从备份恢复。

验证命令：node --test solution/website/tests/*.test.js；python -m unittest discover -s v2/tests -p test_five_step_audit_bridge.py；python -m unittest discover -s solution/website/tests -p test_site_identity.py。HTTP 审校集成测试 review-http-integration.js 必须显式指定隔离 fixture-copy 数据库；不调用模型。
