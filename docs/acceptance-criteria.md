# 验收标准对照表

| # | 验收能力 | 当前实现 | 可核对位置 |
|---|---|---|---|
| 1 | EML 正文与附件 | 解析邮件头/正文，附件递归交给同一格式调度器 | `email_parser.py`；邮件集成测试 |
| 2 | PDF/图片 OCR | 本地文件透明上传七牛，生成短期 URL 调用配置的 OCR 服务，调用后尝试清理；清理失败记录日志且不丢弃成功结果 | `ocr_document_parser.py`、`http_client.py`、`qiniu.py` |
| 3 | Excel/Word 表格 | 解析 XLS/XLSX/XLSM 工作表和 DOCX 段落/表格；DOC 通过可选 LibreOffice 转换 | `excel_parser.py`、`word_parser.py` |
| 4 | 单据号/费用/金额/币种 | Schema 抽取，金额数字化、ISO 4217 校验、逐费用行输出、原文证据校验 | `langchain_extractor.py`、`normalization.py`、`validation.py` |
| 5 | 创建/更新 | 输出四种操作；更新只应用有逐字段原文新值、证据值与候选值一致且与已有值确实不同的 `explicit_changes` | `validation.py`、`decision.py` |
| 6 | AR/AP | 按记账主体、交易方角色和收费方向判断；信息不足时不猜测 | `determine_posting_type()` 及领域测试 |
| 7 | 重复/冲突 | 同一来源行的重复费用、多重已有账单匹配、合计异常和费用证据内 OCR 易混字符阻断自动决策；来源不同的相同费用保留并告警 | `validation.py`、`matching.py` |
| 8 | 稳定性与准确性设计 | 无效结构一次修复、空费用且原始输入存在金额候选时一次保守复核（已有唯一单据只合并费用；空信封只接受复核的唯一单据）、唯一来源 ID 与原文新值校验、LLM/OCR 超时、OCR 有限重试、友好错误、阶段日志、Mock 外部依赖和 80% 覆盖率门禁 | `langchain_extractor.py`、`validation.py`、`settings.py`、`http_client.py`、`.github/workflows/ci.yml` |
| 9 | Python + LangChain | Python 3.11+，`langchain-core` + `langchain-litellm`，模型通过 LiteLLM 可配置 | `pyproject.toml`、`bootstrap/container.py` |

## 演示建议

1. 启动 Streamlit，上传 `tests/fixtures/documents` 中任一文件。
2. 观察 `RECEIVED` 到 `COMPLETED` 的阶段事件。
3. 检查逐费用项输出、`audit_trail.ai_reasoning` 原文证据和信息不足时的 `null/PENDING_REVIEW`。
4. 上传已有账单 JSON，演示匹配、字段继承和更新保护。
5. 在终端查看解析器、OCR、LLM 和临时文件清理日志。
