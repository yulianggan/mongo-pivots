#!/usr/bin/env python3
"""
完整的MongoDB后端 - 包含所有原始API接口
基于原始后端，支持所有前端功能
"""

import os
import uvicorn
import math
import datetime
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient, ASCENDING
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import pandas as pd
import chardet
from io import BytesIO

# 环境变量
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "ozondatas")
ALLOWED_COLLECTIONS = os.getenv("ALLOWED_COLLECTIONS", "*")
PIVOT_PREFS_COLLECTION = os.getenv("PIVOT_PREFS_COLLECTION", "pivot_prefs")

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

# ==================== 数据模型 ====================

class QueryRequest(BaseModel):
    collection: str
    filters: Optional[Dict[str, Any]] = Field(default_factory=dict)
    limit: int = 5000
    skip: int = 0
    projection: Optional[Dict[str, int]] = Field(default_factory=lambda: {"_id": 0})

class DataRequest(BaseModel):
    collection: str
    limit: int = 5000
    skip: int = 0
    filters: Dict[str, Any] = {}

class CollectionInfo(BaseModel):
    name: str
    count: int
    description: str

# ==================== 工具函数 ====================

def safe_convert_value(v):
    """Convert value to JSON-safe format"""
    if v is None:
        return None
    if isinstance(v, (int, str, bool)):
        return v
    if isinstance(v, float):
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    return str(v)

def flatten_value(v):
    if v is None: 
        return None
    if isinstance(v, (list, tuple, set)): 
        return ', '.join(map(str, v))
    if isinstance(v, dict): 
        return str(v)
    return v

def flatten_doc(doc):
    return {k: flatten_value(v) for k, v in doc.items()}

# ==================== 偏好存储 ====================

class PrefsStore:
    def __init__(self):
        if db is not None:
            self._coll = db[PIVOT_PREFS_COLLECTION]
            try:
                self._coll.create_index([("collection", ASCENDING), ("name", ASCENDING)], unique=True)
            except Exception as e:
                print(f"⚠️ 创建偏好索引失败: {e}")
        else:
            self._coll = None
    
    def list(self, collection: str) -> List[Dict[str, Any]]:
        if self._coll is None:
            return []
        return list(self._coll.find(
            {"collection": collection}, 
            {"_id": 0, "collection": 1, "name": 1, "updatedAt": 1}
        ).sort("updatedAt", -1))
    
    def list_all(self) -> List[Dict[str, Any]]:
        if self._coll is None:
            return []
        return list(self._coll.find(
            {}, 
            {"_id": 0, "collection": 1, "name": 1, "updatedAt": 1}
        ).sort("updatedAt", -1))
    
    def get(self, collection: str, name: str) -> Optional[Dict[str, Any]]:
        if self._coll is None:
            return None
        return self._coll.find_one({"collection": collection, "name": name}, {"_id": 0})
    
    def save(self, body: Dict[str, Any]) -> bool:
        if self._coll is None:
            return False
        col = body.get("collection")
        name = body.get("name")
        if not col or not name: 
            return False
        body = dict(body)
        body["updatedAt"] = datetime.datetime.utcnow().isoformat() + "Z"
        self._coll.update_one({"collection": col, "name": name}, {"$set": body}, upsert=True)
        return True
    
    def delete(self, collection: str, name: str) -> bool:
        if self._coll is None:
            return False
        self._coll.delete_one({"collection": collection, "name": name})
        return True

# ==================== FastAPI应用 ====================

app = FastAPI(title="Complete MongoDB Pivot API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_headers=["*"],
    allow_methods=["*"]
)

prefs = PrefsStore()

# ==================== API端点 ====================

@app.get("/")
def root():
    return {"message": "Complete MongoDB Pivot API", "status": "ok"}

@app.get("/api/health")
def health():
    return {"status": "ok", "mongodb_connected": db is not None}

@app.get("/api/engine/status")
def engine_status():
    """获取数据引擎状态和性能统计"""
    return {
        "status": "ok",
        "engine": "pymongo",
        "mongodb_connected": db is not None,
        "database": MONGO_DB,
        "collections_allowed": ALLOWED_COLLECTIONS
    }

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
            safe_doc = {k: safe_convert_value(v) for k, v in doc.items()}
            rows.append(flatten_doc(safe_doc))
        
        return {
            "count": len(rows),
            "rows": rows
        }
    except Exception as e:
        return {"error": f"预览数据失败: {str(e)}"}

