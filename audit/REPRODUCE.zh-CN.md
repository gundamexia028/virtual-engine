# 缺陷复现、回归与真实浏览器复跑

所有命令在解压后的完整候选仓库根目录执行。示例使用Python3.13；不依赖线上仓库，不需要提供真实用户数据或生产密码。输出目录使用独立新路径，不覆盖本轮证据。

## 1. 只验证引擎与控制层，不需要Streamlit

```bash
python -m unittest discover -s tests_audit -v
```

本轮实际43项通过。仅这一命令无法证明页面运行正常。

```bash
python tests_audit/run_regressions.py --unit-double --with-matrix --out audit_results/offline
```

`--unit-double`是显式允许原项目已有Streamlit替身，不是浏览器。真实运行时缺失时两个AppTest脚本仍会BLOCKED，退出码2是预期阻断，不得包装成PASS。
退出码约定：0表示请求的当前层全部通过；1表示测试失败；2表示运行时被阻断。返回0也不代表全部验收完成，尤其当使用了`--only`。
可用`--coverage`生成仅新增43项单元测试的覆盖文件，需先安装 `tests_audit/requirements-test.txt` 中的coverage。

为避免单次工具调用限时，可按下列**独立任务**执行，输出目录必须区分；每个任务有summary/log，不能只保留最后一个：

```bash
python tests_audit/run_regressions.py --unit-double --only audit_unit --out audit_results/unit
python tests_audit/run_regressions.py --unit-double --only academy_questionnaire_idempotency_tests,clinical_result_page_tests,competition_mode_tests,competition_stability_tests,credential_security_tests,flow_strategy_tests,full_workflow_validation,golden_behavior_tests --out audit_results/legacy_A
python tests_audit/run_regressions.py --unit-double --only org_credential_security_tests,organization_authorization_tests,review_live_vitals_hotfix_tests,scenario_contract_tests,scenario_loader_tests,session_recovery_tests,smoke_tests,version_consistency_tests --out audit_results/legacy_B
python tests_audit/bounded_matrix.py --section pairs --out audit_results/matrix
python tests_audit/bounded_matrix.py --section permutations --out audit_results/matrix
python tests_audit/bounded_matrix.py --section numerics --out audit_results/matrix
python tests_audit/bounded_matrix.py --section time_paths --out audit_results/matrix
python tests_audit/directed_branches.py --out audit_results/matrix
```

无任意随机抽样替代穷举；双动作和关键排列的枚举范围写入summary。比较counts、failures和每条轨迹，不只看进程退出。

## 2. 在唯一原包上重新复现

配套证据ZIP内含字节不变的原始基线ZIP。先校验SHA256，再解压到独立目录，不要覆盖候选。

```bash
python - <<'PYCODE'
import hashlib, pathlib, zipfile
p=pathlib.Path('../baseline/virtual-engine-review-deploy.zip')
expected='a58d23bab84d570adabaccf61ff9f3d8a08c71ce0833e25e86926a6bba894400'
assert hashlib.sha256(p.read_bytes()).hexdigest()==expected
with zipfile.ZipFile(p) as z:
    assert z.testzip() is None
    z.extractall('../baseline_unpacked')
PYCODE
```

上例基线路径按全交付包布局；单独下载源码时需先从证据包取得baseline目录。实际源码根为 `../baseline_unpacked/virtual-engine-review-deploy`。

```bash
python tests_audit/reproduce.py --repo ../baseline_unpacked/virtual-engine-review-deploy --out audit_results/baseline
python tests_audit/reproduce_extra.py --repo ../baseline_unpacked/virtual-engine-review-deploy --out audit_results/baseline_extra.json
python tests_audit/reproduce_dose_boundary.py --repo ../baseline_unpacked/virtual-engine-review-deploy --out audit_results/baseline_dose.json
python tests_audit/reproduce.py --repo . --out audit_results/candidate
python tests_audit/reproduce_extra.py --repo . --out audit_results/candidate_extra.json
python tests_audit/reproduce_dose_boundary.py --repo . --out audit_results/candidate_dose.json
```

`reproduce.py`是观察记录器，不是原版正确性断言；原版缺陷路径返回进程成功仅代表记录生成。F07记录当前环境未取得真实应用浏览器复现，不能从它的静态说明推导实际已修复。

## 3. 真实运行时回归和浏览器

仅在独立本地或隔离测试环境执行，禁止连接生产数据。需要可取得真实依赖的网络环境；本轮环境未具备这一条件。

```bash
python -m venv .venv
# macOS/Linux
. .venv/bin/activate
# Windows PowerShell 改用 .venv\Scripts\Activate.ps1
python -m pip install -r app/requirements.txt -r tests_audit/requirements-test.txt
python -m playwright install chromium
python -m pip freeze > audit_results-runtime-resolved.txt
python tests_audit/run_regressions.py --with-matrix --coverage --out audit_results/real_runtime
python tests_audit/real_browser_acceptance.py --out audit_results/browser
```

上面真实运行时回归**不加**`--unit-double`，且运行器在测试启动前显式导入真实Streamlit，避免旧测试模块的兜底替身悄悄掩盖缺失。
浏览器脚本只绑定/访问127.0.0.1，复制临时仓库，使用合成身份和随机测试密码，清空Supabase配置，拦截非本机页面HTTP请求。不能换成在线应用URL。
只有真实执行的`browser_result.json`成功、`production_auth_smoke_executed=true`、8条case结果以及截图/trace均存在，才可称脚本限定的浏览器层通过。完整注册、问卷、管理和目标浏览器人工验收仍须单独记录。
本轮交付的 `audit/browser_result.json` 是0例/BLOCKED；脚本存在不等于脚本已跑通。

## 4. 证据保存

每次修订保存实际源码ZIP、相对本候选及唯一基线的diff、SHA清单、测试命令/环境/退出码/日志。不得用空源码恢复包代替候选。记录真实安装版本，不声称原范围依赖就是可逐位重现的锁文件。
GitHub Actions配置随仓库交付，但本轮没有运行线上CI，更没有推送触发部署。CI通过也仅覆盖它实际执行的层。
