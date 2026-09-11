# -*- coding: utf-8 -*-
"""
conftest.py —— 全局公共 fixture（所有 test_*.py 复用，避免重复公共逻辑）
========================================================================
集中管理：环境变量读取、OpenAI 兼容客户端、各评测框架的依赖守卫、裁判模型配置。
各用例脚本只需 `def test_xxx(openai_api_client):` 之类声明依赖即可。

环境约定（所有脚本共用）
------------------------
EVAL_API_BASE_URL   被测 OpenAI 兼容端点（含 /v1），能力评测 API 模式必填
EVAL_API_KEY        被测端点密钥
EVAL_MODEL          被测模型名
EVAL_ACC_THRESHOLD  能力准确率门禁（默认 0.5）
EVAL_STRICT         1=硬断言门禁（默认）；0=仅记录不阻断（演示/摸底）
EVAL_USE_HARNESS    1=走 lm-evaluation-harness 跑 MMLU+CMMLU
OPENAI_API_KEY      裁判模型密钥（RAGAS/DeepEval/LLM-Judge 共用）
OPENAI_BASE_URL     裁判模型端点（默认官方 /v1）
JUDGE_MODEL         裁判模型名（默认 gpt-4o-mini）
AGENT_STOCHASTIC_N  Agent stochastic 重跑次数（默认 5）
AGENT_PASS_RATE     Agent 通过率门禁（默认 0.8）
"""
import os
import types

import pytest


@pytest.fixture(scope="session")
def eval_env():
    """集中读取公共环境变量与默认值，避免每个脚本各写一遍 os.getenv。"""
    return {
        "api_base_url": os.getenv("EVAL_API_BASE_URL"),
        "api_key": os.getenv("EVAL_API_KEY"),
        "model": os.getenv("EVAL_MODEL", "demo-model"),
        "use_harness": os.getenv("EVAL_USE_HARNESS") == "1",
        "strict": os.getenv("EVAL_STRICT", "1") == "1",
        "acc_threshold": float(os.getenv("EVAL_ACC_THRESHOLD", "0.5")),
        "judge_model": os.getenv("JUDGE_MODEL", "gpt-4o-mini"),
        "openai_base_url": os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        "openai_api_key": os.getenv("OPENAI_API_KEY"),
        "stochastic_n": int(os.getenv("AGENT_STOCHASTIC_N", "5")),
        "pass_rate": float(os.getenv("AGENT_PASS_RATE", "0.8")),
    }


@pytest.fixture
def openai_api_client(eval_env):
    """被测模型的 OpenAI 兼容客户端；未配置端点则 skip（黑盒 API 评测前提）。"""
    base = eval_env["api_base_url"]
    key = eval_env["api_key"]
    if not base or not key:
        pytest.skip("未配置 EVAL_API_BASE_URL / EVAL_API_KEY，跳过 API 模式评测")
    try:
        from openai import OpenAI
    except Exception:  # pragma: no cover
        pytest.skip("未安装 openai 客户端（pip install openai）")
    return OpenAI(base_url=base, api_key=key)


@pytest.fixture
def judge_config(eval_env):
    """裁判模型配置；未配置 OPENAI_API_KEY 则 skip（LLM-Judge / RAGAS / DeepEval 共用前提）。"""
    if not eval_env["openai_api_key"]:
        pytest.skip("未配置 OPENAI_API_KEY，跳过依赖裁判模型的评测")
    return eval_env


@pytest.fixture
def ragas_modules():
    """按需导入 RAGAS 技术栈；未安装则 skip。兼容 v0.3-（evaluate+LangchainLLMWrapper）与 v0.4+（llm_factory+metrics.collections）。"""
    try:
        import ragas
        from importlib.metadata import version as _ragas_ver
        _v = _ragas_ver("ragas")
        _mm = tuple(int(x) for x in _v.split(".")[:2] if x.isdigit())
        is_v4 = (_mm >= (0, 4))  # 0.4.x / 1.x 均按新 API
    except Exception:  # pragma: no cover
        pytest.skip("未安装 ragas，跳过 RAG 评测")
    try:
        from langchain_openai import ChatOpenAI, OpenAIEmbeddings
        from ragas.dataset_schema import SingleTurnSample
    except Exception:  # pragma: no cover
        pytest.skip("未安装 langchain-openai/datasets，跳过 RAG 评测")
    ns = {"is_v4": is_v4, "ChatOpenAI": ChatOpenAI, "OpenAIEmbeddings": OpenAIEmbeddings,
          "SingleTurnSample": SingleTurnSample}
    if is_v4:
        try:
            from ragas.llms.base import llm_factory
            from ragas.metrics.collections import (Faithfulness, AnswerRelevancy,
                                                   ContextPrecision, ContextRecall)
            from ragas.embeddings.base import embedding_factory
        except Exception as e:  # pragma: no cover
            pytest.skip(f"ragas v0.4 关键模块不可用：{e}")
        ns.update(llm_factory=llm_factory, embedding_factory=embedding_factory,
                  Faithfulness=Faithfulness, AnswerRelevancy=AnswerRelevancy,
                  ContextPrecision=ContextPrecision, ContextRecall=ContextRecall)
    else:
        try:
            from ragas import EvaluationDataset, evaluate
            from ragas.embeddings import LangchainEmbeddingsWrapper
            from ragas.llms import LangchainLLMWrapper
            from ragas.metrics import (AnswerRelevancy, ContextPrecision, ContextRecall,
                                       Faithfulness)
        except Exception:  # pragma: no cover
            pytest.skip("未安装 ragas 旧版组件，跳过 RAG 评测")
        ns.update(EvaluationDataset=EvaluationDataset, evaluate=evaluate,
                  LangchainEmbeddingsWrapper=LangchainEmbeddingsWrapper,
                  LangchainLLMWrapper=LangchainLLMWrapper,
                  AnswerRelevancy=AnswerRelevancy, ContextPrecision=ContextPrecision,
                  ContextRecall=ContextRecall, Faithfulness=Faithfulness)
    return types.SimpleNamespace(**ns)


@pytest.fixture
def deepeval_modules():
    """按需导入 DeepEval 栈；未安装则 skip。统一收敛 test_03 / test_04 的 import 守卫。"""
    try:
        from deepeval import assert_test
        from deepeval.metrics import (AnswerRelevancyMetric, FaithfulnessMetric,
                                       GEval, ToxicityMetric)
        from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    except Exception:  # pragma: no cover
        pytest.skip("未安装 deepeval，跳过依赖它的评测")
    return types.SimpleNamespace(
        assert_test=assert_test,
        AnswerRelevancyMetric=AnswerRelevancyMetric,
        FaithfulnessMetric=FaithfulnessMetric,
        GEval=GEval, ToxicityMetric=ToxicityMetric,
        LLMTestCase=LLMTestCase, LLMTestCaseParams=LLMTestCaseParams,
    )
