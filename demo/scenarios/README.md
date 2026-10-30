# 稳定合成演示场景

本目录中的公司名称、单据号、邮箱地址和金额均为合成数据，不对应真实客户或交易。

## 更新已有账单

将 `update-request.eml` 作为业务材料上传，将 `existing-bills-update.json` 作为已有账单上传，并把当前记账主体设置为 `Northstar Logistics Demo Ltd.`。预期结果是根据邮件中的明确新值，将海运费从 USD 180.00 更新为 USD 200.00。

## 安全待复核

上传 `pending-review.eml`。邮件明确给出了金额，但故意缺少账单双方和记账方向，因此安全结果应为 `PENDING_REVIEW`。

创建新费用时，可继续使用 `tests/fixtures/documents` 下的合成 PDF、图片和 EML 样本。
