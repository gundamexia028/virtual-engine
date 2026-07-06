# CURRENT_STATUS.md

## 1. 状态更新时间

更新时间：2026-07-06

当前阶段：原六阶段路线图的阶段1和阶段2已完成；V1.3.8比赛评审专用模式与学院连续教学流程候选已通过PR #6整合进入`develop`，当前正式基线为`e964a9410de9663904c137ab24e8a94b4792ae31`；阶段3“拆分应用流程和会话恢复”尚未开始，阶段4“拆分认证、存储、问卷和管理服务”尚未开始

状态性质：以原224项路线图阶段2回归为基础，competition候选新增32项评审模式测试和40项候选稳定性测试，当前共296/296通过；PR #7已修复统一验证脚本在`develop`上的运行限制，脚本在当前基线返回码为0；路线图阶段语义已校准，competition作为已整合的比赛/评审候选能力和独立功能改进记录，不改变阶段编号；competition与production账号、权限和数据读写已代码级隔离；学院合规给药配合、错误后恢复、统一时间显示、考试自动结束、训练手动确认、重启确认、幂等与三阶段连续流程已增加保护；4份情景JSON、医学、评分、时间窗、生命体征、12条黄金路径和黄金快照未改变；最小页面回归、生产Supabase、RLS和正式部署仍未完成

本文件依据：

* `working/V1.3.8_READONLY_AUDIT.md`
* `working/V1.3.8_BASELINE_REGISTER.md`
* `working/V1.3.8_DEV_REGISTER.md`
* `working/V1.3.8_ENVIRONMENT_AUDIT.md`
* `working/V1.3.8_DEPENDENCY_INSTALL_REPORT.md`
* `working/V1.3.8_LOCAL_CONFIG_REPORT.md`
* `working/V1.3.8_LOCAL_SMOKE_TEST.md`
* `working/V1.3.8_CREDENTIAL_FALLBACK_FIX_REPORT.md`
* `working/V1.3.8_VERSION_ALIGNMENT_REPORT.md`
* `working/V1.3.8_VERSION_PRECHANGE.md`
* `working/V1.3.8_VERSION_POSTCHANGE.md`
* `working/V1.3.8_FULL_WORKFLOW_TEST_REPORT.md`
* `working/V1.3.8_FULL_WORKFLOW_TEST.log`
* `working/V1.3.8_SESSION_RECOVERY_REPORT.md`
* `working/V1.3.8_SESSION_RECOVERY_TEST.log`
* `working/V1.3.8_CLINICAL_RESULT_PAGE_FIX_REPORT.md`
* `working/V1.3.8_CLINICAL_RESULT_PAGE_FIX_TEST.log`
* `working/V1.3.8_ACADEMY_QUESTIONNAIRE_IDEMPOTENCY_REPORT.md`
* `working/V1.3.8_ACADEMY_QUESTIONNAIRE_IDEMPOTENCY_TEST.log`
* `working/V1.3.8_ORGANIZATION_ISOLATION_TEST_REPORT.md`
* `working/V1.3.8_ORGANIZATION_ISOLATION_TEST.log`
* `working/V1.3.8_ORGANIZATION_AUTHORIZATION_FIX_REPORT.md`
* `working/V1.3.8_ORGANIZATION_AUTHORIZATION_FIX_TEST.log`
* `working/V1.3.8_ORG_CODE_HASH_FIX_REPORT.md`
* `working/V1.3.8_ORG_CODE_HASH_FIX_TEST.log`
* `working/V1.3.8_GIT_INITIALIZATION_REPORT.md`
* `source_packages/PACKAGE_REGISTER.md`
* `docs/MODULAR_ARCHITECTURE_PLAN.md`
* `docs/SCENARIO_BEHAVIOR_CONTRACT.md`

## 2. 当前工作区

工作区路径：当前项目根目录（本文档统一使用相对路径，不记录本机绝对路径）。

当前已经建立的目录包括：

* `docs/`
* `references/`
* `source_packages/`
* `source_packages/archive/`
* `releases/`
* `releases/archive/`
* `app/`
* `working/`
* `tests/`

## 3. 基线信息

### 3.1 原始包

| 项目 | 当前记录 |
|---|---|
| 原始包 | `source_packages/V1.3.8.zip` |
| SHA-256 | `04678A30C1352F517B131CEB58CD0AD20585C84E545890BC77CCAE2521A6E649` |
| 文件名标示版本 | V1.3.8 |
| 实际系统版本 | 尚未完全确认 |
| 原始包登记文件 | `source_packages/PACKAGE_REGISTER.md` |

证据来源：审计报告第3节；基线登记文件第2节；原始包登记文件第3节。

### 3.2 只读基线

| 项目 | 当前记录 |
|---|---|
| 只读基线目录 | `working/V1.3.8_baseline/V1.3.8/` |
| 基线文件数 | 28 |
| 基线目录数 | 8 |
| 基线总大小 | 887590 字节 |
| 审计文本文件数 | 25 |
| 基线完整性登记 | `working/V1.3.8_BASELINE_REGISTER.md` |
| 第一次只读审计报告 | `working/V1.3.8_READONLY_AUDIT.md` |

证据来源：审计报告第1节；基线登记文件第4节。

### 3.3 基线保护结论

`working/V1.3.8_baseline/V1.3.8/` 是只读接管基线，不应直接修改。

迁移前开发副本已经建立并保留：

`working/V1.3.8_dev/`

开发副本创建时与只读基线的相对路径、文件数量、文件大小、SHA-256和目录结构完全一致。

正式Git开发目录已经建立：

`app/`

后续正式开发、测试和修改在`app/`进行；`working/V1.3.8_dev/`作为迁移前开发快照不再继续修改；只读基线仍不得修改。

### 3.4 开发副本

| 项目 | 当前记录 |
|---|---|
| 迁移前开发快照 | `working/V1.3.8_dev/` |
| 创建时文件数 | 28 |
| 创建时与基线一致性 | 完全一致 |
| 开发副本登记 | `working/V1.3.8_DEV_REGISTER.md` |
| 正式Git开发目录 | `app/` |
| 正式目录文件数 | 35 |
| 迁移校验 | 35/35相对路径、大小和SHA-256一致；随后仅对示例配置和README进行安全消毒 |
| 后续用途 | `app/`用于正式开发；`working/`用于基线、报告和回滚资料 |

## 4. 已完成事项

### 4.1 项目目录骨架

已完成项目目录和基础 Markdown 文件的创建。

### 4.2 项目级行为规则

已完成：

`AGENTS.md`

该文件规定了默认交流方式、任务前读取顺序、双模式约束、版本规则、医学安全约束、数据和权限约束、代码修改原则、文件操作规则、Git规则、高风险操作限制、文档维护要求、任务执行流程和完成后的汇报格式。

### 4.3 项目背景

已完成：

`docs/PROJECT_CONTEXT.md`

该文件记录项目名称、项目性质、背景、训练目标、目标使用人群、双模式设计原则、预期系统组成、数据应用目标、权限与隐私目标、版本管理背景和医学依据管理原则。

### 4.4 长期决策

已完成：

`docs/DECISIONS.md`

当前已经记录 DEC-001 至 DEC-032，共 32 项项目决策。

### 4.5 原始包登记

已完成：

`source_packages/PACKAGE_REGISTER.md`

当前登记的原始包为：