@app.post("/api/query")
def query(req: QueryRequest):
    """执行MongoDB查询"""
    if db is None:
        raise HTTPException(500, "MongoDB连接失败")
    
    try:
        coll = db[req.collection]
        if not isinstance(req.filters, dict):
            raise HTTPException(400, "filters must be object")
        
        cur = coll.find(req.filters, req.projection).skip(req.skip).limit(req.limit)
        rows = []
        for doc in cur:
            safe_doc = {k: (str(v) if k == "_id" else safe_convert_value(v)) for k, v in doc.items()}
            rows.append(flatten_doc(safe_doc))
        
        return {"count": len(rows), "rows": rows}
    except Exception as e:
        raise HTTPException(500, f"查询失败: {str(e)}")

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
            safe_doc = {k: safe_convert_value(v) for k, v in doc.items()}
            rows.append(flatten_doc(safe_doc))
        
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

@app.post("/api/upload")
async def upload(file: UploadFile = File(...), sheet: str | None = Form(None), start_row: int = Form(1)):
    """文件上传和解析"""
    name = file.filename or "upload"
    content = await file.read()
    ext = (name.split(".")[-1] or "").lower()
    
    if not content:
        raise HTTPException(400, "文件为空")
    
    try:
        if ext in ("csv", "tsv", "txt"):
            # 检测编码
            detected = chardet.detect(content)
            encoding = detected.get('encoding', 'utf-8') if detected else 'utf-8'
            
            # 如果检测置信度低，尝试常见编码
            if detected and detected.get('confidence', 0) < 0.7:
                for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1', 'cp1252']:
                    try:
                        content.decode(enc)
                        encoding = enc
                        break
                    except:
                        continue
            
            # 智能检测分隔符
            sep = ","
            if ext == "tsv":
                sep = "\\t"
            
            # 使用pandas解析CSV
            df = pd.read_csv(
                BytesIO(content),
                sep=sep,
                header=start_row-1 if start_row > 1 else 0,
                encoding=encoding,
                engine='python',
                skipinitialspace=True,
                dtype=str,
                na_values=['', 'NULL', 'null', 'N/A', 'n/a', 'NA', 'na'],
                keep_default_na=True
            )
            
        else:
            # Excel文件处理
            sheet_arg = None
            if sheet:
                try:
                    sheet_arg = int(sheet)
                except:
                    sheet_arg = sheet
            
            df = pd.read_excel(
                BytesIO(content),
                sheet_name=sheet_arg,
                header=start_row-1 if start_row > 1 else 0,
                dtype=str,
                na_values=['', 'NULL', 'null', 'N/A', 'n/a', 'NA', 'na'],
                keep_default_na=True
            )
        
        if df.empty:
            raise HTTPException(400, "文件不包含任何数据")
        
        # 转换为记录列表
        rows = df.fillna('').to_dict('records')
        
        # 获取字段类型信息
        fields = {col: str(df[col].dtype) for col in df.columns}
        
        if not rows:
            raise HTTPException(400, "文件中没有找到有效数据")
        
        return {
            "filename": name,
            "count": len(rows),
            "rows": rows,
            "fields": fields,
            "message": f"成功解析 {len(rows)} 行数据，共 {len(df.columns)} 列"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"文件 '{name}' 解析失败: {str(e)}")

@app.get("/api/prefs/list")
def prefs_list(collection: str = None):
    """获取偏好设置列表"""
    if collection:
        return {"items": prefs.list(collection)}
    else:
        return {"items": prefs.list_all()}

@app.get("/api/prefs/get")
def prefs_get(collection: str, name: str):
    """获取指定偏好设置"""
    return {"doc": prefs.get(collection, name)}

@app.post("/api/prefs/save")
def prefs_save(body: dict):
    """保存偏好设置"""
    return {"ok": prefs.save(body)}

@app.delete("/api/prefs/delete")
def prefs_del(collection: str, name: str):
    """删除偏好设置"""
    return {"ok": prefs.delete(collection, name)}

if __name__ == "__main__":
    print("🚀 启动完整MongoDB后端服务...")
    print("前端访问: http://localhost:3000/")
    print("后端API: http://localhost:8000/")
    print("API文档: http://localhost:8000/docs")
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )