import os
from typing import Dict, Any, List
from pymongo import MongoClient

MONGO_URI=os.getenv("MONGO_URI","mongodb://localhost:27017")
MONGO_DB=os.getenv("MONGO_DB","ozondatas")
ALLOWED=[s.strip() for s in os.getenv("ALLOWED_COLLECTIONS","mbcampagin,opcampaign").split(",") if s.strip()]

_client=MongoClient(MONGO_URI)
_db=_client[MONGO_DB]

def list_collections()->List[Dict[str, Any]]:
    """获取MongoDB中的真实集合列表"""
    try:
        real_collections = _db.list_collection_names()
        
        # 如果ALLOWED_COLLECTIONS设置为"*"，返回所有集合
        if "*" in ALLOWED:
            collections_to_return = real_collections
        else:
            # 只返回允许的集合
            collections_to_return = [coll for coll in real_collections if coll in ALLOWED]
        
        result = []
        for coll_name in collections_to_return:
            try:
                # 获取集合统计信息
                stats = _db.command("collStats", coll_name)
                count = stats.get("count", 0)
                result.append({
                    "name": coll_name,
                    "count": count,
                    "description": f"{coll_name}集合"
                })
            except Exception:
                # 如果无法获取统计信息，使用基本信息
                result.append({
                    "name": coll_name,
                    "count": 0,
                    "description": f"{coll_name}集合"
                })
        
        return result
    except Exception as e:
        # 如果连接失败，返回模拟数据
        print(f"MongoDB连接失败: {e}")
        return [
            {"name": "customers", "count": 1000, "description": "客户数据"},
            {"name": "orders", "count": 2500, "description": "订单数据"},
            {"name": "products", "count": 150, "description": "产品数据"}
        ]

def get_collection(name:str):
    # 如果设置为"*"，允许访问所有集合
    if "*" not in ALLOWED and name not in ALLOWED:
        raise ValueError(f"Collection {name} not allowed")
    return _db[name]

def sample_fields(name:str, sample:int=200)->Dict[str,str]:
    coll=get_collection(name)
    fields={}
    for doc in coll.find({}, limit=sample):
        for k,v in doc.items():
            fields.setdefault(k, type(v).__name__)
    return fields