`source_packages/V1.3.8.zip`

### 4.6 受控解压与基线登记

已完成：

`working/V1.3.8_BASELINE_REGISTER.md`

只读基线目录为：

`working/V1.3.8_baseline/V1.3.8/`

### 4.7 第一次只读代码接管审计

已完成：

`working/V1.3.8_READONLY_AUDIT.md`

审计范围包括：

* 技术栈；
* 版本核实；
* 项目结构；
* 模块与调用关系；
* 功能实现矩阵；
* 病例与评分结构；
* 数据流与存储；
* 配置与部署；
* 安全与敏感信息；
* 代码质量与维护风险；
* 测试现状；
* README 与代码一致性；
* 风险清单；
* 后续步骤。

### 4.8 独立开发副本

已完成开发副本创建和基线一致性校验：

`working/V1.3.8_DEV_REGISTER.md`

### 4.9 Python与依赖环境

已完成：

* Python 3.13.14独立虚拟环境；
* `requirements.txt`安装；
* `pip check`；
* 依赖快照；
* Python 3.13依赖安装兼容验证。

主要证据：

* `working/V1.3.8_ENVIRONMENT_AUDIT.md`
* `working/V1.3.8_DEPENDENCY_INSTALL_REPORT.md`
* `working/V1.3.8_DEPENDENCY_SNAPSHOT.txt`

### 4.10 安全本地测试配置

已创建本地专用Secrets：

`working/V1.3.8_dev/.streamlit/secrets.toml`

字段仅包括：

* `APP_ACCESS_CODE`
* `ADMIN_PASSWORD`

使用随机本地测试凭据，未写入Supabase URL、Key或生产凭据。完整凭据保存在开发副本外，不得写入管理文档。

`.gitignore`已排除`.streamlit/secrets.toml`。

证据：`working/V1.3.8_LOCAL_CONFIG_REPORT.md`。

### 4.11 首次本地离线启动

已完成Streamlit首次本地离线启动和基础页面冒烟检查：

`working/V1.3.8_LOCAL_SMOKE_TEST.md`

应用成功启动，健康检查和首页返回200；错误访问码被拒绝，正确本地访问码可以进入，临床模式和学院模式入口均可见。

### 4.12 第一次正式代码安全修复

已在开发副本完成：

`移除默认访问码和默认管理员密码兜底`

修复结果：

* `APP_ACCESS_CODE`和`ADMIN_PASSWORD`必须同时有效配置；
* 缺失、空字符串、仅空格、非字符串、两值相同或Secrets读取异常时安全失败；
* 配置错误仅显示非敏感提示并通过Streamlit停止当前执行；
* 正确本地访问码和管理员密码仍可进入对应入口；
* 错误凭据仍被拒绝；
* 临床模式和学院模式入口不受影响；
* 20项专项测试和6项现有烟雾测试全部通过；
* 本地浏览器回归、健康检查、进程终止和端口释放全部通过；
* 未连接Supabase，未产生业务数据写入。

证据：

* `working/V1.3.8_CREDENTIAL_FALLBACK_FIX_REPORT.md`
* `working/V1.3.8_CREDENTIAL_FALLBACK_FIX_TEST.log`
* `working/V1.3.8_CREDENTIAL_FALLBACK_PRECHANGE.txt`
* `working/V1.3.8_CREDENTIAL_FALLBACK_POSTCHANGE.txt`

### 4.13 V1.3.8版本语义审计与最小统一

已完成：

* 完整读取20个版本相关文本文件；
* 按语义清点183处版本标识记录；
* 区分系统、包、病例、数据结构和历史版本；
* 将开发副本当前系统版本统一为V1.3.8；
* 将Python包版本统一为1.3.8；
* 在`peds_anaphylaxis_sim/__init__.py`建立唯一运行时代码来源；
* 页面角标、侧边栏和管理端标题统一引用`APP_VERSION`；
* README当前版本说明统一为V1.3.8；
* 病例、schema、历史文档和旧数据字段保持不变；
* 7项版本一致性测试全部通过；
* 全部Python测试33/33通过；
* localhost健康检查和首页均返回200；
* 未连接Supabase，未产生业务数据写入。

证据：

* `working/V1.3.8_VERSION_ALIGNMENT_REPORT.md`
* `working/V1.3.8_VERSION_PRECHANGE.md`
* `working/V1.3.8_VERSION_POSTCHANGE.md`
* `working/V1.3.8_VERSION_ALIGNMENT_TEST.log`

### 4.14 V1.3.8核心业务全流程验证

已完成：

* 20项凭据测试、6项既有烟雾测试、7项版本测试和16项新增全流程测试，最终49/49通过；
* 临床初始/变体和学院初始/变体病例的训练与考核标准路径；
* 4个场景文件共82个声明操作的基础执行检查；
* 正确/错误分支、病情变化、评分维度、复评、家属沟通和SBAR验证；
* localhost普通访问码、双模式入口、登记必填校验和管理员登录；
* 两条虚构临时记录的本地历史读取、临床/学院模式筛选和导出数据生成；
* 无Supabase本地降级、仅本机监听、进程终止、端口释放和测试数据清理；
* 只读基线28/28完整，版本统一后的业务源文件哈希未变化。

24项业务场景分类：

* 通过17项；
* 部分通过4项；
* 失败1项；
* 未实现1项；
* 当前环境无法验证1项。

本轮发现的主要问题：

* 页面刷新丢失训练进度问题已在后续专项修复中解决；
* 临床完成后结果页面未进入正常流程的问题已在后续专项修复中解决；
* 问卷保存失败缺少可靠恢复保护；
* 本地结果写入缺少Session级幂等；
* 单位管理员真实登录隔离和文本筛选仍需继续动态验证。

证据：

* `working/V1.3.8_FULL_WORKFLOW_TEST_REPORT.md`
* `working/V1.3.8_FULL_WORKFLOW_TEST.log`
* `working/V1.3.8_dev/tests/full_workflow_validation.py`

### 4.15 训练进度刷新恢复修复

已完成：

* 为临床/学院、训练/考核四类流程建立统一的训练草稿快照；
* 使用64位十六进制随机恢复标识、客户端特征摘要、SHA-256校验和和12小时有效期；
* 恢复当前模式、病例、分支、操作、评分维度、反馈、复评、沟通和未完成阶段；
* 损坏、无效、过期或绑定不匹配的草稿安全返回入口；
* 完成、主动重新登记、模式切换和重置时清理草稿；
* 草稿不保存普通访问码、管理员密码、Secrets或管理员权限状态；
* 新增13项专项测试，全部通过；当前自动测试合计62/62通过；
* localhost真实刷新验证保持时间60秒、得分20/100和操作数2；
* 未连接Supabase，未产生业务结果文件，临时数据已清理；
* 只读基线28/28完整。

证据：

* `working/V1.3.8_SESSION_RECOVERY_REPORT.md`
* `working/V1.3.8_SESSION_RECOVERY_TEST.log`
* `working/V1.3.8_dev/tests/session_recovery_tests.py`

### 4.16 临床模式结果页闭环修复

已完成：

