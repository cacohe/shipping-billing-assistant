# 合成样本评估基线

仓库包含四份完全合成的公开样本，用于验证格式调度、邮件附件递归、OCR 文件桥接及航运账单字段边界。样本中的企业、联系人、邮箱、单据号、运输标识和金额均不对应真实客户或交易。

| 样本 | 人工基线 | 主要验证点 |
|---|---|---|
| `synthetic-invoice.png` | 发票 `INV-DEMO-1001`；Harborline Carrier Demo Co. 对 Northstar Logistics Demo Ltd.；两条 USD 35.00 / 180.00，总额 215.00；COLLECT | 图片 OCR、账单号与提单号区分、两条费用逐行保留、CC 归一化 |
| `synthetic-arrival-notice.pdf` | Arrival Notice `AN-DEMO-2001`；B/L `MBL-DEMO-20261026`；On-carriage USD 245.00；PREPAID | 图像型 PDF OCR、通知号与提单号区分、PP 归一化 |
| `synthetic-debit-note.pdf` | Debit Note `DN-DEMO-3001`；Northstar 对 Bluewater；三条费用 USD 65.00 / 1,310.40 / 35.00，总额 1,410.40；费用行均为 Collect | 多费用抽取、合计校验、以记账主体和交易方判断 AR/AP |
| `synthetic-pre-alert.eml` | 邮件正文含 HBL `HBL-DEMO-20261026`、箱号和 H/C USD 50.00；两个提单附件不含定价费用 | 邮件头与正文解析、附件递归、忽略内嵌资源、避免把邮件收发人自动当作账单双方 |

## 自动化与人工评估边界

- CI 使用 OCR 和 LLM 测试替身，确定性验证解析入口、来源关系、Schema、标准化、校验和决策规则。
- 实时 OCR/LLM 输出会随供应商和模型版本变化，因此不作为普通 CI 的固定断言。
- 端到端评测应记录服务版本、模型、提示词版本、字段级期望值和允许为空字段，并将差异区分为解析、OCR、抽取和业务规则四类。
- 任何缺少原文证据的字段都不得根据常识补齐；不确定结果应输出 `null` 或 `PENDING_REVIEW`。
