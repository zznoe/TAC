"""
增强版队列服务
基于现有实现，添加并发控制、优先级队列、可见性超时等功能
"""

import json
import time
import uuid
import asyncio
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta

from redis.asyncio import Redis

from app.core.database import get_redis_client

from app.services.queue import (
    READY_LIST,
    TASK_PREFIX,
    BATCH_PREFIX,
    SET_PROCESSING,
    SET_COMPLETED,
    SET_FAILED,
    BATCH_TASKS_PREFIX,
    USER_PROCESSING_PREFIX,
    GLOBAL_CONCURRENT_KEY,
    VISIBILITY_TIMEOUT_PREFIX,
    TIMEOUT_ZSET,
    DEFAULT_USER_CONCURRENT_LIMIT,
    GLOBAL_CONCURRENT_LIMIT,
    VISIBILITY_TIMEOUT_SECONDS,
)
from app.services.queue.helpers import (
    DEQUEUE_LUA_SCRIPT,
    check_user_concurrent_limit,
    check_global_concurrent_limit,
    mark_task_processing,
    unmark_task_processing,
    set_visibility_timeout,
    clear_visibility_timeout,
)

logger = logging.getLogger(__name__)

# Redis键名与配置常量由 app.services.queue.keys 提供（此处不再重复定义）


