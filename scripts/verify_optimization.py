"""
性能优化验证脚本
用于验证 MongoDB 索引、批量操作和缓存优化的效果
"""

import asyncio
import time
import logging
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.utils.bulk_operations import efficient_bulk_upsert
from app.services.config_cache_service import get_config_cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def verify_mongodb_indexes(db):
    """验证 MongoDB 索引是否生效"""
    logger.info("🔍 验证 MongoDB 索引...")
    
    collections = ["analysis_tasks", "reports", "market_quotes", "stock_basic_info"]
    
    for coll_name in collections:
        coll = db[coll_name]
        # 使用 explain 检查查询计划
        pipeline = [{"$match": {"symbol": "600519"}}] if coll_name != "analysis_tasks" else [{"$match": {"task_id": "test"}}]
        
        try:
            explain = await coll.find(pipeline[0]["$match"]).explain()
            winning_plan = explain.get("queryPlanner", {}).get("winningPlan", {})
            stage = winning_plan.get("stage", "")
            
            if "IXSCAN" in str(winning_plan):
                logger.info(f"✅ {coll_name}: 索引生效 (Stage: {stage})")
            else:
                logger.warning(f"⚠️ {coll_name}: 未命中索引，可能需要检查索引创建情况")
        except Exception as e:
            logger.error(f"❌ 验证 {coll_name} 索引失败: {e}")

async def test_bulk_vs_individual(db):
    """对比批量操作与单个操作的性能"""
    logger.info("\n⏱️ 测试批量操作性能 (100条数据)...")
    
    test_data = [
        {"code": f"TEST{i:03d}", "name": f"Test Stock {i}", "updated_at": datetime.utcnow()}
        for i in range(100)
    ]
    
    coll = db["test_performance"]
    await coll.drop()
    
    # 1. 单个操作
    start_time = time.perf_counter()
    for doc in test_data:
        await coll.update_one({"code": doc["code"]}, {"$set": doc}, upsert=True)
    individual_time = time.perf_counter() - start_time
    logger.info(f"🐢 单个操作耗时: {individual_time:.4f}s")
    
    await coll.drop()
    
    # 2. 批量操作
    start_time = time.perf_counter()
    await efficient_bulk_upsert(coll, test_data, key_fields=["code"])
    bulk_time = time.perf_counter() - start_time
    logger.info(f"🚀 批量操作耗时: {bulk_time:.4f}s")
    
    if bulk_time < individual_time:
        improvement = (individual_time - bulk_time) / individual_time * 100
        logger.info(f"📈 性能提升: {improvement:.2f}%")

async def test_redis_cache():
    """测试 Redis 缓存性能"""
    logger.info("\n⚡ 测试 Redis 缓存性能...")
    cache = get_config_cache()
    
    test_key = "perf_test"
    test_data = {"data": "x" * 1000} # 1KB 数据
    
    # 写入并读取
    await cache.set_cached("system_config", test_data, key_suffix=test_key)
    
    start_time = time.perf_counter()
    for _ in range(100):
        await cache.get_cached("system_config", key_suffix=test_key)
    avg_latency = (time.perf_counter() - start_time) / 100 * 1000
    
    logger.info(f"🏎️ Redis 平均读取延迟: {avg_latency:.4f}ms")

async def main():
    client = AsyncIOMotorClient(settings.MONGO_URI)
    db = client[settings.MONGO_DB]
    
    try:
        await verify_mongodb_indexes(db)
        await test_bulk_vs_individual(db)
        await test_redis_cache()
    finally:
        client.close()
        logger.info("\n✅ 验证完成")

if __name__ == "__main__":
    asyncio.run(main())
