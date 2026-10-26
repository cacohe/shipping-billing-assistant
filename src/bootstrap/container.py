"""Construct concrete adapters while keeping the core provider-neutral."""

import logging

from langchain_litellm import ChatLiteLLM

from adapters.outbound.llm.langchain_extractor import LangChainBillingExtractor
from adapters.outbound.ocr.http_client import HttpOcrClient
from adapters.outbound.parsers.composite import CompositeDocumentParser
from adapters.outbound.storage.qiniu import QiniuTemporaryFileStore
from application.use_cases.process_billing_documents import ProcessBillingDocuments
from bootstrap.logging_config import configure_logging
from bootstrap.settings import Settings

logger = logging.getLogger("shipping_billing_assistant.bootstrap")


def build_application(settings: Settings | None = None) -> ProcessBillingDocuments:
    runtime = settings or Settings.from_env()
    configure_logging(runtime.log_level)
    logger.info(
        "构建应用 llm_model=%s temporary_storage_configured=%s",
        runtime.llm_model,
        runtime.temporary_storage_configured,
    )
    model_options: dict[str, object] = {
        "model": runtime.llm_model,
        "temperature": 0,
        "request_timeout": runtime.llm_timeout_seconds,
    }
    if runtime.llm_api_key:
        model_options["api_key"] = runtime.llm_api_key
    if runtime.llm_api_base:
        model_options["api_base"] = runtime.llm_api_base
    model = ChatLiteLLM(**model_options)
    temporary_file_store = None
    if runtime.temporary_storage_configured:
        assert runtime.qiniu_access_key is not None
        assert runtime.qiniu_secret_key is not None
        assert runtime.qiniu_bucket is not None
        assert runtime.qiniu_domain is not None
        temporary_file_store = QiniuTemporaryFileStore(
            runtime.qiniu_access_key,
            runtime.qiniu_secret_key,
            runtime.qiniu_bucket,
            runtime.qiniu_domain,
        )
        logger.info("七牛临时存储已启用 bucket=%s", runtime.qiniu_bucket)
    else:
        logger.info("七牛临时存储未启用，PDF/图片 OCR 将不可用")
    return ProcessBillingDocuments(
        CompositeDocumentParser(
            HttpOcrClient(runtime.ocr_endpoint),
            temporary_file_store,
            runtime.temporary_url_ttl_seconds,
        ),
        LangChainBillingExtractor(model),
    )
