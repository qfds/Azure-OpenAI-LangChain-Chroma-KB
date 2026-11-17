# -*- coding: utf-8 -*-
"""按中文句子切块：把长文本切成 ~chunk_size 字、带 overlap 的段。

切分单位是句子（。！？；或换行结尾），保证每一段都是完整句子的拼接，
避免在句中切断。下一段开头会带上上一段末尾的若干句子（overlap），
让跨段的表述在检索时不断链。
"""

import re

_SENTENCE_RE = re.compile(r"[^。！？；\n]+[。！？；\n]?")
_WHITESPACE_RE = re.compile(r"[ \t\r]+")

# 需要保留进 ids 的来源名先做一次规范化：空白折叠、去首尾空格
def normalize_source_name(name: str) -> str:
    return _WHITESPACE_RE.sub(" ", name).strip()


def split_sentences(text: str) -> list:
    """把文本按句子切开；没有句末标点的长段整体作为一句。"""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    sentences = [s for s in _SENTENCE_RE.findall(text) if s.strip()]
    if not sentences and text.strip():
        sentences = [text.strip()]
    return sentences


def split_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list:
    """返回切好的段列表（每段为字符串）。"""
    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks = []
    current = ""
    for sentence in sentences:
        if len(current) + len(sentence) <= chunk_size:
            current += sentence
        else:
            if current:
                chunks.append(current)
            # 超长单句本身超过 chunk_size：硬切，避免无限循环
            while len(sentence) > chunk_size:
                chunks.append(sentence[:chunk_size])
                sentence = sentence[chunk_size:]
            current = sentence
    if current:
        chunks.append(current)

    if overlap <= 0 or len(chunks) <= 1:
        return chunks

    # 带 overlap 的版本：每一段开头带上上一段末尾 <= overlap 字的句子
    overlapped = [chunks[0]]
    for chunk in chunks[1:]:
        prev = overlapped[-1]
        tail = ""
        # 从上一段尾部按句取，累计不超过 overlap 字
        for s in reversed(split_sentences(prev)):
            if len(tail) + len(s) <= overlap:
                tail = s + tail
            else:
                break
        overlapped.append(tail + chunk if tail else chunk)
    return overlapped
