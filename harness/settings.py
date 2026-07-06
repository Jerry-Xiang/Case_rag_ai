# -*- coding: utf-8 -*-
"""
Harness 配置加载模块
集中管理系统配置
"""

import os
from pathlib import Path
from typing import Any, Dict

import yaml

# 加载 .env 文件（如果存在）
try:
    from dotenv import load_dotenv
    # 项目根目录的 .env 文件
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # dotenv 未安装时，跳过自动加载
    pass


class Settings:
    """配置管理类，单例模式"""

    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config()
        return cls._instance

    def _load_config(self) -> None:
        """加载配置文件"""
        config_path = Path(__file__).parent / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            self._config = yaml.safe_load(f)

        # 处理环境变量替换
        self._config = self._resolve_env_vars(self._config)

    def _resolve_env_vars(self, config: Any) -> Any:
        """递归解析配置中的环境变量"""
        if isinstance(config, dict):
            return {k: self._resolve_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._resolve_env_vars(item) for item in config]
        elif isinstance(config, str) and config.startswith('${') and config.endswith('}'):
            env_var = config[2:-1]
            return os.getenv(env_var, config)
        return config

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点号分隔的路径"""
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    @property
    def llm(self) -> Dict[str, Any]:
        """获取 LLM 配置"""
        return self._config.get('llm', {})

    @property
    def retrieval(self) -> Dict[str, Any]:
        """获取检索配置"""
        return self._config.get('retrieval', {})

    @property
    def workspace(self) -> Dict[str, Any]:
        """获取工作空间配置"""
        return self._config.get('workspace', {})

    @property
    def webui(self) -> Dict[str, Any]:
        """获取 WebUI 配置"""
        return self._config.get('webui', {})

    @property
    def elasticsearch(self) -> Dict[str, Any]:
        """获取 Elasticsearch 配置"""
        return self._config.get('elasticsearch', {})

    @property
    def mcp_tools(self) -> Dict[str, Any]:
        """获取 MCP 工具配置"""
        return self._config.get('mcp_tools', {})


# 全局配置实例
settings = Settings()