* 临床训练和临床考核保存后进入完整结果页；
* 显示临床模式、任务类型、病例、完成状态、总分、模块评分、关键时间轴、问题和现有操作反馈；
* 提供继续后续流程、重新开始本阶段和返回首页入口；
* 完成态草稿支持刷新后继续停留在结果页；
* 重复完成不重复生成报告或追加结果记录；
* 后续流程异常时保留已完成结果和完成态草稿；
* 学院训练、学院考核及原有课后评价门控保持不变；
* 新增15项专项测试；当前自动测试合计77/77通过；
* Streamlit AppTest结果页组件和重复运行通过；
* localhost健康检查和首页返回200，未连接Supabase，无测试数据残留；
* 只读基线28/28完整。

证据：

* `working/V1.3.8_CLINICAL_RESULT_PAGE_FIX_REPORT.md`
* `working/V1.3.8_CLINICAL_RESULT_PAGE_FIX_TEST.log`
* `working/V1.3.8_dev/tests/clinical_result_page_tests.py`

### 4.17 学院问卷失败恢复与本地JSONL跨进程幂等

已完成：

* 学院课后考核训练结果在进入问卷前先保存到本地报告和训练JSONL；
* 问卷失败时保留训练结果、问卷答案草稿、随机完成标识和随机问卷提交标识；
* 页面刷新或同一浏览器在进程重启后可恢复待提交问卷；
* 页面明确提示“训练结果已保存，问卷尚未提交成功”，并提供安全重试；
* 问卷重试成功后不重复保存训练结果或问卷；
* 本地训练结果按完成标识幂等，问卷按提交标识和完成标识幂等；
* JSONL读写使用跨进程文件锁、刷新和磁盘同步；
* 损坏行被安全跳过并记录文件名、行号和异常类型，不记录原始内容；
* 历史读取和导出时将独立问卷事件合并到对应训练完整报告；
* 两个独立进程并发保存同一完成标识或同一问卷提交标识时均只产生一条记录；
* 8个独立进程并发写入后JSONL仍可逐行解析；
* 新增10项专项测试；原有77项测试继续通过，当前合计87/87通过；
* 本地健康检查返回200和`ok`，无Supabase连接迹象，进程已终止且端口已释放；
* 测试数据和临时日志已清理，只读基线28/28完整。

证据：

* `working/V1.3.8_ACADEMY_QUESTIONNAIRE_IDEMPOTENCY_REPORT.md`
* `working/V1.3.8_ACADEMY_QUESTIONNAIRE_IDEMPOTENCY_TEST.log`
* `working/V1.3.8_dev/tests/academy_questionnaire_idempotency_tests.py`

### 4.18 单位管理员动态数据隔离验证

已完成32个动态隔离场景：

* 通过24项；
* 失败7项；
* 当前环境无法验证1项；
* 原有87项自动测试全部通过。

正常有效scope下，临床机构A、临床机构B、学院A和学院B均只读取到各自2条训练/考核记录；学院问卷仅合并到所属学院记录。页面汇总、历史数量、统计、操作明细、CSV和JSONL导出使用同一过滤后数据集，未复现四个合法单位之间的直接串库。

已发现P0阻断问题：

* 后台已解锁但`admin_scope`缺失时回退为`super_admin`；
* 本地JSONL先全量读取，再在页面层过滤；
* CSV和JSONL导出函数自身不接收或验证scope；
* 单位管理码记录的`code_type`缺少角色白名单校验；
* 空字段scope可以匹配空单位记录；
* 训练记录未使用已有`org_id`授权，仍依赖机构名称字符串。

单位名称严格相等能阻止近似名称误串库，但前后空格等同一单位变体也无法识别，名称规范化不可靠。应使用机构唯一ID作为授权主键。

本次不能形成“可试用”结论。未修改业务代码，虚构数据已清理，未连接外部服务，只读基线28/28完整。

证据：

* `working/V1.3.8_ORGANIZATION_ISOLATION_TEST_REPORT.md`
* `working/V1.3.8_ORGANIZATION_ISOLATION_TEST.log`

### 4.19 单位管理员授权隔离修复

已完成：

* 缺失、空白、非法、未知、字段不完整或签名被篡改的scope全部安全拒绝；
* 后台不再以缺失scope回退平台管理员；
* 平台管理员只能由正确平台管理员密码路径显式建立；
* 单位管理员身份必须绑定`role`、`organization_type`和不可变`organization_id`；
* 机构显示名称不再作为权限边界；
* 已配置机构时，普通登记页从可信机构列表选择并写入机构ID；
* 本地摘要、完整报告、问卷合并、历史、统计、明细、质控、CSV和JSONL在数据访问或导出函数内部强制过滤；
* Supabase候选查询增加机构ID和类型过滤并保留返回后复核，但本次未连接真实Supabase；
* 既有缺少机构ID的历史记录对单位管理员默认不可见，仅显式平台管理员可查看；
* 原32个隔离场景复测32项通过、0项失败、0项无法验证；
* 原有87项测试继续通过，新增32项测试通过，当前合计119/119；
* 虚构测试数据和临时文件已清理；
* 只读基线28/28完整。

证据：

* `working/V1.3.8_ORGANIZATION_AUTHORIZATION_FIX_REPORT.md`
* `working/V1.3.8_ORGANIZATION_AUTHORIZATION_FIX_TEST.log`
* `working/V1.3.8_dev/tests/organization_authorization_tests.py`

### 4.20 旧式明文单位管理码兼容修复

已完成：

* 删除JSON明文`admin_code`兼容；
* 删除旧式无盐`admin_code_hash`验证；
* 删除后台固定字符串拼接、生成、暂存和显示明文单位管理码的路径；
* 单位管理员凭据改用身份绑定PBKDF2-HMAC-SHA256；
* 默认600000次迭代，随机16字节盐，32字节摘要；
* 摘要比较使用`secrets.compare_digest`；
* 每条凭据必须绑定`role`、`organization_type`和`organization_id`；
* 缺失、格式错误、身份不匹配、迭代不足或验证失败一律拒绝；
* 相同管理码误用于多个活动机构时检测多重匹配并拒绝登录；
* 新增加盐凭据模块和不回显管理码的本地CLI工具；
* CLI只输出JSON或可用于Streamlit Secrets的TOML哈希配置；
* 真实`config/org_access_codes.json`已加入`.gitignore`；
* 新增20项专项测试，原有119项测试继续通过，当前合计139/139；
* 原32项机构隔离场景继续32/32通过；
* 未连接外部服务，无测试数据残留，只读基线28/28完整。

证据：

* `working/V1.3.8_ORG_CODE_HASH_FIX_REPORT.md`
* `working/V1.3.8_ORG_CODE_HASH_FIX_TEST.log`
* `working/V1.3.8_dev/tests/org_credential_security_tests.py`

### 4.21 正式开发目录与本地Git基线

已完成：

* 从`working/V1.3.8_dev/`受控复制35个源代码、测试、配置模板和项目文档文件到`app/`；
* 排除`.venv/`、`.streamlit/secrets.toml`、`__pycache__/`、`.pyc`、JSONL、恢复草稿、日志和测试残留；
* 复制完成时35/35文件的相对路径、大小和SHA-256与迁移前开发快照一致；
* 将示例认证和Supabase值置空，并移除README中的旧默认访问码说明；
* 根目录`.gitignore`排除工作资料、原始包、发布包、Secrets、虚拟环境、缓存和运行数据；
* 对48个拟纳入文件完成敏感信息终检，未发现真实凭据、真实个人数据、Secrets文件或本机绝对路径；
* 在`app/`使用既有独立虚拟环境执行139项测试，139/139通过；
* 测试临时Secrets、缓存、日志和业务数据均已清理；
* 只读基线28/28文件大小和SHA-256仍与登记一致；
* 本地Git已初始化，默认分支为`main`，未配置远程仓库。

