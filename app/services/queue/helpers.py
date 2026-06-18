"""
队列服务的辅助函数（与 Redis 操作相关），便于在主服务中做薄委托。
"""
from __future__ import annotations
import time
from typing import Dict
from redis.asyncio import Redis

from .keys import (
    READY_LIST,
    TASK_PREFIX,
    SET_PROCESSING,
    USER_PROCESSING_PREFIX,
    VISIBILITY_TIMEOUT_PREFIX,
    TIMEOUT_ZSET,
)

# Lua 脚本：原子出队并检查并发限制
# KEYS: [READY_LIST, USER_PROCESSING_KEY, SET_PROCESSING]
# ARGS: [TASK_PREFIX, WORKER_ID, USER_LIMIT, GLOBAL_LIMIT, START_TIME]
DEQUEUE_LUA_SCRIPT = """
local ready_list = KEYS[1]
local user_processing_key = KEYS[2]
local set_processing = KEYS[3]

local task_prefix = ARGS[1]
local worker_id = ARGS[2]
local user_limit = tonumber(ARGS[3])
local global_limit = tonumber(ARGS[4])
local start_time = ARGS[5]

-- 1. 检查全局并发
local global_count = redis.call('SCARD', set_processing)
if global_count >= global_limit then
    return {err = "GLOBAL_LIMIT_EXCEEDED"}
end

-- 2. 检查用户并发
local user_count = redis.call('SCARD', user_processing_key)
if user_count >= user_limit then
    return {err = "USER_LIMIT_EXCEEDED"}
end

-- 3. 获取任务
local task_id = redis.call('RPOP', ready_list)
if not task_id then
    return nil
end

-- 4. 标记处理中
redis.call('SADD', user_processing_key, task_id)
redis.call('SADD', set_processing, task_id)

-- 5. 更新任务状态
local task_key = task_prefix .. task_id
redis.call('HMSET', task_key, 'status', 'processing', 'worker_id', worker_id, 'started_at', start_time)

return task_id
"""

async def check_user_concurrent_limit(r: Redis, user_id: str, limit: int) -> bool:
    """检查用户并发限制"""
    user_processing_key = USER_PROCESSING_PREFIX + user_id
    current_count = await r.scard(user_processing_key)
    return current_count < limit


async def check_global_concurrent_limit(r: Redis, limit: int) -> bool:
    """检查全局并发限制（基于处理中集合大小）"""
    current_count = await r.scard(SET_PROCESSING)
    return current_count < limit


async def mark_task_processing(r: Redis, task_id: str, user_id: str) -> None:
    """标记任务为处理中"""
    user_processing_key = USER_PROCESSING_PREFIX + user_id
    await r.sadd(user_processing_key, task_id)
    await r.sadd(SET_PROCESSING, task_id)


async def unmark_task_processing(r: Redis, task_id: str, user_id: str) -> None:
    """取消任务处理中标记"""
    user_processing_key = USER_PROCESSING_PREFIX + user_id
    await r.srem(user_processing_key, task_id)
    await r.srem(SET_PROCESSING, task_id)


async def set_visibility_timeout(r: Redis, task_id: str, worker_id: str, visibility_timeout: int) -> None:
    """设置可见性超时"""
    timeout_key = VISIBILITY_TIMEOUT_PREFIX + task_id
    now = int(time.time())
    timeout_at = now + visibility_timeout
    
    timeout_data: Dict[str, str] = {
        "task_id": task_id,
        "worker_id": worker_id,
        "timeout_at": str(timeout_at),
    }
    # 保存详细信息
    await r.hset(timeout_key, mapping=timeout_data)
    await r.expire(timeout_key, visibility_timeout + 60) # 稍微多留一点时间
    
    # 添加到 ZSET 用于高效清理
    await r.zadd(TIMEOUT_ZSET, {task_id: timeout_at})


async def clear_visibility_timeout(r: Redis, task_id: str) -> None:
    """清除可见性超时"""
    timeout_key = VISIBILITY_TIMEOUT_PREFIX + task_id
    await r.delete(timeout_key)
    await r.zrem(TIMEOUT_ZSET, task_id)

