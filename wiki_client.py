# -*- coding: utf-8 -*-
"""中文维基百科词条抓取：直接调 MediaWiki API。

不用 wikipedia-api：它 0.16 版内部写死 httpx.HTTPTransport()，会绕过
系统代理和环境变量代理；在需要代理才能访问维基百科的网络下直接连不上
（httpx.ConnectError SSL WRONG_VERSION_NUMBER → WikiConnectionError）。
urllib.request 默认走系统代理（Windows 上读注册表里的代理设置，
和浏览器一致），所以这里用 urllib。
"""

import json
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = (
    "KB-QA-v2/2.0 (https://github.com/qfds/Azure-OpenAI-LangChain-Chroma-KB)"
)


def fetch_wiki_entry(title: str, language: str = "zh") -> str | None:
    """抓取指定词条的正文；词条不存在或正文为空返回 None。

    网络问题抛 RuntimeError（带具体原因），由调用方显示。
    """
    params = urllib.parse.urlencode({
        "action": "query",
        "prop": "extracts",
        "explaintext": "1",
        "redirects": "1",
        "titles": title,
        "format": "json",
        "formatversion": "2",
    })
    url = f"https://{language}.wikipedia.org/w/api.php?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"维基百科请求失败（HTTP {exc.code}）") from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(
            f"无法连接维基百科：{reason}。请检查网络或代理设置，"
            "确认浏览器能打开 zh.wikipedia.org"
        ) from exc
    pages = (data.get("query") or {}).get("pages") or []
    if not pages or pages[0].get("missing"):
        return None
    text = (pages[0].get("extract") or "").strip()
    return text or None