证据：

* `working/V1.3.8_GIT_INITIALIZATION_REPORT.md`
* `working/V1.3.8_APP_GIT_BASELINE_TEST.log`

### 4.22 模块化重构第1阶段：行为契约与黄金基线

已完成：

* 建立模块化架构评估和6阶段最小风险重构顺序；
* 建立场景结构契约，覆盖4份现有场景脚本；
* 当前脚本确认为`baseline + actions + dynamics + end_conditions`状态机，不虚构为显式节点图；
* 校验4个场景ID、4个隐式起始状态、82个动作选项、44条动态规则和4组结束条件；
* 为未来显式节点扩展建立节点ID、选项ID、目标引用、可达性、终止节点和允许循环校验；
* 建立临床训练、临床考核、学院训练、学院考核4类流程的12条黄金路径；
* 每类流程覆盖理想路径、典型错误路径和关键分支路径；
* 黄金快照固定节点/动作序列、选择、评分维度、最终生命体征、完成状态、关键反馈和结果页核心字段；
* 黄金快照排除时间戳、随机ID、会话标识、本机路径和Secrets；
* 新增20项场景结构契约测试和16项黄金行为测试，36/36通过；
* 原有139项测试继续通过，当前合计175/175；
* `streamlit_app.py`、引擎、病例、评分、页面、存储和权限运行逻辑均未修改；
* 4份场景文件SHA-256保持不变；
* 测试临时Secrets已清理，无JSONL、日志或业务数据残留；
* 未连接Supabase或其他外部业务服务；
* 只读基线28/28文件大小和SHA-256仍与登记一致。

证据：

* `docs/MODULAR_ARCHITECTURE_PLAN.md`
* `docs/SCENARIO_BEHAVIOR_CONTRACT.md`
* `app/tests/scenario_contract_tests.py`
* `app/tests/golden_behavior_tests.py`
* `app/tests/golden/v1_3_8_behavior_baseline.json`

### 4.23 模块化重构第2阶段：情景目录与加载器拆分

已完成：

* 保留`app/peds_anaphylaxis_sim/scenarios/`为4份现有情景定义的集中目录；
* 新增`scenario_catalog.py`，集中登记情景ID、脚本角色、文件名、系统模式、适用阶段、顺序和学院情景库ID；
* 新增`scenario_loader.py`，统一按情景ID、脚本角色、`system_mode + phase + library_id`或已登记路径加载情景；
* 入口页不再扫描情景目录，也不再根据分散JSON元数据自行决定阶段脚本；
* 引擎的通用文件加载入口委托给统一加载器，保留现有JSON及可选YAML兼容行为；
* 恢复草稿只接受已登记情景路径，并再次核对情景身份；
* 4份情景、6组阶段映射、12条黄金路径、82个动作和44条动态规则均保持一致；
* 4份情景JSON的SHA-256保持不变，黄金JSON快照无差异；
* 新增加载器和注册表专项测试22项，22/22通过；
* 原有175项测试继续通过，当前合计197/197；
* 未修改病例、医学内容、评分、生命体征、结束条件、页面文案、存储、权限、认证或问卷；
* 测试临时Secrets、缓存和JSONL临时数据已清理；
* 未连接Supabase或其他外部业务服务。

证据：

* `app/peds_anaphylaxis_sim/scenario_catalog.py`
* `app/peds_anaphylaxis_sim/scenario_loader.py`
* `app/tests/scenario_loader_tests.py`
* `app/tests/scenario_contract_tests.py`
* `app/tests/golden_behavior_tests.py`
* `app/tests/golden/v1_3_8_behavior_baseline.json`

### 4.24 模块化重构第3阶段：流程策略拆分

已完成：

* 新增`flow_strategies.py`，建立临床训练、临床考核、学院训练和学院考核4个不可变流程策略；
* 统一策略明确管理模式标识、即时反馈、评分呈现、错误处理、结束策略、结果页行为、问卷衔接和会话恢复规则；
* 将临床/学院阶段定义、模式元数据和原入口`WORKFLOW_RULES`移入纯Python策略模块；
* 6个既有阶段继续映射到原脚本角色和原页面任务文案；
* `Simulator`通过情景受众与运行模式选择策略，提示启用和考试动作随机顺序不再由散落条件分支决定；
* Streamlit入口通过策略控制训练提示、即时剂量反馈、操作历史结果、实时评分、学院考核中性标签、手动结束、结果页和问卷衔接；
* 草稿继续使用`schema_version = 1`，新增可推导的流程策略身份核对；旧草稿缺少该字段时仍按既有模式与情景恢复；
* 临床完成页恢复和学院待提交问卷恢复继续遵守原规则；
* 新增27项流程策略契约测试，覆盖4种流程、6个阶段、策略唯一性、兼容映射、提示、评分、结束、结果页、问卷和恢复；
* 原有197项测试继续通过，当前合计224/224；
* 4份情景JSON、12条黄金快照、82个动作和44条动态规则保持一致；
* 未修改医学内容、评分规则、生命体征、页面视觉、存储、认证、权限或Supabase实现；
* 未连接Supabase或其他外部业务服务。

证据：

* `app/peds_anaphylaxis_sim/flow_strategies.py`
* `app/peds_anaphylaxis_sim/engine.py`
* `app/streamlit_app.py`
* `app/tests/flow_strategy_tests.py`
* `app/tests/golden_behavior_tests.py`
* `app/tests/golden/v1_3_8_behavior_baseline.json`

### 4.25 模块化路线图来源校准

根据Git历史、PR #2、PR #3、PR #4说明和实际代码职责，已确认：

* 六阶段路线图首次建立于提交`49bb5bc`，后续未发现正式路线图重排决策；
* 历史交付批次1为“行为契约与黄金基线”，经PR #2合并为`1114a21`，测试为175/175，对应原路线图阶段1；
* 历史交付批次2为“情景目录与加载器拆分”，经PR #3合并为`55afcaa`，测试为197/197，对应原路线图阶段2的情景目录和加载器部分；
* 历史交付批次3为“流程策略拆分”，经PR #4合并为`d023d93`，测试为224/224，补完原路线图阶段2的流程策略部分；
* PR #4已集中四类流程策略及其会话恢复规则，并增加恢复时的策略身份核对，但未建立应用流程协调器，也未分离草稿文件操作与Streamlit query/session适配；
* 原路线图阶段3“拆分应用流程和会话恢复”尚未完成，是当前下一阶段；
* 原路线图阶段4的唯一正式名称为“拆分认证、存储、问卷和管理服务”，尚未开始；
* 历史分支、PR和提交中的交付名称继续保留，不作为后续路线图阶段编号顺延依据。

证据：

* `docs/MODULAR_ARCHITECTURE_PLAN.md`第12节；
* `docs/DECISIONS.md` DEC-033；
* PR #2、PR #3、PR #4及其合并提交；
* `app/peds_anaphylaxis_sim/flow_strategies.py`；
* `app/streamlit_app.py`中的草稿、开始、完成、结果、返回和重置函数。

## 5. 已确认技术事实

