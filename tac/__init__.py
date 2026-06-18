#!/usr/bin/env python3
"""TAC (TradingAgents-CN) 兼容层。

本包是 ``tradingagents`` 的过渡期别名,实现"双轨导入":

* 新代码推荐使用 ``from tac import xxx`` / ``from tac.xxx import yyy``
* 旧代码 ``from tradingagents import xxx`` 继续可用
* 两者暴露的子模块是同一份对象,不会出现"两份实例"的状态分裂

实现机制
----------
1. 顶层属性 (``from tac import graph``) 通过 PEP 562 ``__getattr__`` 懒加载
2. 深度属性 (``from tac.graph import trading_graph``) 通过把
   ``tradingagents.xxx`` 显式注册到 ``sys.modules['tac.xxx']`` 实现
3. 顶层模块的常见元信息 (``__version__`` 等) 显式暴露,避免对 ``__getattr__`` 的依赖
"""

from __future__ import annotations

import importlib
import sys
from typing import Any

# 显式预热原包,触发 tradingagents/__init__.py 的导入逻辑
_TRADINGAGENTS = importlib.import_module("tradingagents")


def _resolve(name: str) -> Any:
    """从 tradingagents 包解析属性,优先作为已有属性,其次作为子模块 import。"""
    if hasattr(_TRADINGAGENTS, name):
        return getattr(_TRADINGAGENTS, name)
    full_name = f"tradingagents.{name}"
    return importlib.import_module(full_name)


def __getattr__(name: str) -> Any:
    """PEP 562 懒加载:把所有未在本模块直接定义的属性转发到 tradingagents。"""
    try:
        return _resolve(name)
    except (ImportError, AttributeError) as exc:
        raise AttributeError(
            f"module 'tac' has no attribute {name!r} "
            f"(proxy to tradingagents failed: {exc})"
        ) from exc


def __dir__() -> list[str]:
    """让 dir(tac) 与 dir(tradingagents) 保持一致,便于 IDE 自动补全。"""
    return dir(_TRADINGAGENTS)


# 显式暴露常用元信息
__version__ = getattr(_TRADINGAGENTS, "__version__", "1.0.0-preview")
__author__ = getattr(_TRADINGAGENTS, "__author__", "TradingAgents-CN Team")
__description__ = getattr(
    _TRADINGAGENTS,
    "__description__",
    "Multi-agent stock analysis system for Chinese markets",
)

# 把 tradingagents 的所有顶层子模块都注册成 tac 的子模块,
# 这样 ``from tac.graph import trading_graph`` 这种深度导入也能工作。
# 这一步是"事前尽力而为":对没有额外依赖的子模块会立即加载,
# 有依赖缺失的子模块会跳过,后续真正使用时会通过 __getattr__ 重试。
for _name in (
    "agents",
    "api",
    "config",
    "constants",
    "dataflows",
    "default_config",
    "graph",
    "llm_adapters",
    "llm_clients",
    "models",
    "tools",
    "utils",
):
    try:
        _mod = importlib.import_module(f"tradingagents.{_name}")
    except ImportError:
        # 依赖未安装时跳过,等用户真正使用时会再次尝试
        continue
    sys.modules.setdefault(f"tac.{_name}", _mod)

__all__ = ["__version__", "__author__", "__description__"]