class QueueService:
    """增强版队列服务类"""

    def __init__(self, redis: Redis):
        self.r = redis
        self.user_concurrent_limit = DEFAULT_USER_CONCURRENT_LIMIT
        self.global_concurrent_limit = GLOBAL_CONCURRENT_LIMIT
        self.visibility_timeout = VISIBILITY_TIMEOUT_SECONDS

    async def enqueue_task(
        self,
        user_id: str,
        symbol: str,
        params: Dict[str, Any],
        batch_id: Optional[str] = None
    ) -> str:
        """任务入队，支持并发控制（开源版FIFO队列）"""

        # 检查用户并发限制
        if not await self._check_user_concurrent_limit(user_id):
            raise ValueError(f"用户 {user_id} 达到并发限制 ({self.user_concurrent_limit})")

        # 检查全局并发限制
        if not await self._check_global_concurrent_limit():
            raise ValueError(f"系统达到全局并发限制 ({self.global_concurrent_limit})")

        task_id = str(uuid.uuid4())
        key = TASK_PREFIX + task_id
        now = int(time.time())

        mapping = {
            "id": task_id,
            "user": user_id,
            "symbol": symbol,
            "status": "queued",
            "created_at": str(now),
            "params": json.dumps(params or {}),
            "enqueued_at": str(now)
        }

        if batch_id:
            mapping["batch_id"] = batch_id

        # 保存任务数据
        await self.r.hset(key, mapping=mapping)

        # 添加到FIFO队列
        await self.r.lpush(READY_LIST, task_id)

        if batch_id:
            await self.r.sadd(BATCH_TASKS_PREFIX + batch_id, task_id)

        logger.info(f"任务已入队: {task_id}")
        return task_id

    async def dequeue_task(self, worker_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """原子地从队列中取出任务（使用 Lua 脚本确保并发限制）"""
        try:
            # 如果指定了用户，检查该用户的并发；否则只做基本出队
            # 实际上 DEQUEUE_LUA_SCRIPT 需要特定的 user_processing_key
            # 这里我们假设从 READY_LIST 取出的任务是随机用户的，
            # 复杂的并发控制通常需要按用户分队列，或者在 Lua 中处理。
            
            # 目前的实现逻辑：
            # 我们先尝试 RPOP，如果是空就返回。
            # 如果有值，我们不能原子检查该用户的限制，因为我们还没拿到 task_id 就不知道 user_id。
            
            # 优化方案：
            # 1. 仍然使用 RPOP。
            # 2. 拿到 task_id 后，获取详情拿到 user_id。
            # 3. 使用一个更小的 Lua 脚本原子地检查并发并标记处理中。
            
            task_id = await self.r.rpop(READY_LIST)
            if not task_id:
                return None

            # 获取任务详情
            task_data = await self.get_task(task_id)
            if not task_data:
                logger.warning(f"任务数据不存在: {task_id}")
                return None

            user_id = task_data.get("user")
            
            # 使用 Lua 脚本原子检查用户和全局并发限制并标记
            # KEYS: [USER_PROCESSING_KEY, SET_PROCESSING]
            # ARGS: [TASK_ID, USER_LIMIT, GLOBAL_LIMIT]
            MARK_LUA = """
            local user_key = KEYS[1]
            local global_key = KEYS[2]
            local task_id = ARGS[1]
            local user_limit = tonumber(ARGS[2])
            local global_limit = tonumber(ARGS[3])
            
            if redis.call('SCARD', global_key) >= global_limit then
                return "GLOBAL_LIMIT"
            end
            if redis.call('SCARD', user_key) >= user_limit then
                return "USER_LIMIT"
            end
            
            redis.call('SADD', user_key, task_id)
            redis.call('SADD', global_key, task_id)
            return "OK"
            """
            
            res = await self.r.eval(
                MARK_LUA, 2, 
                USER_PROCESSING_PREFIX + user_id, 
                SET_PROCESSING,
                task_id, self.user_concurrent_limit, self.global_concurrent_limit
            )
            
            if res != "OK":
                # 重新入队
                await self.r.lpush(READY_LIST, task_id)
                logger.warning(f"任务 {task_id} 重新入队 (原因: {res})")
                return None

            # 设置可见性超时
            await self._set_visibility_timeout(task_id, worker_id)

            # 更新任务状态
            await self.r.hset(TASK_PREFIX + task_id, mapping={
                "status": "processing",
                "worker_id": worker_id,
                "started_at": str(int(time.time()))
            })

            logger.info(f"任务已出队: {task_id} -> Worker: {worker_id}")
            return task_data

        except Exception as e:
            logger.error(f"出队失败: {e}")
            return None

    async def ack_task(self, task_id: str, success: bool = True) -> bool:
        """确认任务完成"""
        try:
            task_data = await self.get_task(task_id)
            if not task_data:
                return False

            user_id = task_data.get("user")
            worker_id = task_data.get("worker_id")

            # 从处理中集合移除
            await self._unmark_task_processing(task_id, user_id)

            # 清除可见性超时
            await self._clear_visibility_timeout(task_id)

            # 更新任务状态
            status = "completed" if success else "failed"
            await self.r.hset(TASK_PREFIX + task_id, mapping={
                "status": status,
                "completed_at": str(int(time.time()))
            })

            # 添加到相应的集合
            if success:
                await self.r.sadd(SET_COMPLETED, task_id)
            else:
                await self.r.sadd(SET_FAILED, task_id)

            logger.info(f"任务已确认: {task_id} (成功: {success})")
            return True

        except Exception as e:
            logger.error(f"确认任务失败: {e}")
            return False

    async def create_batch(self, user_id: str, symbols: List[str], params: Dict[str, Any]) -> tuple[str, int]:
        batch_id = str(uuid.uuid4())
        now = int(time.time())
        batch_key = BATCH_PREFIX + batch_id
        await self.r.hset(batch_key, mapping={
            "id": batch_id,
            "user": user_id,
            "status": "queued",
            "submitted": str(len(symbols)),
            "created_at": str(now),
        })
        for s in symbols:
            await self.enqueue_task(user_id=user_id, symbol=s, params=params, batch_id=batch_id)
        return batch_id, len(symbols)

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        key = TASK_PREFIX + task_id
        data = await self.r.hgetall(key)
        if not data:
            return None
        # parse fields
        if "params" in data:
            try:
                data["parameters"] = json.loads(data.pop("params"))
            except Exception:
                data["parameters"] = {}
        if "created_at" in data and data["created_at"].isdigit():
            data["created_at"] = int(data["created_at"])
        if "submitted" in data and str(data["submitted"]).isdigit():
            data["submitted"] = int(data["submitted"])
        return data

    async def get_batch(self, batch_id: str) -> Optional[Dict[str, Any]]:
        key = BATCH_PREFIX + batch_id
        data = await self.r.hgetall(key)
        if not data:
            return None
        # enrich with tasks count if set exists
        submitted = data.get("submitted")
        if submitted is not None and str(submitted).isdigit():
            data["submitted"] = int(submitted)
        if "created_at" in data and data["created_at"].isdigit():
            data["created_at"] = int(data["created_at"])
        data["tasks"] = list(await self.r.smembers(BATCH_TASKS_PREFIX + batch_id))
        return data

    async def stats(self) -> Dict[str, int]:
        queued = await self.r.llen(READY_LIST)
        processing = await self.r.scard(SET_PROCESSING)
        completed = await self.r.scard(SET_COMPLETED)
        failed = await self.r.scard(SET_FAILED)
        return {
            "queued": int(queued or 0),
            "processing": int(processing or 0),
            "completed": int(completed or 0),
            "failed": int(failed or 0),
        }

    # 新增：并发控制方法
    async def _check_user_concurrent_limit(self, user_id: str) -> bool:
        """检查用户并发限制（委托 helpers）"""
        return await check_user_concurrent_limit(self.r, user_id, self.user_concurrent_limit)

    async def _check_global_concurrent_limit(self) -> bool:
        """检查全局并发限制（委托 helpers）"""
        return await check_global_concurrent_limit(self.r, self.global_concurrent_limit)

    async def _mark_task_processing(self, task_id: str, user_id: str, worker_id: str):
        """标记任务为处理中（委托 helpers）"""
        await mark_task_processing(self.r, task_id, user_id)

    async def _unmark_task_processing(self, task_id: str, user_id: str):
        """取消任务处理中标记（委托 helpers）"""
        await unmark_task_processing(self.r, task_id, user_id)

    async def _set_visibility_timeout(self, task_id: str, worker_id: str):
        """设置可见性超时（委托 helpers）"""
        await set_visibility_timeout(self.r, task_id, worker_id, self.visibility_timeout)

    async def _clear_visibility_timeout(self, task_id: str):
        """清除可见性超时"""
        await clear_visibility_timeout(self.r, task_id)

    async def get_user_queue_status(self, user_id: str) -> Dict[str, int]:
        """获取用户队列状态"""
        user_processing_key = USER_PROCESSING_PREFIX + user_id
        processing_count = await self.r.scard(user_processing_key)

        return {
            "processing": int(processing_count or 0),
            "concurrent_limit": self.user_concurrent_limit,
            "available_slots": max(0, self.user_concurrent_limit - int(processing_count or 0))
        }

    async def cleanup_expired_tasks(self):
        """清理过期任务（使用 ZSET 高效查询）"""
        try:
            current_time = int(time.time())
            # 获取所有已过期的任务 ID
            expired_tasks = await self.r.zrangebyscore(TIMEOUT_ZSET, 0, current_time)

            if not expired_tasks:
                return

            # 处理过期任务
            for task_id in expired_tasks:
                if isinstance(task_id, bytes):
                    task_id = task_id.decode('utf-8')
                await self._handle_expired_task(task_id)

            logger.warning(f"⏰ 处理了 {len(expired_tasks)} 个过期任务")

        except Exception as e:
            logger.error(f"清理过期任务失败: {e}")

    async def _handle_expired_task(self, task_id: str):
        """处理过期任务"""
        try:
            task_data = await self.get_task(task_id)
            if not task_data:
                return

            user_id = task_data.get("user")

            # 从处理中集合移除
            await self._unmark_task_processing(task_id, user_id)

            # 清除可见性超时
            await self._clear_visibility_timeout(task_id)

            # 重新加入队列
            await self.r.lpush(READY_LIST, task_id)

            # 更新任务状态
            await self.r.hset(TASK_PREFIX + task_id, mapping={
                "status": "queued",
                "worker_id": "",
                "requeued_at": str(int(time.time()))
            })

            logger.warning(f"过期任务重新入队: {task_id}")

        except Exception as e:
            logger.error(f"处理过期任务失败: {task_id} - {e}")

    async def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        try:
            task_data = await self.get_task(task_id)
            if not task_data:
                return False

            status = task_data.get("status")
            user_id = task_data.get("user")

            if status == "processing":
                # 如果正在处理中，从处理集合移除
                await self._unmark_task_processing(task_id, user_id)
                await self._clear_visibility_timeout(task_id)
            elif status == "queued":
                # 如果在队列中，从队列移除
                await self.r.lrem(READY_LIST, 0, task_id)

            # 更新任务状态
            await self.r.hset(TASK_PREFIX + task_id, mapping={
                "status": "cancelled",
                "cancelled_at": str(int(time.time()))
            })

            logger.info(f"任务已取消: {task_id}")
            return True

        except Exception as e:
            logger.error(f"取消任务失败: {e}")
            return False


def get_queue_service() -> QueueService:
    return QueueService(get_redis_client())