以下内容依据只读审计、环境审计、依赖安装、配置建立和本地冒烟测试报告。

| 项目 | 状态 | 当前结论 | 主要证据 |
|---|---|---|---|
| 编程语言 | 已确认 | Python | 审计报告第4节；`streamlit_app.py`、`peds_anaphylaxis_sim/engine.py`、`tests/smoke_tests.py` |
| Web框架 | 已确认 | Streamlit | 审计报告第4节；`requirements.txt:1`、`streamlit_app.py:29`、`streamlit_app.py:4205-4227` |
| 入口文件 | 已确认 | `streamlit_app.py` | 审计报告第4节；`README.md:49-50`、`streamlit_app.py:4227` |
| 项目主要模块 | 已确认 | `streamlit_app.py`、`peds_anaphylaxis_sim/engine.py`、`peds_anaphylaxis_sim/scenarios/`、`config/`、`.streamlit/`、`tests/` | 审计报告第5节 |
| 配置方式 | 部分确认 | 支持`.streamlit/config.toml`、`st.secrets`、环境变量和本机`config/org_access_codes.json`；单位管理员凭据可由Secrets中的`ORG_ACCESS_RECORDS`提供；生产配置未确认 | 管理码修复报告第4、6节 |
| 依赖管理方式 | 已确认 | `requirements.txt`，依赖使用范围版本，不是精确锁定版本 | 审计报告第4节；`requirements.txt:1-2` |
| Python运行环境 | 已确认 | Python 3.13.14，虚拟环境位于`working/V1.3.8_dev/.venv/`；不使用全局Python直接运行 | 环境审计第8节；依赖安装报告第2-5节；冒烟报告第3节 |
| Python 3.12 | 已确认异常 | 当前Python 3.12安装缺少标准库文件且pip不可用，不作为本项目环境 | 环境审计第3节、第8节 |
| 依赖安装 | 已确认 | `requirements.txt`安装成功，`pip check`通过，未出现编译或wheel问题 | 依赖安装报告第9-13节 |
| Streamlit版本 | 已确认 | 1.58.0 | 依赖安装报告第10节；冒烟报告第3节 |
| Supabase Python客户端版本 | 已确认 | 2.31.0；仅安装SDK，本次未连接Supabase | 依赖安装报告第10节；冒烟报告第13节 |
| Python 3.13兼容性 | 部分确认 | 已通过依赖安装、Streamlit启动、HTTP健康检查、核心业务、恢复、结果页和学院问卷本地保存测试；生产环境和长时间运行未验证 | 依赖安装报告第13节；本次修复报告第8节 |
| 测试现状 | 部分确认 | 15个测试脚本共296项自动测试通过；包含原224项模块化基线、32项competition专项测试和40项候选稳定性测试；competition学院三阶段、评审只读管理端及production双入口已完成人工主流程验收，本轮页面微调仍需最小回归 | `docs/SCENARIO_BEHAVIOR_CONTRACT.md`；`app/tests/scenario_contract_tests.py`；`app/tests/golden_behavior_tests.py`；`app/tests/scenario_loader_tests.py`；`app/tests/flow_strategy_tests.py`；`app/tests/competition_mode_tests.py`；`app/tests/competition_stability_tests.py` |
| 当前数据保存方式 | 部分确认 | 默认保存在 `st.session_state`、本地报告、训练JSONL和独立问卷JSONL；历史读取时按完成标识合并；如 Supabase secrets 存在仍会使用既有数据库候选路径 | 审计报告第9节、第19节；本次修复报告第3-6节 |
| 是否存在真正数据库 | 部分确认 | 基线包内未发现数据库文件；外部真实数据库是否存在未确认 | 审计报告第19节 |
| 是否已连接 Supabase | 未发现 | 基线代码未内置真实 Supabase 连接配置；本次未连接外部服务 | 审计报告第10节、第19节 |
| 是否存在管理端 | 已确认 | 存在管理员后台 | 审计报告第7节、第19节 |
| 是否存在临床模式 | 已确认 | 存在临床模式 | 审计报告第7节、第19节 |
| 是否存在学院模式 | 已确认 | 存在学院模式 | 审计报告第7节、第19节 |
| 是否存在训练模式 | 已确认 | 存在训练模式，映射为 `coach` | 审计报告第7节、第8.6节 |
| 是否存在考核模式 | 已确认 | 存在考核/测评模式，映射为 `exam` | 审计报告第7节、第8.6节 |
| 是否存在评分系统 | 已确认 | 存在引擎评分、模块评分和报告得分 | 审计报告第7节、第8节 |
| 是否存在问卷 | 已确认 | 存在 SUS 问卷和教学体验问卷 | 审计报告第7节 |
| 是否存在历史记录 | 已确认 | 存在本地和数据库候选读取逻辑 | 审计报告第7节、第9节 |
| 是否存在数据导出 | 已确认 | 存在 CSV 和 JSONL 导出 | 审计报告第7节、第9节 |
| 权限隔离 | 本地验证通过 | 本地JSONL模式下缺失或篡改scope安全拒绝；平台角色显式授权；单位按`organization_id`隔离；读取和导出函数内部强制过滤；32/32场景通过。Supabase RLS仍未验证 | 授权隔离修复报告第3-9节 |
| Streamlit Cloud 相关配置 | 部分确认 | 存在 `.streamlit/config.toml` 与 secrets 示例，但未见完整部署流程 | 审计报告第4节、第10节 |
| 本地安全配置 | 已确认 | 本地Secrets仅含`APP_ACCESS_CODE`和`ADMIN_PASSWORD`，使用随机测试值，未含Supabase或生产凭据 | 本地配置报告第8-13节 |
| 首次本地启动 | 已确认 | 监听`127.0.0.1:8502`，健康检查200和`ok`，首页200；进程已终止且端口已释放 | 冒烟报告第5-8节、第16节 |
| 基础页面交互 | 已确认 | 错误访问码被拒绝；正确本地访问码可进入；临床和学院入口可见 | 冒烟报告第9-10节 |
| 本次数据写入 | 已确认 | 未产生JSON、JSONL、CSV、SQLite、训练、问卷或其他业务数据文件 | 冒烟报告第14-15节 |

## 6. 版本状态

### 6.1 当前系统版本

开发副本当前系统版本：`V1.3.8`

Python包版本：`1.3.8`

运行时唯一代码来源位于：

`peds_anaphylaxis_sim/__init__.py`

`streamlit_app.py`中的`APP_VERSION`引用该来源。页面角标、侧边栏、管理端标题和未来记录中的`app_version`均通过`APP_VERSION`取得当前系统版本。

README当前标题和版本定位均为V1.3.8。

### 6.2 独立保留的版本语义

以下旧版本不再视为系统版本冲突：

* 临床场景V1.2.11：病例内容版本；
* 学院场景V1.3.5、V1.3.6等：病例演进和规则来源；
* `schema_version = 1`：数据结构版本；
* V1.1.x至V1.3.7源代码注释：历史规则来源；
* `docs/`和README中的旧版本段落：历史版本记录；
* 第三方依赖版本范围：Python依赖版本。

上述内容均按语义保留，不进行批量替换。

### 6.3 当前结论

开发副本的当前系统版本、包版本、README当前说明和页面主要版本显示已经统一到V1.3.8。

病例版本、数据结构版本和历史版本继续独立保留。当前尚未形成正式发布包，不修改`docs/VERSION_HISTORY.md`。

