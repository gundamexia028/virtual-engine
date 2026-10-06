# 可直接交给下一执行方的完整任务

接管本包中的Virtual-Engine 1.3.9-audit.1完整候选源码，不从零重建。唯一原始基线SHA256为a58d23bab84d570adabaccf61ff9f3d8a08c71ce0833e25e86926a6bba894400；原包在配套baseline目录。目标仅gundamexia028/virtual-engine的review-deploy，入口app/streamlit_app.py；仍只操作离线/隔离测试副本，不碰peds-anaphylaxis-simulation，不推送、不部署。

先核验交付SHA及manifest，读取audit/AUDIT_REPORT.zh-CN.md、TEST_BOUNDARIES.zh-CN.md、acceptance_status.json。已验证的第1—6项缺陷修复和11,768条矩阵/68条定向见证是当前基线；不要因旧黄金断言不同而回退成“准备=实际给药”。保留原始黄金文件与本轮变更记录。

当前必须补的门禁是：安装真实Streamlit/Supabase及测试依赖，保存实际版本；不带--unit-double执行全部真实运行时测试；执行real_browser_acceptance.py并保存8病例模式工作流、实际入口、连续操作、刷新、模式切换、截图、Playwright trace、pageerror和服务日志。脚本本身未实际运行成功，选择器/fixture错误须按真实页面修正，但不能降低被测试的产品断言。

继续补全完整注册、问卷、管理、下载、刷新恢复、目标Safari与多会话流程。对8条未观察规则给出自然可达见证，或给出带前提的不可达/冗余论证；不能将任意注入状态称为自然覆盖。更多深度探索须写明有限界限。医学内容和评分调整必须提交负责人审查，不能为了测试全绿自行删掉临床节点或改剂量规则。

每一阶段先保存实际源码ZIP、与接管候选及原始基线的差异、真实测试日志、环境和SHA，再推进。需要修复时只做有复现证据支持的修改并重跑受影响层。保持外部状态和测试输出分离；不要向线上存储写入。

最终交付完整修复后仓库ZIP、原版/候选复现对照、真实运行时和浏览器证据、覆盖边界、部署回退说明及机器可读验收状态。若真实浏览器或某条断言失败，保持HOLD并记录失败，不准称最终验收完成。本轮不能声称之前已经完成过真实浏览器测试。
