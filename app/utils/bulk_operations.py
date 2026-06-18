"""
批量数据库操作优化工具
提供高效的批量插入、更新和 Upsert 操作
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from motor.motor_asyncio import AsyncIOMotorCollection
from pymongo import UpdateOne, InsertOne

logger = logging.getLogger(__name__)


class BulkOperationOptimizer:
    """批量操作优化工具类"""
    
    @staticmethod
    async def bulk_upsert(
        collection: AsyncIOMotorCollection,
        operations: List[Dict[str, Any]],
        key_fields: List[str] = ["code"],
        batch_size: int = 1000
    ) -> Dict[str, int]:
        """
        批量 Upsert 操作（插入或更新），使用 MongoDB bulk_write 提高效率
        
        Args:
            collection: MongoDB 集合
            operations: 操作列表，每项包含 {key_field: value, ...data...}
            key_fields: 唯一键字段名列表，用于构建查询条件
            batch_size: 每批处理的数量
            
        Returns:
            统计信息 {matched, upserted, modified, errors}
        """
        stats = {"matched": 0, "upserted": 0, "modified": 0, "errors": 0}
        
        for i in range(0, len(operations), batch_size):
            batch = operations[i:i + batch_size]
            bulk_ops = []
            
            for doc in batch:
                filter_doc = {}
                missing_key = False
                for field in key_fields:
                    val = doc.get(field)
                    if not val:
                        logger.warning(f"跳过缺少键字段 {field} 的文档")
                        missing_key = True
                        break
                    filter_doc[field] = val
                
                if missing_key:
                    stats["errors"] += 1
                    continue
                
                # 确保不修改原始文档，或者至少移除 _id 如果存在
                data = doc.copy()
                data.pop("_id", None)
                
                bulk_ops.append(
                    UpdateOne(filter_doc, {"$set": data}, upsert=True)
                )
            
            if bulk_ops:
                try:
                    result = await collection.bulk_write(bulk_ops, ordered=False)
                    stats["matched"] += result.matched_count
                    stats["upserted"] += result.upserted_count
                    stats["modified"] += result.modified_count
                except Exception as e:
                    logger.error(f"批量 Upsert 失败: {e}")
                    stats["errors"] += len(bulk_ops)
        
        return stats
    
    @staticmethod
    async def bulk_insert(
        collection: AsyncIOMotorCollection,
        documents: List[Dict[str, Any]],
        batch_size: int = 1000
    ) -> Dict[str, int]:
        """
        批量插入操作
        
        Args:
            collection: MongoDB 集合
            documents: 要插入的文档列表
            batch_size: 每批处理的数量
            
        Returns:
            统计信息
        """
        stats = {"inserted": 0, "errors": 0}
        
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            
            try:
                result = await collection.insert_many(batch)
                stats["inserted"] += len(result.inserted_ids)
            except Exception as e:
                logger.error(f"批量插入失败: {e}")
                stats["errors"] += len(batch)
        
        return stats
    
    @staticmethod
    async def bulk_replace_one_by_ids(
        collection: AsyncIOMotorCollection,
        ids: List[Any],
        replacement: Dict[str, Any]
    ) -> Dict[str, int]:
        """
        批量替换操作
        
        Args:
            collection: MongoDB 集合
            ids: 要替换的文档 ID 列表
            replacement: 替换后的文档
            
        Returns:
            统计信息
        """
        stats = {"matched": 0, "modified": 0, "errors": 0}
        
        try:
            result = await collection.update_many(
                {"_id": {"$in": ids}},
                {"$set": replacement}
            )
            stats["matched"] = result.matched_count
            stats["modified"] = result.modified_count
        except Exception as e:
            logger.error(f"批量替换失败: {e}")
            stats["errors"] += 1
        
        return stats


# 便捷函数
async def efficient_bulk_upsert(collection, operations, key_fields=["code"]):
    """高效批量 Upsert 的便捷函数"""
    return await BulkOperationOptimizer.bulk_upsert(collection, operations, key_fields)


async def efficient_bulk_insert(collection, documents):
    """高效批量插入的便捷函数"""
    return await BulkOperationOptimizer.bulk_insert(collection, documents)