证据：`working/V1.3.8_VERSION_ALIGNMENT_REPORT.md`。

## 7. 安全风险

本节仅记录风险描述、文件位置、脱敏摘要、风险等级和建议处理顺序。

不得在本文件中写出完整密码、访问码或密钥。

| 顺序 | 风险等级 | 风险描述 | 文件位置 | 脱敏摘要 | 建议处理 |
|---:|---|---|---|---|---|
| 1 | 高风险来源已修复，示例风险仍在 | 默认管理员密码源代码兜底已移除；示例配置仍存在被误用风险 | `.streamlit/secrets.example.toml:5`、`streamlit_app.py:623-673`、`streamlit_app.py:3544` | 不记录原值；当前代码要求有效Secrets | 保持安全失败；后续单独处理示例Secrets和部署注入规则 |
| 2 | 高风险来源已修复，示例风险仍在 | 默认应用访问码源代码兜底已移除；README和示例配置仍存在被误用风险 | `README.md:53-57`、`.streamlit/secrets.example.toml:4`、`streamlit_app.py:623-673`、`streamlit_app.py:3407` | 不记录原值；当前代码要求有效Secrets | 保持安全失败；后续单独处理README、示例Secrets和部署注入规则 |
| 3 | 高 | Supabase Service Role Key 配置字段属于高权限凭据风险 | `.streamlit/secrets.example.toml:7-9`、`streamlit_app.py:898-947` | 示例为占位符，字段名指向高权限 key | 不得把示例配置当正式配置；先设计密钥管理、最小权限和RLS |
| 4 | 高 | 生产 Supabase 接入条件不足 | `streamlit_app.py:898-947`、`.streamlit/secrets.example.toml:7-9` | 未确认表结构、RLS、迁移和权限策略 | 不得直接连接生产 Supabase |
| 5 | 已修复 | 机构管理码兼容旧式明文字段 | 管理码修复报告第2-5节 | 明文字段和旧无盐SHA-256均已拒绝 | 保持PBKDF2身份绑定验证，不得恢复兼容 |
| 6 | 中 | 管理端权限主要为应用层过滤，数据库级隔离未确认 | `streamlit_app.py:681-714`、`streamlit_app.py:3573-3576` | scope 过滤存在；未见数据库级RLS证据 | Supabase接入前必须建立数据库级权限策略 |
| 7 | 已修复 | 运行时显示新生成管理码 | 管理码修复报告第5-6节 | 后台不再生成、暂存或显示明文管理码 | 仅使用本机getpass工具生成哈希配置 |
| 8 | 中 | 培训人员相关登记信息和导出权限风险 | `streamlit_app.py:728-779`、`streamlit_app.py:2085-2435`、`streamlit_app.py:3673-3677` | 姓名首字母、学校/班级、医院/科室等 | 需要最小化收集并强化导出权限 |
| 9 | 低 | 完整日志显示和下载可能扩大信息暴露 | `streamlit_app.py:4191-4201` | 完整报告和操作日志可显示/下载 | 后续复核日志内容和下载权限 |

审计报告未发现真实 API Key、真实数据库连接字符串、真实患者身份信息、`.env` 文件或 Webhook 地址。

证据来源：审计报告第11节、第15节、第19节。

当前高风险结论：

* 开发副本中的默认访问码和默认管理员密码源代码兜底已移除并通过测试；
* 正式目录中的示例认证和Supabase值已置空，README不再提供默认访问码；真实Secrets仍必须通过安全配置注入；
* 开发副本当前系统版本已统一为V1.3.8，但尚未形成正式发布包；
* 临床与学院核心引擎路径、历史读取和导出数据生成已验证；
* 单位管理员授权隔离已完成修复；本地JSONL模式下缺失或篡改scope安全拒绝，读取和导出按机构ID强制隔离，32/32场景通过；
* 旧式明文和无盐SHA-256单位管理码兼容已移除，当前使用身份绑定PBKDF2和恒定时间比较；
* 页面刷新丢失进行中训练的问题已修复，四类流程专项测试和临床训练localhost真实刷新均通过；
* SUS与教学体验问卷失败恢复、刷新/进程重启恢复和安全重试已通过专项测试；完整人工页面体验仍需试用验证；
* 尚不具备连接生产Supabase的条件；
* 尚不应部署生产环境。

## 8. 代码质量与维护风险

以下风险来自审计报告第12节和第15节：

| 风险等级 | 问题 | 证据 | 当前处理状态 |
|---|---|---|---|
| 高风险来源已修复 | 当前系统版本标识不一致 | 审计报告 R-003、QA-004；版本统一报告 | 开发副本已完成最小统一；病例、schema和历史版本按语义保留 |
| 中 | 发布包包含 `__pycache__` 和 `.pyc`；首次运行重新生成2个既有`.pyc` | 审计报告 R-005、QA-003；冒烟报告 SMOKE-001 | 未清理；业务源代码未变化；只读基线不修改 |
| 中 | `streamlit_app.py` 单文件过长 | 审计报告 QA-001 | 未处理 |
| 中 | `engine.py` 单文件较长 | 审计报告 QA-002 | 未处理 |
| 中 | 使用 `eval()` 执行场景表达式 | 审计报告 R-007、QA-007 | 未处理 |
| 中 | 宽泛异常处理可能隐藏错误 | 审计报告 R-008、QA-008 | 未处理 |
| 已修复 | 本地 JSONL 并发写入无保护 | 审计报告 R-006、QA-009；本次修复报告 | 已增加跨进程文件锁、稳定完成标识、问卷提交标识、磁盘同步和损坏行记录；并发测试通过 |
| 中 | Supabase SDK 调用未见显式超时设置 | 审计报告 QA-010 | 未处理 |
| 已修复 | 运行时写 `config/org_access_codes.json` | 审计报告 R-011、QA-011；管理码修复报告第5节 | 后台写入路径已移除；配置由本机CLI生成后安全注入 |
| 中 | README 与实际代码不一致 | 审计报告 QA-012 | 未处理 |
| 中 | 测试覆盖不足 | 审计报告 R-012、QA-013；模块化行为契约 | 当前175项自动测试通过，已增加4场景结构契约和12条黄金路径；真实WebSocket模糊测试和长时间运行仍未覆盖 |
| 已修复 | 页面刷新后进行中的训练状态丢失 | 全流程验证报告 FWT-001；刷新恢复报告 | 四类流程专项测试通过；临床训练localhost真实刷新恢复通过 |
| 已修复 | 临床正常完成后结果页未进入主流程 | 全流程验证报告 FWT-002；临床结果页修复报告 | 临床训练和考核均进入结果页，完成态刷新和重复结算测试通过 |
| 已修复 | 问卷保存失败缺少状态恢复保护 | 全流程验证报告 FWT-003；本次修复报告 | 训练结果先保存；问卷草稿、失败状态和随机提交标识可恢复并安全重试 |
| 已修复 | 本地JSONL保存缺少Session级幂等 | 全流程验证报告 FWT-004；本次修复报告 | 训练和问卷分别按稳定标识去重；两个独立进程并发测试通过 |
| 已修复 | 已解锁但scope缺失时回退平台管理员 | 单位隔离验证报告 ORG-P0-001；授权隔离修复报告第3、5节 | 缺失或无效授权会清除后台状态并在读取数据前退出 |
| 已修复 | 本地读取和导出未在函数边界强制scope | 单位隔离验证报告 ORG-P0-002、ORG-P0-003；授权隔离修复报告第6-8节 | 读取、统计、明细、CSV和JSONL均验证授权并在返回前过滤 |
| 已修复 | 单位管理码角色缺少白名单与scope完整性校验 | 单位隔离验证报告 ORG-P0-004、ORG-P0-005；授权隔离修复报告第3、5节 | 仅允许临床或学院单位角色；空白、非法、未知和篡改上下文安全拒绝 |
| 已修复 | 权限依赖机构名称而非唯一ID | 单位隔离验证报告 ORG-P0-006、ORG-M-001；授权隔离修复报告第4节 | 新记录和单位身份使用`organization_id`；名称仅展示；无ID历史记录对单位管理员默认不可见 |

