#!/usr/bin/env python3
"""
简化的MongoDB连接测试后端
用于验证MongoDB连接和集合显示
"""

import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from typing import List, Dict, Any
from pydantic import BaseModel

class DataRequest(BaseModel):
    collection: str
    limit: int = 5000
    skip: int = 0
    filters: Dict[str, Any] = {}

# 环境变量
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "ozondatas")
ALLOWED_COLLECTIONS = os.getenv("ALLOWED_COLLECTIONS", "*")

print(f"🔗 MongoDB URI: {MONGO_URI}")
print(f"📊 Database: {MONGO_DB}")
print(f"📋 Allowed Collections: {ALLOWED_COLLECTIONS}")

# MongoDB连接
try:
    client = MongoClient(MONGO_URI)
    db = client[MONGO_DB]
    print(f"✅ MongoDB连接成功")
except Exception as e:
    print(f"❌ MongoDB连接失败: {e}")
    client = None
    db = None

app = FastAPI(title="MongoDB Connection Test API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"]
)

@app.get("/")
def root():
    return {"message": "MongoDB Test API", "status": "ok"}

@app.get("/api/health")
def health():
    return {"status": "ok", "mongodb_connected": db is not None}

@app.get("/api/collections")
def collections():
    """获取MongoDB集合列表"""
    if db is None:
        return {
            "success": False,
            "error": "MongoDB连接失败",
            "collections": []
        }
    
    try:
        # 获取真实集合
        real_collections = db.list_collection_names()
        print(f"🔍 发现集合: {real_collections}")
        
        # 检查允许的集合
        allowed = [s.strip() for s in ALLOWED_COLLECTIONS.split(",") if s.strip()]
        if "*" in allowed:
            collections_to_return = real_collections
        else:
            collections_to_return = [coll for coll in real_collections if coll in allowed]
        
        result = []
        for coll_name in collections_to_return:
            try:
                # 获取文档数量
                count = db[coll_name].count_documents({})
                result.append({
                    "name": coll_name,
                    "count": count,
                    "description": f"{coll_name}集合"
                })
            except Exception as e:
                print(f"⚠️ 获取集合 {coll_name} 统计失败: {e}")
                result.append({
                    "name": coll_name,
                    "count": 0,
                    "description": f"{coll_name}集合"
                })
        
        print(f"📋 返回集合: {[r['name'] for r in result]}")
        return {
            "success": True,
            "collections": result
        }
        
    except Exception as e:
        print(f"❌ 列出集合失败: {e}")
        return {
            "success": False,
            "error": f"列出集合失败: {str(e)}",
            "collections": []
        }

@app.get("/api/fields")
def fields(collection: str, sample: int = 200):
    """获取集合字段信息"""
    if db is None:
        return {"error": "MongoDB连接失败"}
    
    try:
        coll = db[collection]
        fields = {}
        for doc in coll.find({}).limit(sample):
            for k, v in doc.items():
                fields.setdefault(k, type(v).__name__)
        
        return {
            "collection": collection,
            "fields": fields
        }
    except Exception as e:
        return {"error": f"获取字段失败: {str(e)}"}

@app.get("/api/peek")
def peek(collection: str, limit: int = 50):
    """预览集合数据"""
    if db is None:
        return {"error": "MongoDB连接失败"}
    
    try:
        coll = db[collection]
        rows = []
        for doc in coll.find({}, {"_id": 0}).limit(limit):
            # 简化处理，直接转换为字符串避免序列化问题
            safe_doc = {}
            for k, v in doc.items():
                try:
                    if v is None:
                        safe_doc[k] = None
                    elif isinstance(v, (str, int, float, bool)):
                        safe_doc[k] = v
                    else:
                        safe_doc[k] = str(v)
                except:
                    safe_doc[k] = str(v)
            rows.append(safe_doc)
        
        return {
            "count": len(rows),
            "rows": rows
        }
    except Exception as e:
        return {"error": f"预览数据失败: {str(e)}"}

@app.post("/api/data")
def get_data(request: DataRequest):
    """获取集合数据（兼容前端API调用）"""
    if db is None:
        return {
            "success": False,
            "message": "MongoDB连接失败",
            "data": []
        }
    
    try:
        coll = db[request.collection]
        
        # 构建查询
        query = request.filters or {}
        
        # 执行查询
        cursor = coll.find(query, {"_id": 0}).skip(request.skip).limit(request.limit)
        
        rows = []
        for doc in cursor:
            # 简化处理，直接转换为字符串避免序列化问题
            safe_doc = {}
            for k, v in doc.items():
                try:
                    if v is None:
                        safe_doc[k] = None
                    elif isinstance(v, (str, int, float, bool)):
                        safe_doc[k] = v
                    else:
                        safe_doc[k] = str(v)
                except:
                    safe_doc[k] = str(v)
            rows.append(safe_doc)
        
        return {
            "success": True,
            "data": rows,
            "total": len(rows),
            "message": f"成功获取 {len(rows)} 条记录"
        }
        
    except Exception as e:
        return {
            "success": False,
            "message": f"获取数据失败: {str(e)}",
            "data": []
        }

if __name__ == "__main__":
    print("🚀 启动MongoDB测试服务...")
    print("前端访问: http://localhost:3000/")
    print("后端API: http://localhost:8000/")
    print("API文档: http://localhost:8000/docs")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )