# C01–C05 专项回归

本目录新增测试只验证软件契约，不变更医学指南、剂量、评分规则或正式数据。

## 范围与边界

- `test_workflow_five_regressions.py`：15个引擎/真实命令控制器测试方法，含四病例×训练/考试子矩阵
- `test_workflow_real_runtime.py`：3个真实 Streamlit AppTest 方法，不使用 Streamlit 替身，也不声称是浏览器测试
- `real_browser_acceptance.py`：真实 Chromium/Playwright 运行器，扩展 C01–C05；本轮 socket 权限阻断、执行0条浏览器病例，需在允许本地服务的环境继续运行
- `browser_fixture_app.py`：本地测试专用、环境变量防护、合成身份；观察真实产品状态。不是完整登记、问卷或管理端端到端测试

### 固定的验收语义

1. C01：临床病例遗漏ABC或体位管理不能返回成功；四病例完整路径仍为100分
2. C02：临床 `stop_infusion → continue_infusion` 必须恢复正在输入、清除已停止标志，无有效药物时病程不能冻结；多轮停止/恢复不重复加分。学院同名动作是“继续观察”干扰项，保留原语义及停止输入后隐藏行为
3. C03：学院训练成功保持终态，只能查看，“继续操作”改为“返回查看”；取消结束确认不能重新开放变更。临床训练保留原有自动结果页。重新开始生成新会话、恢复可操作，旧事件不能污染新会话
4. C04：学院有效复评后仍可再次复评，新有效日志和模拟时间增加，分数及评分奖项不增加，首次有效时间保持不变。过期事件重放不重复推进。临床复评行为保持原样
5. C05：学院既往顺序违规在补救完成后仍显示于安全问题摘要，保留原始原因和时间；本次不扩展临床安全摘要，临床原有日志及评分契约单独保护

学院两情景JSON字节SHA256还与修复前基线核对，防止共享引擎修复暗改病例。

## 复跑

在源码根目录，使用已安装真实 Streamlit 的 Python：

```bash
python tests_audit/test_workflow_five_regressions.py
python tests_audit/test_workflow_real_runtime.py
python -m unittest discover -s tests_audit -v
```

缺少真实 Streamlit 时，运行时测试明确 `SKIP`，不得计为运行时通过。引擎/控制器测试不依赖 Streamlit。

与保留基线对照，在新进程中运行；不要在同一解释器混合两棵源码：

```bash
VE_WORKFLOW_ROOT=/absolute/path/to/baseline python tests_audit/test_workflow_five_regressions.py
VE_WORKFLOW_ROOT=/absolute/path/to/baseline python tests_audit/test_workflow_real_runtime.py
```

真实浏览器：

```bash
python tests_audit/real_browser_acceptance.py --chromium /usr/bin/chromium --out /absolute/new/evidence/browser
python tests_audit/real_browser_acceptance.py --repo /absolute/path/to/baseline --chromium /usr/bin/chromium --out /absolute/new/evidence/baseline-browser
```

浏览器运行器会先克隆所选源码，使用合成身份及独立临时存储。运行器禁止访问外部网页。只有实际完成的结果、截图及trace可算浏览器证据。

## 本轮实测结果

同一最终测试代码：

- 修复前基线：15个引擎/控制器方法中出现33个失败子用例；C01、C02、C03、C04、C05均有独立失败。既有保护项通过，不将这些通过项称为原版缺陷
- 修复后候选：15个引擎/控制器方法全部通过
- 修复前基线真实AppTest：3个方法中出现6个失败子用例，C03学院训练2例、C04学院病例/模式4例
- 修复后候选真实AppTest：3个方法全部通过
- 真实浏览器：启动阶段 socket 权限阻断，0例，不计为通过

运行日志保存在独立证据目录，源码包不包含测试身份、运行数据或缓存。