## 9. 当前尚未完成事项

### 9.1 开发副本

正式目录迁移已完成，不再属于未完成事项。

正式Git开发目录：

`app/`

迁移前开发快照：

`working/V1.3.8_dev/`

后续正式修改只允许在`app/`进行；迁移前开发快照仅用于回滚和证据核对。

只读基线仍不得修改：

`working/V1.3.8_baseline/V1.3.8/`

### 9.2 运行环境

已确认并完成：

* Python 3.13.14；
* 独立虚拟环境；
* requirements安装；
* `pip check`；
* 安全本地Secrets；
* 无Supabase本地启动；
* HTTP健康检查；
* 访问码和双模式入口基础冒烟。

仍未完成：

* 短暂断线和浏览器误返回的独立动态恢复验证；
* 长时间运行和高负载并发验证。

证据来源：环境审计、依赖安装报告、本地配置报告和本地冒烟报告。

### 9.3 测试

当前测试文件共15个：

* `tests/smoke_tests.py`：6项；
* `tests/credential_security_tests.py`：20项；
* `tests/version_consistency_tests.py`：7项；
* `tests/full_workflow_validation.py`：16项；
* `tests/session_recovery_tests.py`：13项；
* `tests/clinical_result_page_tests.py`：15项；
* `tests/academy_questionnaire_idempotency_tests.py`：10项；
* `tests/organization_authorization_tests.py`：32项；
* `tests/org_credential_security_tests.py`：20项；
* `tests/scenario_contract_tests.py`：20项；
* `tests/golden_behavior_tests.py`：16项；
* `tests/scenario_loader_tests.py`：22项；
* `tests/flow_strategy_tests.py`：27项；
* `tests/competition_mode_tests.py`：32项。
* `tests/competition_stability_tests.py`：40项。

当前最终自动测试296/296通过。测试结构为：原有139项 + 第1阶段36项 + 第2阶段22项 + 第3阶段27项 + 评审模式32项 + 候选稳定性40项 = 296项。历史阶段中的175/175、197/197、224/224、256/256与288/288结果保留在对应阶段记录中，不代表当前最终基线。

已验证：

* 临床与学院四个场景的训练和考核标准路径；
* 82个声明操作的基础执行；
* 错误反馈、病情变化、评分、复评和SBAR；
* 本地历史读取、模式筛选和CSV/JSONL生成；
* 四类流程的训练进度刷新恢复；
* 临床训练和考核结果页闭环；
* 学院问卷失败后训练结果保护、草稿恢复和重试；
* 本地训练与问卷JSONL跨进程幂等和损坏行容错；
* 四个虚构单位按机构ID执行页面、历史、统计、明细和导出隔离；
* 缺失、空白、非法、未知和篡改scope安全拒绝；
* 直接调用数据读取和导出函数不能绕过单位过滤；
* 普通用户和单位管理员不能提升角色；
* 明文单位管理码、旧无盐SHA-256、缺失凭据参数和身份不匹配均安全拒绝；
* CLI的JSON与TOML输出不含原始管理码；
* 无Supabase本地降级。
* 4份场景结构、82个动作选项、44条动态规则和结束条件契约；
* 临床/学院、训练/考核4类流程共12条黄金行为路径；
* 黄金快照不含时间戳、随机ID、会话标识、本机路径或Secrets。
* 学院三阶段无需选择“独立完成急救注射”即可完成，等待老师和其他非终末错误后仍可纠正；
* 所有参与者可见模拟时间统一为`mm:ss`，重启、动作、跳转、完成和问卷具有UI幂等保护；
* 三阶段同一参与者、独立会话、独立完成页、结果页、问卷和全流程完成顺序；
* 模拟训练核心节点完成后等待学习者二次确认，继续操作不丢失状态，确认结束及刷新不重复保存；
* 训练完成页不显示内部空值，三阶段标题、问卷按钮和全流程侧栏使用与页面状态一致的中文；
* competition退出清理授权，production/competition入口、权限和数据源互不覆盖。

仍未完成：

* SUS和教学体验问卷本轮按钮文案最小人工回归；
* production问卷是否取消初始3分默认值仍需产品/研究设计确认；
* 高负载并发、短暂断线、浏览器误返回和长时间运行；
* Supabase测试环境、RLS和迁移验证。

当前按15个测试脚本分别运行；其中`unittest`共290项，另含6项冒烟检查，合计296项。仓库沿用既有`unittest`与轻量冒烟结构，不依赖`pytest`。统一入口为`scripts/verify_competition_candidate.py`。

证据来源：`working/V1.3.8_FULL_WORKFLOW_TEST_REPORT.md`、`working/V1.3.8_SESSION_RECOVERY_REPORT.md`、`working/V1.3.8_CLINICAL_RESULT_PAGE_FIX_REPORT.md`、`working/V1.3.8_ACADEMY_QUESTIONNAIRE_IDEMPOTENCY_REPORT.md`、`working/V1.3.8_ORGANIZATION_AUTHORIZATION_FIX_REPORT.md`、`working/V1.3.8_ORG_CODE_HASH_FIX_REPORT.md`。

### 9.4 医学资料

已在`references/`建立规范引文与医学依据索引，当前主要依据为：

《中国康复医学会变态反应性疾病康复专业委员会等. 严重过敏反应诊断和临床管理专家共识[J]. 中华预防医学杂志, 2025, 59(6): 749-765. DOI:10.3760/cma.j.cn112150-20250109-00024.》

已完成：

* `references/README.md`：收录医学依据使用边界、版权与原创性边界；
* `references/医学依据索引.md`：建立诊断、去除诱因、呼救、肾上腺素、给氧、液体复苏、监测、复评、二线药物等规则与情景文件、动作ID、动态规则和代码位置的可追溯关系。

说明：该索引用于证明规则来源和教学转化路径，不等同于临床诊疗指南；系统仍仅用于护理教学、培训与科研可行性验证。

### 9.5 Git与远程仓库

当前状态：

* 本地Git已初始化；
* `main`和`develop`分支已建立；
* 当前模块化工作分支为`feature/modularization-stage-3`；
* 首次安全基线提交使用说明：`chore: establish secure virtual engine baseline`；
* 已配置私有GitHub远程仓库`origin`；
* 已建立从功能分支到`develop`、从`develop`到`main`的Pull Request流程；
* 已配置Python 3.13 GitHub Actions自动测试；
* 未配置自动部署。

