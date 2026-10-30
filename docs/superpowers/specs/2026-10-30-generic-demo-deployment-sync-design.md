# 通用演示与部署能力同步设计

## 意图

把参赛仓库中具有长期产品价值的改进同步回原始仓库，使原项目拥有更清晰的演示结果、受控的公开部署入口、可复用的合成演示场景和相应测试，同时保持原项目与任何赛事、云厂商或特定模型无关。

## 目标

- 保留原项目现有中文产品定位和通用 LiteLLM 配置。
- 增强 Streamlit 页面：展示处理安全流程、上传限制、汇总指标、结果表格、证据与决策轨迹、原始 JSON 和下载入口。
- 增加完全合成的创建、更新和待复核演示场景。
- 增加容器部署文件和适合公开运行的 Streamlit 安全配置。
- 在 README 中增加供应商中立的 Mermaid 架构图、增强演示说明和 Docker 运行方式。
- 用单元测试覆盖上传限制、结果汇总、表格转换和演示场景数据。

## 非目标与禁止项

- 不加入 Hackathon、Devpost、目标赛道、评委、比赛截止时间、提交清单或视频脚本。
- 不加入 Nebius、Token Factory、NVIDIA 指定模型或任何比赛专属配置。
- 不修改现有 `.env.example` 中的 DeepSeek/LiteLLM 默认配置。
- 不修改账单抽取、证据校验、匹配、AR/AP 或操作决策等核心业务规则。
- 不把原始仓库与参赛仓库建立持续同步关系。

## 采用方案

采用选择性移植：以原项目为主体，手工迁入通用能力并改写参赛版中的英文或评审导向文案。没有采用“整体复制后清理”，因为它容易遗留赛事或厂商耦合；没有采用“只同步部署基础”，因为它会遗漏演示增强和测试价值。

## 设计

### 展示层

新增 `application.presentation` 作为纯展示辅助模块，负责：

- 限制最多 8 个文件、单文件 10 MB、请求合计 25 MB；
- 汇总费用项、自动决策、待复核数量和币种；
- 将稳定 JSON 输出转换为适合表格展示的行。

`demo/app.py` 使用该模块，但保持中文标题、字段和错误提示。页面展示通用的安全处理流程，并提供完全合成的下载样本。`demo/presentation.py` 只保留兼容导出，避免外部代码依赖旧导入路径时失效。

### 合成演示场景

加入一个更新请求邮件、一份已有账单 JSON 和一个待复核邮件，并用通用说明描述 CREATE、UPDATE 和 PENDING_REVIEW 演示方式。文件不得出现赛事或真实客户信息。

### 公开部署

加入 `Dockerfile`、`.dockerignore` 和 `.streamlit/config.toml`。容器只安装运行依赖，监听 8501，提供 Streamlit 健康检查；Streamlit 禁止遥测、隐藏详细错误并保留 XSRF 防护。部署文件不内置密钥或指定云厂商。

### 文档

README 增加：

- 从输入文档到确定性决策的 Mermaid 架构图；
- 增强演示页面及上传限制说明；
- Docker 构建和运行命令；
- 公开部署时使用服务端密钥、配额和仅合成样本的安全提示。

所有描述保持通用，不出现参赛仓库、赛事或 Nebius 内容。

### 测试与验证

先加入展示层行为测试并确认因模块缺失而失败，再实现最小功能使其通过。测试覆盖正常小文件、文件数量、单文件大小、合计大小、汇总指标、表格转换和演示 JSON。

Docker、Streamlit TOML 和 README 属于声明式配置/文档，不为其编写伪行为测试；通过格式检查、类型检查、完整测试套件和可用环境中的容器构建验证。若本机没有 Docker，明确报告未执行容器构建，不把静态文件存在等同于镜像已验证。

## 预计文件范围

新增：

- `.dockerignore`
- `.streamlit/config.toml`
- `Dockerfile`
- `demo/presentation.py`
- `demo/scenarios/README.md`
- `demo/scenarios/existing-bills-update.json`
- `demo/scenarios/pending-review.eml`
- `demo/scenarios/update-request.eml`
- `src/application/presentation.py`
- `tests/unit/demo/test_presentation.py`

修改：

- `demo/app.py`
- `README.md`

明确不修改：

- `.env.example`
- 核心领域、抽取、OCR、匹配和决策代码
- GitHub Actions 工作流（现有工作流会自动运行新增测试）

## 验收标准

- 原始中文演示功能保持可用，并新增指标、表格、证据轨迹和上传限制。
- 通用合成场景可下载且已有账单 JSON 能通过现有输入模型校验。
- README 能说明架构、本地运行和容器运行，不包含赛事或 Nebius 字样。
- 仓库新增内容不包含真实凭据或真实业务数据。
- Ruff 格式检查、Ruff lint、Mypy 和完整 Pytest 套件通过；Docker 构建仅在工具可用时声明通过。
