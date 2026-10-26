# Integration tests

集成测试按实际边界组织。`document_parsing` 验证 Excel、Word、EML、EML 附件和 OCR 文档解析，并使用 `tests/fixtures/documents` 中的合成样例；外部临时存储和 OCR 调用由测试替身代替。新增集成点时再建立对应目录。