首次Git安全基线以175项测试建立；模块化第3阶段扩展至224项，评审模式候选先扩展至256项，候选稳定性收口先扩展至288项，本轮最终页面收口扩展至296项，并保留既有开发安全基线。

证据来源：`working/V1.3.8_GIT_INITIALIZATION_REPORT.md`。

### 9.6 Supabase与生产环境

当前状态：

* 基线代码支持 Supabase；
* 基线包内未发现真实 Supabase 连接配置；
* 外部真实数据库是否存在未确认；
* 未配置测试 Supabase；
* 未配置生产 Supabase；
* 未建立数据库迁移；
* 未配置 Row Level Security 策略；
* 未建立测试与生产环境隔离；
* 未配置正式部署流程。

审计报告结论：不具备直接接入生产 Supabase 的条件。

证据来源：审计报告第10节、第19节。

## 10. 当前禁止事项

在完成其余P0安全事项、完整测试和必要动态验证前，不得：

* 直接修改只读基线；
* 直接向`main`推送功能修改；
* 绕过Pull Request审查合并模块化重构；
* 连接生产 Supabase；
* 部署生产环境；
* 使用默认管理员密码；
* 使用默认访问码；
* 将示例 Secrets 作为正式配置；
* 将当前版本直接标记为已验证稳定版；
* 将当前代码直接交付正式学生或临床研究采集使用；
* 把旧版本标识无审计地批量替换为 V1.3.8；
* 自动修复审计中发现的问题；
* 修改医学剂量或关键流程。

## 11. 下一阶段目标

下一阶段为：

执行原六阶段路线图阶段3“拆分应用流程和会话恢复”。

建议顺序：

1. 以已完成的4个流程策略、6个阶段映射、27项专项测试、224项路线图阶段2回归和296项competition整合回归作为输入基线；
2. 每次提交前运行296项回归并核对4份情景哈希和12条黄金快照；
3. 建立应用流程协调器；
4. 将开始、完成、结果页、返回和重置转为显式状态转换；
5. 将草稿文件操作与Streamlit query/session适配分开；
6. 保持现有快照schema、恢复行为、医学、评分和结果格式不变；
7. 本阶段不提前拆分认证、存储、问卷和管理服务；
8. 生产接入条件未满足前不得连接生产Supabase或部署。

## 12. 当前结论

当前已完成：

* 项目管理骨架；
* 原始包登记；
* 受控解压；
* 只读基线完整性登记；
* 第一次只读代码接管审计；
* 审计结果管理文档固化；
* 独立开发副本和一致性校验；
* Python 3.13.14独立虚拟环境；
* 项目依赖安装和`pip check`；
* 安全本地Secrets；
* 首次本地离线启动；
* HTTP健康检查和基础页面交互冒烟；
* Python 3.13首次运行验证；
* 默认凭据安全修复；
* V1.3.8版本语义审计与最小统一；
* 296项自动测试，其中交付批次2新增22项加载器测试、交付批次3新增27项流程策略测试、评审模式新增32项、候选稳定性累计新增40项；
* 模块化架构评估与6阶段重构计划；
* 场景行为契约、20项结构校验和12条黄金行为路径；
* 原路线图阶段2已通过交付批次2和3完成统一情景注册表、纯Python加载器、阶段路由及四类流程策略；
* 历史交付批次3已完成临床训练、临床考核、学院训练和学院考核统一流程策略；
* 临床和学院核心业务全流程验证；
* 临床、学院、训练和考核四类流程的刷新恢复专项验证；
* 临床训练localhost真实刷新恢复验证；
* 临床训练和考核结果页闭环及完成态刷新恢复；
* 学院问卷失败恢复、刷新/进程重启恢复和安全重试；
* 本地训练及问卷JSONL跨进程幂等、损坏行容错和历史合并；
* 单位管理员动态数据隔离验证32项；
* 缺失scope角色提升、单位管理码角色校验、机构ID授权、数据读取和导出层隔离修复；
* 旧式明文和无盐SHA-256单位管理码兼容移除；
* 身份绑定PBKDF2验证与本地安全生成工具；
* 正式Git开发目录`app/`及根目录安全忽略规则；
* 提交前敏感信息终检；
* `app/`正式目录当前296/296回归；
* 本地Git初始化和`main`分支；
* 修复后原32项隔离场景全部通过；
* localhost登记、双模式、错误分支和管理端交互；
* 临时本地历史、模式筛选和导出数据验证；
* 测试数据清理、端口释放和基线完整性复核。

当前未完成：

* 原路线图阶段3的应用流程协调器、显式状态转换和会话恢复适配拆分；
* 原路线图阶段4的认证、存储、问卷和管理服务拆分；
* SUS和教学体验问卷完整人工页面体验验证；
* 短暂断线和浏览器误返回场景的独立动态验证；
* 既有无机构ID历史记录的受控迁移；
* 生产Supabase表字段和RLS权限验证；
* 高负载并发与长时间运行验证；
* Supabase 测试环境设计；
* 医学依据追溯。

当前项目技术实现状态应表述为：

`正式Git开发目录app/已建立；原六阶段路线图阶段1和阶段2已完成，阶段3“拆分应用流程和会话恢复”为下一阶段且尚未开始，阶段4“拆分认证、存储、问卷和管理服务”尚未开始。V1.3.8同一程序内的competition评审候选已完成统一APP_MODE、独立评审账号、只读虚拟后台、互斥存储、学院合规给药配合、可恢复错误分支、统一时间、连续三阶段、训练手动确认、重启确认和幂等保护；4份情景、12条黄金路径、82个原动作、44条动态规则和296项自动测试均保持通过。病例、医学内容、评分、时间窗、生命体征和黄金快照未改变。production问卷默认值、生产Supabase、RLS、历史机构ID迁移和正式部署仍未验证。`

当前正式目录相对只读基线的计划内业务变化：

* 修改：`streamlit_app.py`、`README.md`、`peds_anaphylaxis_sim/__init__.py`、`peds_anaphylaxis_sim/engine.py`；
* 新增安全模块与工具：`peds_anaphylaxis_sim/org_credentials.py`、`tools/generate_org_admin_credential.py`；
* 新增测试：`tests/credential_security_tests.py`、`tests/version_consistency_tests.py`、`tests/full_workflow_validation.py`、`tests/session_recovery_tests.py`、`tests/clinical_result_page_tests.py`、`tests/academy_questionnaire_idempotency_tests.py`、`tests/organization_authorization_tests.py`、`tests/org_credential_security_tests.py`；
* 新增模块化基线测试：`tests/scenario_contract_tests.py`、`tests/golden_behavior_tests.py`和`tests/golden/v1_3_8_behavior_baseline.json`；
* 新增情景注册表与加载器：`peds_anaphylaxis_sim/scenario_catalog.py`、`peds_anaphylaxis_sim/scenario_loader.py`；
* 新增加载器专项测试：`tests/scenario_loader_tests.py`；
* 新增流程策略与专项测试：`peds_anaphylaxis_sim/flow_strategies.py`、`tests/flow_strategy_tests.py`；
* 病例JSON、评分标准、问卷题目和版本号未因本次管理码修复改变；
* 只读基线28个文件的大小和SHA-256仍与登记一致；
* `.pyc`和`__pycache__`属于运行缓存，已由根目录`.gitignore`排除；
* 后续正式开发路径为`app/`，`working/`仅保留基线、报告、迁移前快照和回滚资料。
