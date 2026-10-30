# Generic Demo and Deployment Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将参赛仓库中的通用演示增强、合成场景、公开部署能力、架构说明和测试选择性同步到原始仓库，同时排除全部赛事和 Nebius 专属内容。

**Architecture:** 保持现有领域层、应用用例和适配器不变，在 `application.presentation` 中加入无 Streamlit 依赖的纯展示辅助函数，由中文 Streamlit 页面调用。容器和 Streamlit 配置作为供应商中立的部署边界，README 只描述通用架构与运行方式。

**Tech Stack:** Python 3.12、Streamlit、Pydantic、pytest、Ruff、Mypy、uv、Docker

**Spec:** `docs/superpowers/specs/2026-10-30-generic-demo-deployment-sync-design.md`

## Global Constraints

- 保留原项目中文产品定位和 `.env.example` 中现有 DeepSeek/LiteLLM 配置。
- 不加入 Hackathon、Devpost、目标赛道、评委、比赛提交、Nebius、Token Factory 或 NVIDIA 指定模型内容。
- 不修改账单抽取、证据校验、匹配、AR/AP 和操作决策逻辑。
- 演示场景只能使用合成数据；部署文件不得内置密钥。
- 上传限制固定为最多 8 个文件、单文件 10 MB、合计 25 MB。
- 声明式 Docker、TOML 和文档改动按已批准设计不执行行为 TDD，但必须接受静态检查和可用环境中的实际构建验证。

## Review Focus

- 恰好 8 个文件应允许，9 个文件应拒绝：Task 1 的计数边界测试覆盖。
- 恰好 10 MB 的单文件应允许，超过 1 字节应拒绝：Task 1 的单文件边界测试覆盖。
- 恰好 25 MB 的合计上传应允许，超过 1 字节应拒绝：Task 1 的合计边界测试覆盖。
- 空结果和缺失可选字段不得导致指标或表格转换异常：Task 1 的空值测试覆盖。
- 合成已有账单必须符合当前 `ExistingBillInput` 模型且不含赛事或厂商名称：Task 2 的场景验证测试覆盖。

---

### Task 1: Add provider-neutral presentation helpers

**Files:**
- Create: `tests/unit/demo/test_presentation.py`
- Create: `src/application/presentation.py`
- Create: `demo/presentation.py`

**Interfaces:**
- Consumes: `application.errors.UserInputError` and the existing stable output dictionaries produced by `records_to_json_data`.
- Produces: `validate_uploads(files: Sequence[UploadedFile]) -> None`, `summarize_results(output: list[dict[str, Any]]) -> ResultSummary`, and `build_result_rows(output: list[dict[str, Any]]) -> list[dict[str, str]]`.

- [ ] **Step 1: Read `superpowers:test-driven-development/writing-good-tests.md` and add failing behavior tests**

  Add tests named:

  - `test_validate_uploads_accepts_exact_limits`
  - `test_validate_uploads_rejects_too_many_files`
  - `test_validate_uploads_rejects_oversized_file`
  - `test_validate_uploads_rejects_oversized_request`
  - `test_summarize_results_handles_decisions_and_empty_output`
  - `test_build_result_rows_formats_amounts_and_missing_values`

  Assertions must pin the 8/10 MB/25 MB limits, Chinese-safe `UserInputError` behavior, automatic versus pending counts, currency sorting, `USD 120.00`, and `—` for missing values.

- [ ] **Step 2: Run the new tests and verify RED**

  Run: `uv run pytest tests/unit/demo/test_presentation.py -q`

  Expected: collection fails because `application.presentation` does not exist.

- [ ] **Step 3: Implement the minimal pure helpers**

  Create `src/application/presentation.py` with the exact public interfaces above and constants `MAX_FILE_COUNT`, `MAX_FILE_SIZE_BYTES`, and `MAX_TOTAL_SIZE_BYTES`. Error messages must be general product messages, not public-demo, judge, competition, or provider language.

- [ ] **Step 4: Add the compatibility import module**

  Create `demo/presentation.py` that re-exports the presentation constants, protocol, dataclass, and functions without duplicating implementation.

- [ ] **Step 5: Run focused tests and verify GREEN**

  Run: `uv run pytest tests/unit/demo/test_presentation.py -q`

  Expected: all presentation tests pass.

- [ ] **Step 6: Commit Task 1**

  ```bash
  git add src/application/presentation.py demo/presentation.py tests/unit/demo/test_presentation.py
  git commit -m "feat: add reusable demo presentation helpers"
  ```

### Task 2: Enhance the Chinese demo and add synthetic scenarios

**Files:**
- Modify: `tests/unit/demo/test_presentation.py`
- Modify: `demo/app.py`
- Create: `demo/scenarios/README.md`
- Create: `demo/scenarios/existing-bills-update.json`
- Create: `demo/scenarios/update-request.eml`
- Create: `demo/scenarios/pending-review.eml`

**Interfaces:**
- Consumes: Task 1 presentation functions and existing `ExistingBillInput` validation.
- Produces: downloadable synthetic CREATE/UPDATE/PENDING_REVIEW inputs and a Chinese UI showing metrics, table, evidence trail, raw JSON, and upload validation.

- [ ] **Step 1: Add failing scenario validation tests**

  Add `test_update_scenario_contains_a_valid_existing_bill` and `test_demo_scenarios_are_provider_and_competition_neutral`. The first must validate the JSON through `ExistingBillInput`; the second must scan the four scenario files for forbidden case-insensitive terms `hackathon`, `devpost`, `nebius`, `token factory`, and `nvidia`.

