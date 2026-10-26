# Source layout

核心实现采用 DDD 与六边形架构。依赖方向为：适配器依赖应用层，应用层依赖领域层；领域层不依赖任何框架或外部服务。

- `domain/billing` 保存纯业务模型和规则；
- `application/dto` 保存跨解析器的技术文档模型；
- `application/use_cases` 编排流程；
- `adapters/outbound` 实现文件解析、OCR、七牛临时存储和 LiteLLM 边界；
- `bootstrap` 负责配置与装配。
- Streamlit 演示页直接调用应用用例，不额外保留未使用的 CLI 适配器。
