# Virtual-Engine — 1.3.9-audit.3

当前交付修订为r3，请使用r3归档与source_manifest_r3.json；旧r2归档保留供比对，不用于本次发布。

演示评审版可靠性修复候选，基线提交 `f243720049cc77e4d9cd05030853b47aa0bebfa6`。只修改独立副本；未提交、未部署、未迁移生产数据。

- [本轮修复和兼容性说明](audit/PATCH_1.3.9-audit.3.zh-CN.md)
- [演示启动、核验与回退](audit/DEMO_1.3.9-audit.3.zh-CN.md)
- 本轮验收最终以 `audit/audit3_acceptance_status.json` 为准；下面均为历史交接材料。

# Virtual-Engine — 1.3.9-audit.2

五项已确认流程缺陷的独立补丁候选，尚未提交或部署。当前说明和结果以 [补丁说明](audit/PATCH_1.3.9-audit.2.zh-CN.md) 与 audit/patch_acceptance_status.json 为准。源码基线为已部署提交 4a3e619b1287ecc16b5a9a9f80e82fea9502d39d；下方保留 audit.1 历史交接状态，不代表 audit.2 最新测试结果。

# Virtual-Engine — 1.3.9-audit.1

**交付状态：完整修复候选仓库；HOLD，未完成真实浏览器及真实 Streamlit 运行时验收。禁止据此直接覆盖线上。**

唯一基线为用户上传的 `virtual-engine-review-deploy.zip`，SHA256：
`a58d23bab84d570adabaccf61ff9f3d8a08c71ce0833e25e86926a6bba894400`。
目标是 `gundamexia028/virtual-engine` 的 `review-deploy` 分支，入口 `app/streamlit_app.py`。
本轮只修改离线副本；没有修改线上，也没有操作其他仓库。

## 先读这几份文件

- [审计与验证报告](audit/AUDIT_REPORT.zh-CN.md)：原版证据、修复内容、保留风险。
- [覆盖边界](audit/TEST_BOUNDARIES.zh-CN.md)：真实执行数量与未覆盖范围。
- [复现和复跑命令](audit/REPRODUCE.zh-CN.md)：不是只有补丁，测试代码均在本仓库。
- [部署及回退说明](audit/DEPLOY_ROLLBACK.zh-CN.md)：先通过验收，不能直接推送。
- [下一执行方完整任务](audit/WORK_ACCEPTANCE_ORDER.zh-CN.md)：只补运行时/浏览器门禁，不从零重构。
- [机器可读验收状态](audit/acceptance_status.json)。

`app/README.md` 和 `docs/`、`app/docs/` 中部分内容是保留的历史基线材料；
涉及当前状态和新版语义，以本目录的审计报告及实际代码为准，不能将历史“冻结/通过”当成本候选验收结论。

## 本轮已执行结果

43项新增引擎/控制层单元测试通过；既有16个测试脚本中14个使用显式原有 Streamlit 测试替身通过，
2个真实运行时测试被阻断。有限矩阵11,768条历史/数值探针及68条定向分支见证通过。
真实应用浏览器交互执行数为0；没有生成或冒充成功截图。详细日志在配套证据包。

## 最小本地引擎回归

```bash
python -m unittest discover -s tests_audit -v
```

完整运行时与浏览器验收命令见 `audit/REPRODUCE.zh-CN.md`。本候选不是医学指南，也不是经过临床验证的生理模型。