- [ ] **Step 2: Run scenario tests and verify RED**

  Run: `uv run pytest tests/unit/demo/test_presentation.py -q`

  Expected: failure because `demo/scenarios` files do not exist.

- [ ] **Step 3: Create the synthetic scenario files**

  Use fictional companies, identifiers, addresses and amounts. The README must explain how to demonstrate new-charge creation, explicit update and safe pending review without mentioning a competition or provider.

- [ ] **Step 4: Run scenario tests and verify GREEN**

  Run: `uv run pytest tests/unit/demo/test_presentation.py -q`

  Expected: all tests pass.

- [ ] **Step 5: Enhance `demo/app.py`**

  Preserve Chinese page identity and existing safe error handling. Add a generic safety-workflow expander, synthetic sample downloads, upload validation before external calls, summary metrics, flattened result table, evidence/decision expanders, raw JSON expander and JSON download. Do not introduce provider or competition text.

- [ ] **Step 6: Run focused tests plus import/type checks**

  Run: `uv run pytest tests/unit/demo/test_presentation.py -q`

  Run: `uv run ruff check demo/app.py demo/presentation.py src/application/presentation.py tests/unit/demo/test_presentation.py`

  Run: `uv run mypy`

  Expected: all commands exit 0.

- [ ] **Step 7: Commit Task 2**

  ```bash
  git add demo/app.py demo/scenarios tests/unit/demo/test_presentation.py
  git commit -m "feat: enhance the synthetic reconciliation demo"
  ```

### Task 3: Add provider-neutral container deployment

**Files:**
- Create: `Dockerfile`
- Create: `.dockerignore`
- Create: `.streamlit/config.toml`

**Interfaces:**
- Consumes: `pyproject.toml`, `uv.lock`, `src`, `demo`, and synthetic fixture files.
- Produces: a Python 3.12 container listening on port 8501 with a Streamlit health check and hardened public runtime defaults.

- [ ] **Step 1: Add deployment files**

  Pin uv to the version used by CI, install only demo runtime dependencies, copy only runtime-required sources and synthetic sample assets, expose port 8501, and use `/_stcore/health` for the health check. Exclude `.env`, Git metadata, caches, coverage, docs and non-runtime tests from the build context.

- [ ] **Step 2: Check configuration for forbidden content and secrets**

  Run: `rg -n -i "hackathon|devpost|nebius|token factory|nvidia|litellm_api_key\s*=.+" Dockerfile .dockerignore .streamlit`

  Expected: no matches.

- [ ] **Step 3: Build the image when Docker is available**

  Run: `docker build -t shipping-billing-assistant .`

  Expected: exit 0. If the Docker CLI or daemon is unavailable, record this exact limitation and continue with the remaining repository verification without claiming the image was built.

- [ ] **Step 4: Commit Task 3**

  ```bash
  git add Dockerfile .dockerignore .streamlit/config.toml
  git commit -m "build: add containerized demo deployment"
  ```

### Task 4: Document the generic architecture and run paths

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the existing application architecture and Tasks 1–3 runtime behavior.
- Produces: provider-neutral architecture, enhanced demo, upload limit, Docker, and public deployment guidance.

- [ ] **Step 1: Add the generic Mermaid architecture diagram**

  Show documents flowing through parsers/OCR, provider-neutral LiteLLM extraction, evidence and financial validation, bill matching, and the four decisions. Do not name a model vendor or event.

- [ ] **Step 2: Add enhanced demo and Docker instructions**

  Document the metrics/table/evidence UI, synthetic sample downloads, 8-file/10 MB/25 MB limits, `docker build`, and `docker run --env-file .env`. Include a security note that public deployments must use server-side credentials, quotas and synthetic examples.

- [ ] **Step 3: Verify README exclusions and links**

  Run: `rg -n -i "hackathon|devpost|nebius|token factory|nvidia" README.md demo src/application/presentation.py tests/unit/demo/test_presentation.py Dockerfile .streamlit`

  Expected: no matches.

- [ ] **Step 4: Commit Task 4**

  ```bash
  git add README.md
  git commit -m "docs: add generic architecture and deployment guide"
  ```

### Task 5: Full verification and scope audit

**Files:**
- Verify all changed files; modify only if a verification failure identifies an in-scope defect.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: evidence that the original repository remains provider-neutral and its complete quality gate passes.

- [ ] **Step 1: Audit the final diff and protected files**

  Run: `git diff origin/main -- . ':!docs/superpowers'`

  Run: `git diff --exit-code origin/main -- .env.example src/domain src/adapters src/application/services src/application/use_cases`

  Expected: the first diff contains only planned generic changes; the second command exits 0.

- [ ] **Step 2: Run formatting and lint checks**

  Run: `uv run ruff format --check .`

  Run: `uv run ruff check .`

  Expected: both exit 0.

- [ ] **Step 3: Run type checking**

  Run: `uv run mypy`

  Expected: exit 0 with no issues.

- [ ] **Step 4: Run the complete test suite**

  Run: `uv run pytest`

  Expected: exit 0 and coverage at or above 80%.

- [ ] **Step 5: Audit all changed content for forbidden competition/vendor terms and secrets**

  Run: `git diff --name-only origin/main` and scan every returned product/config/document file with `rg -n -i "hackathon|devpost|nebius|token factory|nvidia|api[_-]?key\s*[:=]\s*[^<\s]"`.

  Expected: no unintended match; the generic design/plan documents may name excluded terms only to state the exclusion policy.

- [ ] **Step 6: Record final repository status**

  Run: `git status --short --branch`

  Expected: only the planned commits differ from `origin/main`, with no uncommitted product changes.
