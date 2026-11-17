# -*- coding: utf-8 -*-
"""中文维基百科词条抓取。

wikipedia-api 新版要求必须传 user_agent，否则直接报错。
"""

import wikipediaapi

USER_AGENT = (
    "KB-QA-v2/2.0 (https://github.com/qfds/Azure-OpenAI-LangChain-Chroma-KB)"
)


def fetch_wiki_entry(title: str, language: str = "zh") -> str | None:
    """抓取指定词条的正文；词条不存在或正文为空返回 None。

    抛出异常时由调用方处理（网络、被墙、限流等），这里不吞异常。
    """
    wiki = wikipediaapi.Wikipedia(user_agent=USER_AGENT, language=language)
    page = wiki.page(title)
    if not page.exists:
        return None
    text = (page.text or "").strip()
    if not text:
        return None
    return text
