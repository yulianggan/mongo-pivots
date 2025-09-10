"""
预设配置管理服务

提供连接预设的CRUD操作，包括：
- 保存和更新预设配置
- 查询和列表预设
- 用户权限控制
- 配置模板管理
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from ..core.config import settings
from ..models.api.request_models import JoinOperation
from ..models.api.response_models import PresetInfo

logger = logging.getLogger(__name__)


class PresetService:
    """预设配置管理服务"""
    
    def __init__(self):
        # 临时使用内存存储，实际应该使用数据库
        self._presets: Dict[str, Dict[str, Any]] = {}
        self._user_presets: Dict[str, List[str]] = {}  # user_id -> [preset_ids]
        
    async def save_preset(
        self,
        name: str,
        description: Optional[str],
        operations: List[JoinOperation],
        output_columns: Optional[List[str]],
        tags: Optional[List[str]],
        is_public: bool,
        user_id: str
    ) -> PresetInfo:
        """
        保存预设配置
        
        Args:
            name: 预设名称
            description: 预设描述
            operations: 连接操作列表
            output_columns: 输出列配置
            tags: 标签列表
            is_public: 是否公开
            user_id: 用户ID
            
        Returns:
            PresetInfo: 保存的预设信息
            
        Raises:
            ValueError: 预设名称已存在
        """
        # 检查名称是否重复（用户范围内）
        existing_preset = await self.get_preset_by_name(name, user_id)
        if existing_preset:
            raise ValueError(f"预设名称 '{name}' 已存在")
            
        # 生成预设ID
        preset_id = f"preset_{uuid.uuid4().hex[:12]}"
        
        # 创建预设数据
        now = datetime.now(timezone.utc)
        preset_data = {
            "preset_id": preset_id,
            "name": name,
            "description": description,
            "user_id": user_id,
            "is_public": is_public,
            "tags": tags or [],
            "usage_count": 0,
            "created_at": now,
            "updated_at": now,
            "operations": [op.dict() for op in operations],
            "output_columns": output_columns or []
        }
        
        # 保存预设
        self._presets[preset_id] = preset_data
        
        # 更新用户预设索引
        if user_id not in self._user_presets:
            self._user_presets[user_id] = []
        self._user_presets[user_id].append(preset_id)
        
        logger.info(f"保存预设成功: {preset_id} (用户: {user_id})")
        
        return PresetInfo(**{
            k: v for k, v in preset_data.items() 
            if k not in ["operations", "output_columns"]
        })
    
    async def get_preset_by_name(
        self, 
        name: str, 
        user_id: str, 
        exclude_preset_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        根据名称查找预设（用户范围内）
        
        Args:
            name: 预设名称
            user_id: 用户ID
            exclude_preset_id: 排除的预设ID（用于更新时检查）
            
        Returns:
            预设数据或None
        """
        user_preset_ids = self._user_presets.get(user_id, [])
        
        for preset_id in user_preset_ids:
            if exclude_preset_id and preset_id == exclude_preset_id:
                continue
                
            preset = self._presets.get(preset_id)
            if preset and preset["name"] == name:
                return preset
                
        return None
    
    async def get_preset(self, preset_id: str) -> Optional[Dict[str, Any]]:
        """
        获取预设基本信息
        
        Args:
            preset_id: 预设ID
            
        Returns:
            预设数据或None
        """
        return self._presets.get(preset_id)
    
    async def get_preset_detail(
        self, 
        preset_id: str, 
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取预设详细信息（包含完整配置）
        
        Args:
            preset_id: 预设ID
            user_id: 用户ID（用于权限检查）
            
        Returns:
            预设详细数据或None
        """
        preset = self._presets.get(preset_id)
        if not preset:
            return None
            
        # 检查访问权限
        if not preset["is_public"] and preset["user_id"] != user_id:
            return None
            
        return preset
    
    async def list_presets(
        self,
        user_id: str,
        offset: int = 0,
        limit: int = 20,
        search: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_public: Optional[bool] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc"
    ) -> Dict[str, Any]:
        """
        查询预设列表
        
        Args:
            user_id: 用户ID
            offset: 分页偏移量
            limit: 每页记录数
            search: 搜索关键词
            tags: 标签过滤
            is_public: 公开性过滤
            sort_by: 排序字段
            sort_order: 排序顺序
            
        Returns:
            包含预设列表和分页信息的字典
        """
        # 获取用户可访问的预设
        accessible_presets = []
        
        for preset_id, preset in self._presets.items():
            # 权限检查：公开预设或用户自己的预设
            if preset["is_public"] or preset["user_id"] == user_id:
                accessible_presets.append(preset)
        
        # 过滤条件
        filtered_presets = accessible_presets
        
        # 公开性过滤
        if is_public is not None:
            filtered_presets = [
                p for p in filtered_presets 
                if p["is_public"] == is_public
            ]
        
        # 搜索过滤
        if search:
            search_lower = search.lower()
            filtered_presets = [
                p for p in filtered_presets
                if (search_lower in p["name"].lower()) or
                   (p["description"] and search_lower in p["description"].lower()) or
                   any(search_lower in tag.lower() for tag in p["tags"])
            ]
        
        # 标签过滤
        if tags:
            filtered_presets = [
                p for p in filtered_presets
                if any(tag in p["tags"] for tag in tags)
            ]
        
        # 排序
        reverse = sort_order == "desc"
        if sort_by == "created_at" or sort_by == "updated_at":
            filtered_presets.sort(
                key=lambda x: x[sort_by], 
                reverse=reverse
            )
        elif sort_by == "name":
            filtered_presets.sort(
                key=lambda x: x["name"].lower(), 
                reverse=reverse
            )
        elif sort_by == "usage_count":
            filtered_presets.sort(
                key=lambda x: x["usage_count"], 
                reverse=reverse
            )
        
        # 分页
        total = len(filtered_presets)
        paged_presets = filtered_presets[offset:offset + limit]
        
        # 转换为PresetInfo格式
        preset_infos = [
            PresetInfo(**{
                k: v for k, v in preset.items() 
                if k not in ["operations", "output_columns"]
            })
            for preset in paged_presets
        ]
        
        return {
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + limit) < total,
            "presets": preset_infos
        }
    
    async def update_preset(
        self,
        preset_id: str,
        name: str,
        description: Optional[str],
        operations: List[JoinOperation],
        output_columns: Optional[List[str]],
        tags: Optional[List[str]],
        is_public: bool,
        user_id: str
    ) -> PresetInfo:
        """
        更新预设配置
        
        Args:
            preset_id: 预设ID
            name: 预设名称
            description: 预设描述
            operations: 连接操作列表
            output_columns: 输出列配置
            tags: 标签列表
            is_public: 是否公开
            user_id: 用户ID
            
        Returns:
            PresetInfo: 更新后的预设信息
            
        Raises:
            ValueError: 预设不存在或无权限
        """
        preset = self._presets.get(preset_id)
        if not preset:
            raise ValueError(f"预设 {preset_id} 不存在")
            
        if preset["user_id"] != user_id:
            raise ValueError("只能更新自己创建的预设")
        
        # 检查名称冲突（排除当前预设）
        existing_preset = await self.get_preset_by_name(
            name, user_id, exclude_preset_id=preset_id
        )
        if existing_preset:
            raise ValueError(f"预设名称 '{name}' 已存在")
        
        # 更新预设数据
        preset["name"] = name
        preset["description"] = description
        preset["tags"] = tags or []
        preset["is_public"] = is_public
        preset["operations"] = [op.dict() for op in operations]
        preset["output_columns"] = output_columns or []
        preset["updated_at"] = datetime.now(timezone.utc)
        
        logger.info(f"预设更新成功: {preset_id}")
        
        return PresetInfo(**{
            k: v for k, v in preset.items() 
            if k not in ["operations", "output_columns"]
        })
    
    async def delete_preset(self, preset_id: str, user_id: str) -> None:
        """
        删除预设配置
        
        Args:
            preset_id: 预设ID
            user_id: 用户ID
            
        Raises:
            ValueError: 预设不存在或无权限
        """
        preset = self._presets.get(preset_id)
        if not preset:
            raise ValueError(f"预设 {preset_id} 不存在")
            
        if preset["user_id"] != user_id:
            raise ValueError("只能删除自己创建的预设")
        
        # 删除预设
        del self._presets[preset_id]
        
        # 更新用户预设索引
        if user_id in self._user_presets:
            self._user_presets[user_id].remove(preset_id)
        
        logger.info(f"预设删除成功: {preset_id}")
    
    async def clone_preset(
        self, 
        source_preset_id: str, 
        new_name: str, 
        user_id: str
    ) -> PresetInfo:
        """
        克隆预设配置
        
        Args:
            source_preset_id: 源预设ID
            new_name: 新预设名称
            user_id: 用户ID
            
        Returns:
            PresetInfo: 新创建的预设信息
            
        Raises:
            ValueError: 源预设不存在或无访问权限
        """
        source_preset = await self.get_preset_detail(source_preset_id, user_id)
        if not source_preset:
            raise ValueError(f"预设 {source_preset_id} 不存在或无访问权限")
        
        # 检查新名称是否冲突
        existing_preset = await self.get_preset_by_name(new_name, user_id)
        if existing_preset:
            raise ValueError(f"预设名称 '{new_name}' 已存在")
        
        # 重建操作对象
        operations = [
            JoinOperation(**op_data) 
            for op_data in source_preset["operations"]
        ]
        
        # 创建克隆预设
        cloned_preset = await self.save_preset(
            name=new_name,
            description=f"克隆自预设 {source_preset['name']}",
            operations=operations,
            output_columns=source_preset["output_columns"],
            tags=["克隆"] + source_preset["tags"],
            is_public=False,  # 克隆的预设默认为私有
            user_id=user_id
        )
        
        logger.info(f"预设克隆成功: {source_preset_id} -> {cloned_preset.preset_id}")
        
        return cloned_preset
    
    async def increment_usage_count(self, preset_id: str) -> None:
        """
        增加预设使用次数
        
        Args:
            preset_id: 预设ID
        """
        preset = self._presets.get(preset_id)
        if preset:
            preset["usage_count"] += 1
            logger.debug(f"预设使用次数更新: {preset_id} -> {preset['usage_count']}")
    
    async def get_popular_presets(
        self, 
        user_id: str, 
        limit: int = 10
    ) -> List[PresetInfo]:
        """
        获取热门预设（按使用次数排序）
        
        Args:
            user_id: 用户ID
            limit: 返回数量限制
            
        Returns:
            热门预设列表
        """
        result = await self.list_presets(
            user_id=user_id,
            limit=limit,
            sort_by="usage_count",
            sort_order="desc"
        )
        
        return result["presets"]
    
    async def get_recent_presets(
        self, 
        user_id: str, 
        limit: int = 10
    ) -> List[PresetInfo]:
        """
        获取最近创建的预设
        
        Args:
            user_id: 用户ID
            limit: 返回数量限制
            
        Returns:
            最近预设列表
        """
        result = await self.list_presets(
            user_id=user_id,
            limit=limit,
            sort_by="created_at",
            sort_order="desc"
        )
        
        return result["presets"]
    
    async def get_preset_templates(self) -> List[Dict[str, Any]]:
        """
        获取预设模板列表
        
        Returns:
            预设模板列表
        """
        # 返回一些常用的预设模板
        templates = [
            {
                "template_id": "template_inner_join",
                "name": "内连接模板",
                "description": "两表内连接的基础模板",
                "category": "基础连接",
                "operations": [
                    {
                        "left_dataset": {
                            "dataset_id": "",
                            "alias": "left",
                            "columns": []
                        },
                        "right_dataset": {
                            "dataset_id": "",
                            "alias": "right", 
                            "columns": []
                        },
                        "join_type": "inner",
                        "conditions": [
                            {
                                "left_column": "",
                                "right_column": "",
                                "operator": "="
                            }
                        ]
                    }
                ],
                "output_columns": []
            },
            {
                "template_id": "template_left_join",
                "name": "左连接模板", 
                "description": "两表左连接的基础模板",
                "category": "基础连接",
                "operations": [
                    {
                        "left_dataset": {
                            "dataset_id": "",
                            "alias": "left",
                            "columns": []
                        },
                        "right_dataset": {
                            "dataset_id": "",
                            "alias": "right",
                            "columns": []
                        },
                        "join_type": "left",
                        "conditions": [
                            {
                                "left_column": "",
                                "right_column": "",
                                "operator": "="
                            }
                        ]
                    }
                ],
                "output_columns": []
            },
            {
                "template_id": "template_multi_join",
                "name": "多表连接模板",
                "description": "三表连接的复合模板",
                "category": "复合连接",
                "operations": [
                    {
                        "left_dataset": {
                            "dataset_id": "",
                            "alias": "first",
                            "columns": []
                        },
                        "right_dataset": {
                            "dataset_id": "",
                            "alias": "second",
                            "columns": []
                        },
                        "join_type": "inner",
                        "conditions": [
                            {
                                "left_column": "",
                                "right_column": "",
                                "operator": "="
                            }
                        ]
                    },
                    {
                        "left_dataset": {
                            "dataset_id": "result_step_1",
                            "alias": "prev",
                            "columns": []
                        },
                        "right_dataset": {
                            "dataset_id": "",
                            "alias": "third",
                            "columns": []
                        },
                        "join_type": "left",
                        "conditions": [
                            {
                                "left_column": "",
                                "right_column": "",
                                "operator": "="
                            }
                        ]
                    }
                ],
                "output_columns": []
            }
        ]
        
        return templates


# 全局预设服务实例
preset_service = PresetService()