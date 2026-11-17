# -*- coding: utf-8 -*-
"""Gemini API 封装：对话、向量、语音转写、语音合成。

只用 google-genai 新 SDK（from google import genai），不用已废弃的
google-generativeai。所有网络错误都原样抛给调用方，由界面显示具体原因。
"""

from google import genai
from google.genai import types

# TTS 输出：16-bit PCM、单声道、24kHz（Gemini TTS 固定格式）
TTS_SAMPLE_RATE = 24000

SYSTEM_PROMPT = (
    "你是一个本地知识库问答助手。请只根据下面给出的知识库片段回答问题，"
    "用中文回答，简洁准确。\n"
    "如果知识库片段里没有相关内容，就直接回答“我不知道”，不要编造，"
    "也不要用自己的通用知识回答。\n"
    "回答时可以在句末注明依据，如（来源：词条名）。"
)


class GeminiClient:
    def __init__(self, api_key: str, chat_model: str = "gemini-3.8-flash",
                 embed_model: str = "gemini-embedding-001",
                 tts_model: str = "gemini-3.8-flash-tts",
                 tts_voice: str = "Kore"):
        if not api_key:
            raise ValueError("Gemini API key 为空，请先在设置里填写")
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.tts_model = tts_model
        self.tts_voice = tts_voice
        # TTS 预览模型只在 v1beta 提供，客户端固定走 v1beta
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(api_version="v1beta"),
        )

    # ---------- 向量 ----------
    def embed_texts(self, texts: list, batch_size: int = 32) -> list:
        """批量生成向量；返回与 texts 一一对应的向量列表。"""
        vectors = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            resp = self._client.models.embed_content(
                model=self.embed_model, contents=batch
            )
            for emb in resp.embeddings:
                vectors.append(list(emb.values))
        return vectors

    # ---------- 对话 ----------
    def chat(self, question: str, context_chunks: list,
             history: list | None = None) -> str:
        """context_chunks: [{"source": str, "chunk": int, "text": str}]。

        history: [(role, text), ...]，role 为 "user"/"assistant"，只取最近 3 轮。
        """
        context = "\n\n".join(
            "来源：%s 第 %d 段\n%s" % (c["source"], c["chunk"] + 1, c["text"])
            for c in context_chunks
        )
        parts = [SYSTEM_PROMPT]
        if history:
            turns = history[-6:]
            hist_text = "\n".join(
                "%s：%s" % ("用户" if role == "user" else "助手", text)
                for role, text in turns
            )
            parts.append("之前的对话\n%s" % hist_text)
        parts.append("知识库片段\n%s" % context)
        parts.append("用户问题\n%s" % question)
        prompt = "\n\n".join(parts)
        resp = self._client.models.generate_content(
            model=self.chat_model,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        return (resp.text or "").strip()

    # ---------- 语音转写 ----------
    def transcribe_audio(self, wav_bytes: bytes) -> str:
        """把 WAV 录音转写成中文文字；只返回转写结果。"""
        resp = self._client.models.generate_content(
            model=self.chat_model,
            contents=[
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
                "请把这段语音原样转写成中文文字，只输出转写结果，不要加任何解释。",
            ],
        )
        return (resp.text or "").strip()

    # ---------- 语音合成 ----------
    def synthesize_speech(self, text: str) -> bytes:
        """把文字合成为语音；返回 16-bit PCM 原始字节（24kHz 单声道）。

        注意：contents 只传要朗读的正文，不加“请朗读”之类的指令，
        否则 TTS 模型会把指令本身也读出来。
        """
        resp = self._client.models.generate_content(
            model=self.tts_model,
            contents=text,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(
                            voice_name=self.tts_voice
                        )
                    )
                ),
            ),
        )
        # 音频可能分在多个 part 里（长回答时），全部拼起来，不要只取第一个
        audio_chunks = []
        for cand in resp.candidates or []:
            content = getattr(cand, "content", None)
            for part in (getattr(content, "parts", None) or []):
                inline = getattr(part, "inline_data", None)
                if inline is None or not inline.data:
                    continue
                data = inline.data
                if isinstance(data, str):
                    import base64
                    data = base64.b64decode(data)
                audio_chunks.append(bytes(data))
        if not audio_chunks:
            raise RuntimeError("语音合成没有返回音频数据")
        return b"".join(audio_chunks)
