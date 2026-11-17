# -*- coding: utf-8 -*-
"""本地配置管理：config.ini 的读写。

优先级：环境变量 GEMINI_API_KEY > config.ini。
config.ini 只保存在程序目录本地，绝不提交进仓库（见 .gitignore）。
"""

import configparser
import os
import sys

CONFIG_FILENAME = "config.ini"

DEFAULTS = {
    "Gemini": {
        "GEMINI_API_KEY": "",
        "GEMINI_MODEL": "gemini-3.8-flash",
        "GEMINI_EMBED_MODEL": "gemini-embedding-001",
        "GEMINI_TTS_MODEL": "gemini-3.8-flash-tts",
        "GEMINI_TTS_VOICE": "Kore",
    },
    "Knowledge": {
        "CHUNK_SIZE": "1000",
        "CHUNK_OVERLAP": "200",
        "TOP_K": "3",
        "DISTANCE_THRESHOLD": "0.45",
    },
}


def app_dir() -> str:
    """程序所在目录：打包后是 exe 所在目录，开发时是源码目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def config_path() -> str:
    return os.path.join(app_dir(), CONFIG_FILENAME)


def load_config() -> configparser.ConfigParser:
    """读 config.ini；缺失或缺项时用默认值补齐（不写盘）。"""
    cfg = configparser.ConfigParser()
    for section, items in DEFAULTS.items():
        cfg[section] = dict(items)
    path = config_path()
    if os.path.exists(path):
        cfg.read(path, encoding="utf-8")
    return cfg


def save_config(cfg: configparser.ConfigParser) -> None:
    with open(config_path(), "w", encoding="utf-8") as f:
        cfg.write(f)


def get_api_key(cfg: configparser.ConfigParser) -> str:
    """环境变量优先，其次 config.ini。"""
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        return env_key
    return cfg.get("Gemini", "GEMINI_API_KEY", fallback="").strip()


def get_str(cfg: configparser.ConfigParser, section: str, key: str) -> str:
    return cfg.get(section, key, fallback=DEFAULTS[section][key])


def get_int(cfg: configparser.ConfigParser, section: str, key: str) -> int:
    try:
        return cfg.getint(section, key, fallback=int(DEFAULTS[section][key]))
    except ValueError:
        return int(DEFAULTS[section][key])


def get_float(cfg: configparser.ConfigParser, section: str, key: str) -> float:
    try:
        return cfg.getfloat(section, key, fallback=float(DEFAULTS[section][key]))
    except ValueError:
        return float(DEFAULTS[section][key])
