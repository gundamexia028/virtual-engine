# 正式入口行为契约与部署边界

## 1. 文档目的

本文件锁定三个彼此独立的系统入口：旧版公网系统、新版 production 正式系统、
新版 competition 评审系统。它只描述入口、权限、数据和部署边界，不改变医学、
评分、情景或数据库结构。

## 2. 历史入口演进

### 2.1 最早网页原型

最早原型以单一训练入口验证动态分支、生命体征、操作选择和结果报告。该阶段没有
当前的临床/学院双模式入口，也没有 competition 评审隔离层。

### 2.2 V1.1.3 正式采集入口

V1.1.3 将正式采集入口标准化为：访问码 → 对象登记 → 评估阶段。院区、科室和
参与者编号由正式采集规则生成，评估阶段固定为基线评估、模拟培训和培训后考核。

### 2.3 V1.3.4 临床/学院双模式入口

V1.3.4 在同一正式程序中增加临床/学院模式选择。临床模式保留正式临床训练流程；
学院模式进入学院教学情景库、护生登记及课前/训练/课后教学流程。

## 3. 当前仓库与旧版仓库

### 3.1 当前新版唯一开发主仓库

- Repository：`gundamexia028/virtual-engine`
- 当前候选分支：`feature/competition-review-mode`
- 入口文件：`app/streamlit_app.py`
- production 与 competition 均从本仓库同一入口文件启动，由 `APP_MODE` 隔离。

### 3.2 旧版公网系统

- 旧网址：`https://peds-anaphylaxis-simulation-ktdrprhqmsz7sl3tk5wlxg.streamlit.app/`
- 旧仓库：`peds-anaphylaxis-simulation`
- 旧部署坐标：`peds-anaphylaxis-simulation / main / streamlit_app.py`

旧版系统不是当前仓库的部署实例。当前不得修改、删除或向旧仓库复制新版代码，
也不得让旧网址在新版验收前切换到新版代码。

## 4. production 正式入口契约

`APP_MODE="production"` 时：

1. 打开新版正式系统；
2. 输入正式 `APP_ACCESS_CODE`；
3. 进入临床模式/学院模式选择；
4. 临床模式进入正式对象登记、临床训练、正式报告和正式数据逻辑；
5. 学院模式进入学院情景库、护生登记、课前测评、模拟训练、课后考核、结果和问卷。

production 不得显示比赛评审演示环境、评审体验码、评审管理码、虚拟数据提示、
competition 虚拟身份或评审只读后台提示。competition 结果目录不得覆盖 production
正式数据目录；未配置 Supabase 时只能使用明确的本地或测试存储，不得伪装线上写入。

## 5. competition 评审入口契约

`APP_MODE="competition"` 时：

1. 显示“比赛评审演示环境”；
2. 评审体验码只能进入虚拟体验范围；
3. 评审管理码只能进入“评审只读环境”；
4. 体验使用虚拟身份和 competition 专用写目录；
5. 只读管理端只读取 `app/demo_data/`；
6. 页面明确说明“虚拟演示数据，不代表实际研究结果”。

competition 禁止读取或写入 production runtime、正式 Supabase、正式医院/学院/科室/
人员信息、正式访问码和正式管理写入口。管理端不得提供新增、编辑、删除或生成访问码。
`AUTH_CONTEXT_SIGNING_KEY` 未安全配置时管理授权必须拒绝；旧
`PEDSIM_PUBLIC_REVIEW_MODE` 仅在未明确设置 `APP_MODE` 时提供弃用兼容。

## 6. 权限边界

| 能力 | production 体验 | production 管理 | competition 体验 | competition 管理 |
|---|---:|---:|---:|---:|
| 正式临床/学院入口 | 是 | 按正式权限 | 否 | 否 |
| competition 虚拟体验 | 否 | 否 | 是 | 否 |
| 正式数据读取/写入 | 按正式流程 | 按正式授权 | 否 | 否 |
| 虚拟演示数据读取 | 否 | 否 | 否 | 只读 |
| competition 临时结果写入 | 否 | 否 | 是 | 否 |
| 管理新增/编辑/删除 | 按正式既有权限 | 按正式既有权限 | 否 | 否 |

浏览器刷新、返回或带恢复标识重新进入时，服务端状态必须重新核对当前运行模式、
阶段顺序和管理授权；任何恢复都不得提升权限。

## 7. 数据边界

- production：使用 production 存储适配器；正式目录和正式 Supabase 能力保持原契约。
- competition 体验：只写 `PEDSIM_COMPETITION_RESULTS_DIR` 指向的专用目录。
- competition 管理：只读版本内 `app/demo_data/`，不合并本次评委临时体验记录。
- 两种模式的参与者身份、placeholder、访问码、授权上下文和结果路径互不复用。
- 四份情景 JSON、动作 ID、规则 ID、医学演化和评分内核由两种模式共同只读使用。

## 8. Streamlit 双 App 部署关系

后续公网需从 `virtual-engine` 创建两个独立 Streamlit App：

1. 新版 competition 评审 App：独立网址、独立 Secrets、
   `APP_MODE="competition"`、独立评审码和独立结果目录；
2. 新版 production 正式 App：独立网址、独立 Secrets、
   `APP_MODE="production"`、正式访问码和正式数据配置。

两个 App 可以使用同一入口 `app/streamlit_app.py`，但必须拥有独立网址、Secrets、
APP_MODE、访问码、权限范围、数据目录和部署配置。比赛期间可与旧版历史 App 同时存在，
因此最多为三个 App；新版稳定后再评估旧版退役，目标形态为两个新版 App。

## 9. 旧版迁移与退役原则

1. 当前不删除、不修改旧 App 和旧仓库；
2. 当前不把新代码复制回旧仓库；
3. 新版验收前不更改旧网址；
4. 旧版在新版 production 稳定运行一段时间前保留为回退参照；
5. 停用旧版必须另行评估数据、网址、用户通知和回退方案。

## 10. 本地启动与明早验收

运行环境使用仓库既有虚拟环境：

```powershell
Set-Location D:\CodexWorkspace\Virtual-Engine
.\working\V1.3.8_dev\.venv\Scripts\python.exe -m streamlit run app\streamlit_app.py
```

### 10.1 competition

在未跟踪的本地 `app/.streamlit/secrets.toml` 中配置安全测试值：

```toml
APP_MODE = "competition"
COMPETITION_REVIEW_CODE = "<本地测试体验码>"
COMPETITION_ADMIN_CODE = "<不同的本地测试管理码>"
AUTH_CONTEXT_SIGNING_KEY = "<至少32字符的本地随机测试值>"
PEDSIM_COMPETITION_RESULTS_DIR = "<competition专用本地目录>"
```

启动后应看到比赛评审入口；分别验证体验码和只读管理码。不要配置正式 Supabase。

### 10.2 production

将同一未跟踪本地 Secrets 的 `APP_MODE` 改为 `production`，并配置互不相同的本地测试
`APP_ACCESS_CODE`、`ADMIN_PASSWORD` 和至少32字符的本地随机签名密钥；保持 Supabase
未配置。重启 Streamlit 后应看到正式访问码入口及临床/学院模式选择，不得出现评审文案。

Secrets 的值优先于环境变量；如本地 Secrets 已设置 `APP_MODE`，单独修改
`$env:APP_MODE` 不会覆盖它。`app/.streamlit/secrets.toml` 不得加入 Git。
