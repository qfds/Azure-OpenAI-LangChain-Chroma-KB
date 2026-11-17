# -*- coding: utf-8 -*-
"""录音与放音：sounddevice + numpy + 标准库 wave。

录音带静音检测：开始后最长录 20 秒，连续 2 秒静音即停。
放音：播放 Gemini TTS 返回的 16-bit PCM（24kHz 单声道）。
本模块不做网络调用；转写/合成在 gemini_client 里。
"""

import io
import threading
import wave

import numpy as np

try:
    import sounddevice as sd
except Exception:  # 无音频设备或 PortAudio 缺失时，导入也不应炸掉整个程序
    sd = None

SAMPLE_RATE = 16000          # 录音采样率（转写够用）
MAX_SECONDS = 20.0           # 单次录音最长
SILENCE_SECONDS = 2.0        # 连续静音即停（说中文时句间停顿常见，1.2 秒太容易断）
SILENCE_RMS = 0.01           # 静音阈值（RMS）
TTS_SAMPLE_RATE = 24000      # Gemini TTS 输出采样率

_play_lock = threading.Lock()


def audio_available() -> bool:
    return sd is not None


def record_until_silence() -> bytes:
    """录一段语音，返回 WAV 字节；没麦克风/没声音时抛 RuntimeError。"""
    if sd is None:
        raise RuntimeError("本机没有可用的音频设备（sounddevice 初始化失败）")
    try:
        devices = sd.query_devices()
    except Exception as exc:
        raise RuntimeError(f"无法枚举音频设备：{exc}") from exc
    if not any(d.get("max_input_channels", 0) > 0 for d in devices):
        raise RuntimeError("没有检测到麦克风输入设备")

    frames = []
    silent_chunks = 0
    chunk_seconds = 0.1
    chunk_samples = int(SAMPLE_RATE * chunk_seconds)
    max_silent_chunks = int(SILENCE_SECONDS / chunk_seconds)
    max_chunks = int(MAX_SECONDS / chunk_seconds)
    heard_voice = False

    def callback(indata, _frames, _time, status):
        nonlocal silent_chunks, heard_voice
        data = np.frombuffer(indata, dtype=np.float32).copy()
        frames.append(data)
        rms = float(np.sqrt(np.mean(data ** 2))) if data.size else 0.0
        if rms > SILENCE_RMS:
            heard_voice = True
            silent_chunks = 0
        elif heard_voice:
            silent_chunks += 1

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1,
                            dtype="float32", callback=callback,
                            blocksize=chunk_samples):
            import time
            waited = 0.0
            while waited < MAX_SECONDS:
                time.sleep(chunk_seconds)
                waited += chunk_seconds
                if heard_voice and silent_chunks >= max_silent_chunks:
                    break
                if len(frames) >= max_chunks:
                    break
    except Exception as exc:
        raise RuntimeError(f"录音失败：{exc}") from exc

    if not heard_voice or not frames:
        raise RuntimeError("没有听到声音，请靠近麦克风再试一次")
    audio = np.concatenate(frames).astype(np.float32)
    pcm16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm16.tobytes())
    return buf.getvalue()


def play_pcm(pcm_bytes: bytes, sample_rate: int = TTS_SAMPLE_RATE) -> None:
    """播放 PCM；同一时间只播一路，后到的会等前一路播完。

    播放前先确认本机有音频输出设备，否则直接报清原因（不要静默无声）。
    """
    if sd is None:
        raise RuntimeError("本机没有可用的音频设备（sounddevice 初始化失败）")
    try:
        devices = sd.query_devices()
    except Exception as exc:
        raise RuntimeError(f"无法枚举音频设备：{exc}") from exc
    if not any(d.get("max_output_channels", 0) > 0 for d in devices):
        raise RuntimeError("没有检测到音频输出设备（扬声器/耳机），请检查系统声音设置")
    data = np.array(np.frombuffer(pcm_bytes, dtype=np.int16), dtype=np.int16)
    if data.size == 0:
        raise RuntimeError("语音合成返回了空音频")
    with _play_lock:
        sd.play(data, samplerate=sample_rate)
        sd.wait()
