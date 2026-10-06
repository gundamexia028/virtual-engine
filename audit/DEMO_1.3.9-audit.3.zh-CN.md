# 国赛演示评审版：启动和交付核验

此版本是护理教学仿真，不用于真实诊疗。演示只使用匿名虚构学员和内置虚构后台数据。

## 运行

1. 安装官方依赖：`python -m pip install -r app/requirements.txt`。
2. 根据 `app/.streamlit/secrets.example.toml` 在本机创建非提交文件 `app/.streamlit/secrets.toml`。设置 `APP_MODE = "competition"`，按模板配置评审体验码、只读管理码和不少于32字符的独立随机授权签名密钥。不要使用模板空值或把密钥发到聊天/仓库。
3. 先进入 `app` 目录，再执行 `python -m streamlit run streamlit_app.py`。看到版本 `V1.3.9-audit.3` 后进入评审体验。
4. 演示机保持运行；不要把一次性容器本地存储当成永久科研数据保存。

## 更新后必须完整重启

代码更新后，在演示应用管理控制台执行完整Reboot，然后用新浏览器会话重新登录，实际点击临床与学院的“开始本阶段”。线上audit.2曾出现新入口文件与已加载旧Simulator类不一致，完整重启后恢复；不能只看版本页面或自动部署日志就算验收，也不要用catch掩盖此错误。此步骤不清理数据。

## 现场演示清单

- 评审入口能进入学院与临床体验，页面不要求真实个人信息。
- 临床依次演示基线评估→填写必需补充信息→继续后续流程→模拟培训→继续后续流程→培训后考核；保持同一匿名学员，每阶段使用新会话；最终显示三阶段完成。
- 学院依次演示课前测评→模拟训练→确认结束→课后考核→SUS及教学体验→全流程完成。
- 训练中的取消结束/返回查看不重复保存，不重新开放已结束病程；明确重新开始才创建新会话。
- 更换演示学员后旧成绩、问卷和操作不残留；新一轮报告对应当前学员与会话。
- 刷新仅在同浏览器恢复当前草稿；出现草稿不可用警告时不要刷新，先解决演示机磁盘路径问题。
- 后台用只读评审管理入口查看虚构数据；competition禁止正式数据库读写和机构管理修改。
- 1366×768及窄屏检查按钮可读、无水平溢出、完成页分数与操作历史一致。

## 自动化复跑

`python -m pip install -r tests_audit/requirements-test.txt`

`python -m playwright install chromium`

`python tests_audit/run_regressions.py --out audit_results/regressions --with-matrix --coverage`

`python tests_audit/real_browser_acceptance.py --out audit_results/browser`

结果须分别标注单元/真实AppTest/有界矩阵/真实浏览器。外部数据库stub不代表真实端到端。实际CI由发布方针对最终源提交运行并核验。

## 回退

由授权发布方回退至 `f243720049cc77e4d9cd05030853b47aa0bebfa6`，不删除数据目录，不改另一版本。此前提是现场确认新版出现不可接受回归；audit.2含已修复缺陷，不能视为等价稳定替代。
