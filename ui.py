# -*- coding: utf-8 -*-
"""CustomTkinter 界面（浅色主题，1080x660）。

布局与设计图一致：蓝色顶栏、左侧知识学习栏、右侧对话区、
底部输入 + 发送 + 语音问答 + 朗读开关、状态栏。
学习/问答/语音都在后台线程跑，界面不卡住；报错显示具体原因。
"""

import os
import re
import threading
import tkinter as tk
from tkinter import filedialog

import customtkinter as ctk

try:
    import opencc
    t2s = opencc.OpenCC("t2s")
except Exception:
    # OpenCC 的编译组件（opencc_clib）在 PyInstaller 打包时容易漏掉，
    # 缺失时退化为不做繁转简，程序仍能正常运行。
    opencc = None

    class _IdentityConverter:
        def convert(self, text):
            return text

    t2s = _IdentityConverter()

import config_manager as cm
from chunker import normalize_source_name, split_text
from gemini_client import GeminiClient
from kb_store import KBStore
from wiki_client import fetch_wiki_entry
import voice as voice_mod

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")

UNKNOWN_ANSWER = "知识库中没有找到相关内容，我不知道。"


class SettingsDialog(ctk.CTkToplevel):
    """首次运行 / 设置：填 Gemini key 与模型参数，存本地 config.ini。"""

    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.parent = parent
        self.cfg = cfg
        self.title("设置")
        self.geometry("480x720")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        ctk.CTkLabel(self, text="首次运行需要填写 Gemini API key",
                     font=("微软雅黑", 13, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        ctk.CTkLabel(self, text="key 只保存在本机 config.ini，不会上传或提交到仓库。",
                     font=("微软雅黑", 11), text_color="gray").pack(anchor="w", padx=16, pady=(0, 10))

        self.entries = {}

        def add_field(label, section, key, show=None):
            ctk.CTkLabel(self, text=label, font=("微软雅黑", 11)).pack(anchor="w", padx=16)
            e = ctk.CTkEntry(self, font=("微软雅黑", 11), height=32, show=show)
            e.insert(0, cm.get_str(self.cfg, section, key))
            e.pack(fill="x", padx=16, pady=(2, 8))
            self.entries[(section, key)] = e

        add_field("Gemini API key", "Gemini", "GEMINI_API_KEY", show="•")
        add_field("问答模型", "Gemini", "GEMINI_MODEL")
        add_field("向量模型", "Gemini", "GEMINI_EMBED_MODEL")
        add_field("语音合成模型", "Gemini", "GEMINI_TTS_MODEL")
        add_field("朗读声音", "Gemini", "GEMINI_TTS_VOICE")
        add_field("每次取回段数 (TOP_K)", "Knowledge", "TOP_K")
        add_field("相似度阈值（余弦距离，越小越严）", "Knowledge", "DISTANCE_THRESHOLD")

        self.err = ctk.CTkLabel(self, text="", font=("微软雅黑", 11), text_color="#C0392B")
        self.err.pack(anchor="w", padx=16)
        ctk.CTkButton(self, text="保存", height=36, font=("微软雅黑", 12, "bold"),
                      command=self._save).pack(fill="x", padx=16, pady=12)

    def _save(self):
        key = self.entries[("Gemini", "GEMINI_API_KEY")].get().strip()
        if not key:
            self.err.configure(text="请先填写 Gemini API key")
            return
        for (section, k), entry in self.entries.items():
            self.cfg[section][k] = entry.get().strip()
        cm.save_config(self.cfg)
        self.parent.after(0, self.parent.init_backend)
        self.destroy()


class KBApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("本地知识库问答 v2.0")
        self.geometry("1080x660")
        self.resizable(False, False)

        self.cfg = cm.load_config()
        self.gemini = None
        self.kb = None
        self.history = []          # [(role, text)]，role: user/assistant
        self.last_answer = ""      # 最近一次 AI 回答（供手动“朗读”用）
        self._rec_stop = None      # 按住录音的停止信号（threading.Event）
        self.busy = False
        self.read_var = ctk.BooleanVar(value=False)

        self._build_ui()
        self.after(300, self.init_backend)

    # ---------- 界面 ----------
    def _build_ui(self):
        top = ctk.CTkFrame(self, height=52, corner_radius=0, fg_color="#1F6AA5")
        top.pack(fill="x")
        ctk.CTkLabel(top, text="本地知识库问答  v2.0", font=("微软雅黑", 16, "bold"),
                     text_color="white").pack(side="left", padx=16)
        self.model_pill = ctk.CTkLabel(top, text="", font=("微软雅黑", 11),
                                       text_color="white", fg_color="#2B7CB8", corner_radius=12)
        self.model_pill.pack(side="right", padx=8, pady=12)
        ctk.CTkButton(top, text="设置", width=64, height=28, fg_color="#2B7CB8",
                      hover_color="#3590CF", font=("微软雅黑", 11),
                      command=self._open_settings).pack(side="right", padx=4, pady=12)

        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True)

        # 左侧：知识学习
        left = ctk.CTkFrame(main, width=300, corner_radius=10)
        left.pack(side="left", fill="y", padx=12, pady=12)
        left.pack_propagate(False)

        ctk.CTkLabel(left, text="知识学习", font=("微软雅黑", 13, "bold")).pack(
            anchor="w", padx=14, pady=(12, 6))
        ctk.CTkLabel(left, text="输入维基词条进行学习", font=("微软雅黑", 11),
                     text_color="gray").pack(anchor="w", padx=14)
        self.wiki_entry = ctk.CTkEntry(left, placeholder_text="例如：海豹科",
                                       font=("微软雅黑", 11), height=34)
        self.wiki_entry.pack(fill="x", padx=14, pady=6)
        self.learn_btn = ctk.CTkButton(left, text="学习词条", height=34,
                                       font=("微软雅黑", 11, "bold"),
                                       command=self._on_learn_wiki)
        self.learn_btn.pack(fill="x", padx=14, pady=(0, 8))
        self.upload_btn = ctk.CTkButton(left, text="上传本地 TXT 文件", height=34,
                                        fg_color="#DEDEDE", text_color="#333333",
                                        hover_color="#CFCFCF", font=("微软雅黑", 11),
                                        command=self._on_upload_txt)
        self.upload_btn.pack(fill="x", padx=14, pady=(0, 10))

        ctk.CTkLabel(left, text="已学词条", font=("微软雅黑", 13, "bold")).pack(
            anchor="w", padx=14, pady=(6, 4))
        self.source_list = ctk.CTkScrollableFrame(left, fg_color="transparent", height=220)
        self.source_list.pack(fill="x", padx=6, pady=2)
        self.kb_info = ctk.CTkLabel(left, text="向量库：0 段", font=("微软雅黑", 11),
                                    text_color="gray")
        self.kb_info.pack(anchor="w", padx=14, pady=(10, 0))

        # 右侧：问答
        right = ctk.CTkFrame(main, corner_radius=10)
        right.pack(side="left", fill="both", expand=True, padx=(0, 12), pady=12)

        self.chat = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self.chat.pack(fill="both", expand=True, padx=10, pady=10)

        bottom = ctk.CTkFrame(right, fg_color="transparent")
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        self.q_entry = ctk.CTkEntry(bottom, placeholder_text="输入问题，例如：海豹吃什么？",
                                    font=("微软雅黑", 12), height=38)
        self.q_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.q_entry.bind("<Return>", lambda _e: self._on_ask())
        self.ask_btn = ctk.CTkButton(bottom, text="发送", width=70, height=38,
                                     font=("微软雅黑", 12, "bold"), command=self._on_ask)
        self.ask_btn.pack(side="left", padx=(0, 8))
        self.voice_btn = ctk.CTkButton(bottom, text="语音问答", width=90, height=38,
                                       fg_color="#C0392B", hover_color="#D84A35",
                                       font=("微软雅黑", 12))
        self.voice_btn.pack(side="left")
        # 按住说话：按下开始录音，松开停止。CTkButton.bind 已重写为
        # 绑在内部 canvas / 文字标签上，一次调用就覆盖全部可点区域。
        self.voice_btn.bind("<ButtonPress-1>", self._on_voice_press, add=True)
        self.voice_btn.bind("<ButtonRelease-1>", self._on_voice_release, add=True)
        self.read_btn = ctk.CTkButton(bottom, text="朗读", width=64, height=38,
                                      fg_color="#2B7CB8", hover_color="#3590CF",
                                      font=("微软雅黑", 12), command=self._on_read_aloud)
        self.read_btn.pack(side="left", padx=(8, 0))
        ctk.CTkLabel(bottom, text="朗读回答", font=("微软雅黑", 11)).pack(side="left", padx=(10, 2))
        ctk.CTkSwitch(bottom, text="", variable=self.read_var, width=40).pack(side="left")

        status = ctk.CTkFrame(self, height=26, corner_radius=0, fg_color="#E8E8E8")
        status.pack(fill="x", side="bottom")
        self.status_label = ctk.CTkLabel(status, text="正在启动…",
                                         font=("微软雅黑", 10), text_color="#666666")
        self.status_label.pack(side="left", padx=12)

    # ---------- 后端初始化 ----------
    def init_backend(self):
        key = cm.get_api_key(self.cfg)
        if not key:
            self.set_status("未配置 API key，请在设置里填写 Gemini API key")
            self._open_settings()
            return
        try:
            self.gemini = GeminiClient(
                api_key=key,
                chat_model=cm.get_str(self.cfg, "Gemini", "GEMINI_MODEL"),
                embed_model=cm.get_str(self.cfg, "Gemini", "GEMINI_EMBED_MODEL"),
                tts_model=cm.get_str(self.cfg, "Gemini", "GEMINI_TTS_MODEL"),
                tts_voice=cm.get_str(self.cfg, "Gemini", "GEMINI_TTS_VOICE"),
            )
            db_dir = os.path.join(cm.app_dir(), "vs")
            self.kb = KBStore(db_dir, self.gemini)
            self.model_pill.configure(text=self.gemini.chat_model)
            self.refresh_sources()
            note = ""
            if getattr(self.kb, "stale_backup", None):
                note = f" | 旧向量库已备份到 {self.kb.stale_backup}，请重新学习词条"
            self.set_status(f"就绪 | 模型 {self.gemini.chat_model} | "
                            f"向量库 {self.kb.count()} 段{note}")
        except Exception as exc:
            self.gemini = None
            self.kb = None
            self.set_status(f"初始化失败：{exc}")

    def _open_settings(self):
        SettingsDialog(self, self.cfg)

    # ---------- 小工具 ----------
    def set_status(self, text: str):
        self.status_label.configure(text=text)

    def _set_busy(self, busy: bool, keep_voice: bool = False):
        self.busy = busy
        state = "disabled" if busy else "normal"
        btns = (self.learn_btn, self.upload_btn, self.ask_btn)
        if not keep_voice:
            btns = btns + (self.voice_btn,)
        for btn in btns:
            btn.configure(state=state)

    def _scroll_chat_bottom(self):
        try:
            self.chat.update_idletasks()
            self.chat._parent_canvas.yview_moveto(1.0)
        except Exception:
            pass

    def add_bubble(self, text: str, who: str, source: str | None = None):
        colors = {"user": ("#EFEFEF", "gray"), "ai": ("#DCEAF6", "#1F6AA5"),
                  "system": ("#FDECEA", "#C0392B")}
        bg, title_color = colors.get(who, ("#EFEFEF", "gray"))
        title = {"user": "你", "ai": "AI 回答", "system": "系统提示"}.get(who, "")
        frame = ctk.CTkFrame(self.chat, fg_color=bg, corner_radius=10)
        frame.pack(fill="x", padx=6, pady=5)
        ctk.CTkLabel(frame, text=title, font=("微软雅黑", 10, "bold"),
                     text_color=title_color).pack(anchor="w", padx=12, pady=(8, 0))
        ctk.CTkLabel(frame, text=text, font=("微软雅黑", 12), wraplength=560,
                     justify="left").pack(anchor="w", padx=12, pady=(2, 4))
        if source:
            ctk.CTkLabel(frame, text=source, font=("微软雅黑", 10),
                         text_color="#1F6AA5", fg_color="#C4DDF2",
                         corner_radius=8).pack(anchor="w", padx=12, pady=(0, 8))
        self._scroll_chat_bottom()

    def refresh_sources(self):
        for child in self.source_list.winfo_children():
            child.destroy()
        if not self.kb:
            return
        sources = self.kb.list_sources()
        for name, n in sources:
            row = ctk.CTkFrame(self.source_list, fg_color="#EBEBEB", corner_radius=8, height=34)
            row.pack(fill="x", padx=8, pady=3)
            ctk.CTkLabel(row, text=name, font=("微软雅黑", 11)).pack(side="left", padx=10)
            ctk.CTkLabel(row, text=f"{n} 段", font=("微软雅黑", 11),
                         text_color="gray").pack(side="right", padx=10)
        total = sum(n for _, n in sources)
        self.kb_info.configure(text=f"向量库：{total} 段 · Chroma 本地存储")

    def _run_thread(self, target, *args):
        threading.Thread(target=target, args=args, daemon=True).start()

    def _need_backend(self) -> bool:
        if self.gemini is None or self.kb is None:
            self.add_bubble("请先在设置里填写 Gemini API key，再使用本功能。", "system")
            return False
        return True

    # ---------- 学习 ----------
    def _on_learn_wiki(self):
        if self.busy or not self._need_backend():
            return
        title = self.wiki_entry.get().strip()
        if not title:
            self.add_bubble("请输入内容后再操作！", "system")
            return
        self._set_busy(True)
        self.set_status(f"正在学习维基词条「{title}」…")
        self._run_thread(self._learn_wiki_worker, title)

    def _learn_wiki_worker(self, title: str):
        try:
            text = fetch_wiki_entry(title)
            if text is None:
                raise RuntimeError(f"维基百科没有找到词条「{title}」")
            self._ingest(title, text, via="维基")
            self.after(0, lambda: self.wiki_entry.delete(0, tk.END))
        except Exception as exc:
            self.after(0, lambda e=exc: (
                self.add_bubble(f"学习失败：{e}", "system"),
                self.set_status(f"学习失败：{e}"),
                self._set_busy(False),
            ))

    def _on_upload_txt(self):
        if self.busy or not self._need_backend():
            return
        path = filedialog.askopenfilename(filetypes=[("Text files", "*.txt")])
        if not path:
            return
        self._set_busy(True)
        self._run_thread(self._upload_worker, path)

    def _upload_worker(self, path: str):
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            if not text.strip():
                raise RuntimeError("文件是空的")
            self._ingest(name, text, via="本地")
        except Exception as exc:
            self.after(0, lambda e=exc: (
                self.add_bubble(f"上传失败：{e}", "system"),
                self.set_status(f"上传失败：{e}"),
                self._set_busy(False),
            ))

    def _ingest(self, source_name: str, text: str, via: str):
        """切块 → 入库；全程在后台线程，UI 更新用 after 回主线程。"""
        source_name = normalize_source_name(source_name)
        clean = t2s.convert(text)
        chunk_size = cm.get_int(self.cfg, "Knowledge", "CHUNK_SIZE")
        overlap = cm.get_int(self.cfg, "Knowledge", "CHUNK_OVERLAP")
        chunks = split_text(clean, chunk_size=chunk_size, overlap=overlap)
        if not chunks:
            raise RuntimeError("文本切块后为空，无法学习")
        n = self.kb.add_entry(source_name, chunks)
        self.after(0, lambda: (
            self.add_bubble(f"{via}「{source_name}」学习成功，可以开始问答啦！（{n} 段）", "ai"),
            self.refresh_sources(),
            self.set_status(f"就绪 | 模型 {self.gemini.chat_model} | 向量库 {self.kb.count()} 段"),
            self._set_busy(False),
        ))

    # ---------- 问答 ----------
    def _on_ask(self):
        if self.busy or not self._need_backend():
            return
        question = self.q_entry.get().strip()
        if not question:
            self.add_bubble("请输入内容后再操作！", "system")
            return
        self.q_entry.delete(0, tk.END)
        self._ask(question)

    def _ask(self, question: str):
        # 开关状态在主线程读（tkinter 变量不要跨线程读），再传给后台线程
        read_aloud = self.read_var.get()
        self._set_busy(True)
        self.add_bubble(question, "user")
        self.set_status("正在检索知识库…")
        self._run_thread(self._ask_worker, question, read_aloud)

    def _ask_worker(self, question: str, read_aloud: bool = False):
        try:
            top_k = cm.get_int(self.cfg, "Knowledge", "TOP_K")
            threshold = cm.get_float(self.cfg, "Knowledge", "DISTANCE_THRESHOLD")
            hits = self.kb.query(question, top_k=top_k)
            good = [h for h in hits if h["distance"] <= threshold]
            if not good:
                self.after(0, lambda: (
                    self.add_bubble(UNKNOWN_ANSWER, "ai"),
                    self.set_status("就绪：知识库中没有相关内容"),
                    self._set_busy(False),
                ))
                return
            self.after(0, lambda: self.set_status("正在生成回答…"))
            answer = self.gemini.chat(question, good, history=self.history)
            self.last_answer = answer
            self.history.append(("user", question))
            self.history.append(("assistant", answer))
            self.history = self.history[-12:]
            # 来源只在气泡下方单独显示一次（按词条合并段号），不写进正文
            grouped = {}
            for h in good:
                grouped.setdefault(h["source"], []).append(h["chunk"] + 1)
            source = "来源：" + "、".join(
                f"{name} 第 {'、'.join(str(c) for c in sorted(set(chunks)))} 段"
                for name, chunks in grouped.items()
            )
            self.after(0, lambda: (
                self.add_bubble(answer, "ai", source=source),
                self.set_status(f"就绪 | 模型 {self.gemini.chat_model} | "
                                f"向量库 {self.kb.count()} 段"),
                self._set_busy(False),
            ))
            if read_aloud:
                self._run_thread(self._speak_worker, answer)
        except Exception as exc:
            self.after(0, lambda e=exc: (
                self.add_bubble(f"问答失败：{e}", "system"),
                self.set_status(f"问答失败：{e}"),
                self._set_busy(False),
            ))

    def _speak_worker(self, text: str):
        """合成 + 播放；每一步都在状态栏报进度，失败在对话框里报清原因。

        不碰 busy 状态（调用方自己管），这样手动朗读时界面不用锁死。
        状态栏会写明本次用的输出设备名，方便定位“没声音”是设备问题
        还是合成问题。
        朗读时去掉来源标注（正文里残留的“（来源：…）”），只读回答本身，
        不然一句话没说完就插一段来源，听着断断续续。
        """
        try:
            self.after(0, lambda: self.set_status("正在合成语音…"))
            speak_text = re.sub(r"[（(]来源：[^）)]*[）)]", "", text)
            speak_text = re.sub(r"\n\s*\n+", "\n", speak_text).strip()
            pcm = self.gemini.synthesize_speech(speak_text)
            dev = voice_mod.default_output_device_name()
            dev_note = f"（输出设备：{dev}）" if dev else ""
            self.after(0, lambda: self.set_status(f"正在朗读…{dev_note}"))
            voice_mod.play_pcm(pcm)
            self.after(0, lambda: self.set_status(f"朗读完成{dev_note}"))
        except Exception as exc:
            self.after(0, lambda e=exc: (
                self.add_bubble(f"朗读失败：{e}", "system"),
                self.set_status(f"朗读失败：{e}"),
            ))

    def _on_read_aloud(self):
        """手动朗读最近一次 AI 回答（不受“朗读回答”开关影响）。"""
        if not self._need_backend():
            return
        if not self.last_answer:
            self.add_bubble("还没有可以朗读的回答，先问一个问题吧。", "system")
            return
        self._run_thread(self._speak_worker, self.last_answer)

    # ---------- 语音问答（按住说话，松开结束）----------
    def _on_voice_press(self, event=None):
        """按下语音按钮：开始录音。"""
        if self.busy or not self._need_backend():
            return
        self._rec_stop = threading.Event()
        self._set_busy(True, keep_voice=True)
        self.voice_btn.configure(text="● 录音中，松开结束")
        self.add_bubble("🎤 正在录音，请说话…\n松开按钮结束，最长 20 秒。", "system")
        self.set_status("正在录音，松开按钮结束…")
        try:
            self.voice_btn.grab_set()
        except Exception:
            pass
        self._run_thread(self._voice_worker, self._rec_stop)

    def _on_voice_release(self, event=None):
        """松开语音按钮：停止录音。"""
        if getattr(self, "_rec_stop", None) is None:
            return
        self._rec_stop.set()
        self._release_voice_grab()

    def _release_voice_grab(self):
        try:
            self.voice_btn.grab_release()
        except Exception:
            pass

    def _voice_worker(self, stop_event):
        try:
            wav = voice_mod.record_until_stop(stop_event)
            self.after(0, lambda: (
                self.voice_btn.configure(text="语音问答"),
                self.set_status("正在识别语音…"),
            ))
            text = self.gemini.transcribe_audio(wav)
            if not text:
                raise RuntimeError("没有识别到语音内容，请再试一次")
            self.after(0, lambda: self._ask(text))
        except Exception as exc:
            self.after(0, lambda e=exc: (
                self.voice_btn.configure(text="语音问答"),
                self.add_bubble(f"语音问答失败：{e}", "system"),
                self.set_status(f"语音问答失败：{e}"),
                self._set_busy(False),
            ))
        finally:
            self._rec_stop = None
            self.after(0, self._release_voice_grab)
