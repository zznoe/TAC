"""
配置缓存服务
使用 Redis 缓存频繁查询的配置数据，减少 MongoDB 查询压力
"""

import json
import logging
from typing import Optional, Any, Dict
from datetime import timedelta
from app.core.redis_client import get_redis_service, RedisService

logger = logging.getLogger(__name__)

# 缓存过期时间配置
CACHE_TTL_CONFIG = {
    "system_config": 300,  # 5分钟
    "model_catalog": 600,  # 10分钟
    "providers": 300,      # 5分钟
    "favorites": 1800,     # 30分钟
    "stock_info": 3600,    # 1小时
}


class ConfigCacheService:
    """配置缓存服务"""
    
    def __init__(self):
        self.redis_service = get_redis_service()
    
    def _get_cache_key(self, cache_type: str, key_suffix: str = "") -> str:
        """生成缓存键"""
        if key_suffix:
            return f"cache:{cache_type}:{key_suffix}"
        return f"cache:{cache_type}"
    
    async def get_cached(self, cache_type: str, key_suffix: str = "") -> Optional[Any]:
        """
        获取缓存数据
        
        Args:
            cache_type: 缓存类型 (system_config, model_catalog, providers 等)
            key_suffix: 键后缀
            
        Returns:
            缓存的数据，如果没有缓存则返回 None
        """
        try:
            key = self._get_cache_key(cache_type, key_suffix)
            cached_data = await self.redis_service.redis.get(key)
            
            if cached_data:
                logger.debug(f"✅ 缓存命中: {key}")
                return json.loads(cached_data)
            
            logger.debug(f"❌ 缓存未命中: {key}")
            return None
            
        except Exception as e:
            logger.error(f"❌ 获取缓存失败: {e}")
            return None
    
    async def set_cached(self, cache_type: str, data: Any, key_suffix: str = "", ttl: Optional[int] = None):
        """
        设置缓存数据
        
        Args:
            cache_type: 缓存类型
            data: 要缓存的数据
            key_suffix: 键后缀
            ttl: 过期时间（秒），默认为该类型的默认值
        """
        try:
            key = self._get_cache_key(cache_type, key_suffix)
            default_ttl = CACHE_TTL_CONFIG.get(cache_type, 300)
            ttl = ttl or default_ttl
            
            json_data = json.dumps(data, ensure_ascii=False, default=str)
            await self.redis_service.set_with_ttl(key, json_data, ttl)
            
            logger.debug(f"💾 缓存已设置: {key} (TTL: {ttl}s)")
            
        except Exception as e:
            logger.error(f"❌ 设置缓存失败: {e}")
    
    async def invalidate_cache(self, cache_type: str, key_suffix: str = ""):
        """
        使缓存失效
        
        Args:
            cache_type: 缓存类型
            key_suffix: 键后缀
        """
        try:
            key = self._get_cache_key(cache_type, key_suffix)
            await self.redis_service.redis.delete(key)
            logger.info(f"🗑️ 缓存已清除: {key}")
            
        except Exception as e:
            logger.error(f"❌ 清除缓存失败: {e}")
    
    async def invalidate_all(self, cache_type: str):
        """
        清除指定类型的所有缓存
        
        Args:
            cache_type: 缓存类型
        """
        try:
            pattern = f"cache:{cache_type}:*"
            keys = await self.redis_service.redis.keys(pattern)
            if keys:
                await self.redis_service.redis.delete(*keys)
                logger.info(f"🗑️ 已清除 {len(keys)} 个 {cache_type} 缓存")
            
        except Exception as e:
            logger.error(f"❌ 批量清除缓存失败: {e}")
    
    async def get_or_set(self, cache_type: str, fetch_func, key_suffix: str = "", ttl: Optional[int] = None):
        """
        获取缓存，如果不存在则调用 fetch_func 获取并缓存
        
        Args:
            cache_type: 缓存类型
            fetch_func: 获取数据的异步函数
            key_suffix: 键后缀
            ttl: 过期时间
            
        Returns:
            数据（从缓存或数据库）
        """
        # 先尝试从缓存获取
        cached_data = await self.get_cached(cache_type, key_suffix)
        if cached_data is not None:
            return cached_data
        
        # 缓存未命中，调用 fetch_func 获取
        try:
            logger.info(f"🔄 缓存未命中，从数据库获取: {cache_type}:{key_suffix}")
            data = await fetch_func()
            
            # 缓存数据
            if data is not None:
                await self.set_cached(cache_type, data, key_suffix, ttl)
            
            return data
            
        except Exception as e:
            logger.error(f"❌ 获取数据失败: {e}")
            raise


# 全局缓存服务实例
config_cache: Optional[ConfigCacheService] = None


def get_config_cache() -> ConfigCacheService:
    """获取配置缓存服务实例"""
    global config_cache
    if config_cache is None:
        config_cache = ConfigCacheService()
    return config_cache
