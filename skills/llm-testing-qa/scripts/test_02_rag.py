# -*- coding: utf-8 -*-
"""
用例 2：RAG 系统评测（检索增强生成质量）
=======================================
框架   ：RAGAS（canonical 现 github.com/vibrantlabsai/ragas，Apache-2.0，~1.1万★，业界采用最广的 RAG 评测）
指标   ：faithfulness（忠实度/幻觉检测）、answer_relevancy（答案相关性）、
        context_precision（上下文精度）、context_recall（上下文召回）
对应手册：模块 11 原缺失标配维度 - RAG（RAGAS / MTEB / RAGEval） / 模块 7 安全测试

公共依赖（来自 conftest.py）：ragas_modules / judge_config
说明
----
- 裁判模型（Judge LLM）需 OpenAI 兼容接口；本地化可用 Ollama 等价模型。
- SAMPLES 为示意样本；真实项目应替换为你们 RAG 系统的线上样本（建议 50~100 条）。
- 未安装 ragas/langchain-openai/datasets 或无 OPENAI_API_KEY 时本用例自动 skip，不阻断整体流水线。
- 版本兼容：RAGAS v0.4+（evaluate()/LangchainLLMWrapper 已废弃）用 llm_factory + metrics.collections；
  v0.3- 用旧 evaluate() + LangchainLLMWrapper。conftest 的 ragas_modules 已按版本切换。
"""
import pytest


def _build_samples(rm):
    return [
        rm.SingleTurnSample(
            user_input="RAGAS 是什么？",
            retrieved_contexts=[
                "RAGAS（Retrieval-Augmented Generation Assessment）是用于评测 RAG 系统的开源框架。"
            ],
            response="RAGAS 是一个用于评测检索增强生成（RAG）系统的开源框架。",
            reference="RAGAS 是用于评测 RAG 系统的开源框架。",
        ),
        rm.SingleTurnSample(
            user_input="忠实度（faithfulness）衡量什么？",
            retrieved_contexts=[
                "忠实度衡量答案中的论断有多少能从检索上下文中推断出来，分数越高代表幻觉越少。"
            ],
            response="忠实度衡量答案中的论断能否从检索上下文中推断出来，分数越高说明幻觉越少。",
            reference="忠实度衡量答案论断是否可由检索上下文支撑，越高幻觉越少。",
        ),
    ]


def test_rag_faithfulness_and_relevancy(ragas_modules, judge_config):
    """RAG 忠实度与相关性评测：答案须忠实于检索上下文、切题。"""
    rm = ragas_modules
    JUDGE_MODEL = judge_config["judge_model"]
    API_KEY = judge_config["openai_api_key"]
    BASE_URL = judge_config["openai_base_url"]
    SAMPLES = _build_samples(rm)

    if rm.is_v4:
        # RAGAS v0.4+：evaluate()/LangchainLLMWrapper 已废弃，改用 llm_factory + metrics.collections
        import asyncio

        from openai import AsyncOpenAI

        llm = rm.llm_factory(JUDGE_MODEL,
                            client=AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL))
        emb = rm.embedding_factory("text-embedding-3-small",
                                   client=AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL))
        metrics = [rm.Faithfulness(llm=llm, embeddings=emb),
                   rm.AnswerRelevancy(llm=llm, embeddings=emb),
                   rm.ContextPrecision(llm=llm, embeddings=emb),
                   rm.ContextRecall(llm=llm, embeddings=emb)]

        async def _score(m, s):
            return await m.ascore(user_input=s.user_input, response=s.response,
                                  retrieved_contexts=s.retrieved_contexts, reference=s.reference)

        # results 顺序：[(m0,s0),(m1,s0),(m2,s0),(m3,s0),(m0,s1),...]
        results = asyncio.run(asyncio.gather(*[_score(m, s) for m in metrics for s in SAMPLES]))
        faith = [r.value for r in results[0::4]]
        rel = [r.value for r in results[1::4]]
        assert sum(faith) / len(faith) >= 0.8, "平均忠实度低于 0.8，存在幻觉风险"
        assert sum(rel) / len(rel) >= 0.7, "平均答案相关性低于 0.7"
    else:
        # RAGAS v0.3-：旧 API
        llm = rm.LangchainLLMWrapper(
            rm.ChatOpenAI(model=JUDGE_MODEL, temperature=0,
                          openai_api_key=API_KEY, openai_api_base=BASE_URL)
        )
        embeddings = rm.LangchainEmbeddingsWrapper(
            rm.OpenAIEmbeddings(model="text-embedding-3-small",
                                openai_api_key=API_KEY, openai_api_base=BASE_URL)
        )
        dataset = rm.EvaluationDataset(samples=SAMPLES)
        result = rm.evaluate(
            dataset=dataset,
            metrics=[rm.Faithfulness(), rm.AnswerRelevancy(), rm.ContextPrecision(), rm.ContextRecall()],
            llm=llm,
            embeddings=embeddings,
        )
        df = result.to_pandas()
        assert df["faithfulness"].mean() >= 0.8, "平均忠实度低于 0.8，存在幻觉风险"
        assert df["answer_relevancy"].mean() >= 0.7, "平均答案相关性低于 0.7"
