# Test fixtures

`documents` 保存完全合成的 EML、PDF 和图片示例，仅用于解析集成测试和本地演示。所有企业、联系人、邮箱、单据号、运输标识及金额均为虚构数据，不对应真实客户或交易。

测试不会把这些文件发送到外部服务。PDF、图片和 EML 内的 PDF 附件通过 OCR 测试替身处理，因此运行测试不需要 API Key、网络访问或公网文件地址。

运行 `uv run python tests/fixtures/generate_synthetic_documents.py` 可以重新生成全部样本。生成器依赖 `--all-extras` 安装的 Pillow。
