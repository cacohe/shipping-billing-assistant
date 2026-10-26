# Test layout

- `unit`：直接镜像 `src` 下的 `domain`、`application`、`adapters` 和 `bootstrap` 目录结构。
- `integration`：按照实际集成能力或端到端业务流程划分，不要求镜像源码目录。

当前测试覆盖领域规则、输入契约、应用用例、OCR 客户端、七牛临时存储、多格式文档解析和 Streamlit 页面行为。`fixtures/documents` 保存完全合成的公开示例文件，测试会替换外部存储及 OCR 调用，不需要真实密钥或公网文件地址。运行 `uv run pytest` 执行全部测试。

