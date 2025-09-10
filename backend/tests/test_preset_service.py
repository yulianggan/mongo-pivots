"""
预设配置管理服务测试

测试PresetService类的所有功能，包括：
- CRUD操作
- 用户权限控制
- 预设模板管理
- 搜索和分页功能
"""
import pytest
from datetime import datetime, timezone
from typing import Dict, Any

from ..services.preset_service import PresetService
from ..models.api.request_models import JoinOperation, DatasetReference, JoinCondition, JoinType


class TestPresetService:
    """预设服务测试类"""
    
    @pytest.fixture
    def preset_service(self):
        """创建预设服务实例"""
        return PresetService()
    
    @pytest.fixture
    def sample_operation(self):
        """创建示例连接操作"""
        return JoinOperation(
            left_dataset=DatasetReference(
                dataset_id="ds_users",
                alias="u",
                columns=["id", "name", "email"]
            ),
            right_dataset=DatasetReference(
                dataset_id="ds_orders", 
                alias="o",
                columns=["user_id", "amount", "created_at"]
            ),
            join_type=JoinType.INNER,
            conditions=[
                JoinCondition(
                    left_column="id",
                    right_column="user_id",
                    operator="="
                )
            ]
        )
    
    @pytest.mark.asyncio
    async def test_save_preset_success(self, preset_service, sample_operation):
        """测试成功保存预设"""
        # 准备测试数据
        name = "测试预设"
        description = "这是一个测试预设"
        operations = [sample_operation]
        output_columns = ["u.name", "o.amount"]
        tags = ["测试", "用户订单"]
        is_public = False
        user_id = "user_123"
        
        # 执行保存操作
        preset_info = await preset_service.save_preset(
            name=name,
            description=description,
            operations=operations,
            output_columns=output_columns,
            tags=tags,
            is_public=is_public,
            user_id=user_id
        )
        
        # 验证结果
        assert preset_info.name == name
        assert preset_info.description == description
        assert preset_info.user_id == user_id
        assert preset_info.is_public == is_public
        assert preset_info.tags == tags
        assert preset_info.usage_count == 0
        assert preset_info.preset_id.startswith("preset_")
        
        # 验证预设已保存
        saved_preset = await preset_service.get_preset(preset_info.preset_id)
        assert saved_preset is not None
        assert saved_preset["name"] == name
    
    @pytest.mark.asyncio
    async def test_save_preset_duplicate_name(self, preset_service, sample_operation):
        """测试保存重复名称预设失败"""
        name = "重复预设"
        user_id = "user_123"
        
        # 先保存一个预设
        await preset_service.save_preset(
            name=name,
            description="第一个预设",
            operations=[sample_operation],
            output_columns=[],
            tags=[],
            is_public=False,
            user_id=user_id
        )
        
        # 尝试保存重复名称的预设
        with pytest.raises(ValueError, match="预设名称 '重复预设' 已存在"):
            await preset_service.save_preset(
                name=name,
                description="第二个预设",
                operations=[sample_operation],
                output_columns=[],
                tags=[],
                is_public=False,
                user_id=user_id
            )
    
    @pytest.mark.asyncio
    async def test_get_preset_by_name(self, preset_service, sample_operation):
        """测试根据名称查找预设"""
        name = "查找测试预设"
        user_id = "user_123"
        
        # 保存预设
        preset_info = await preset_service.save_preset(
            name=name,
            description="查找测试",
            operations=[sample_operation],
            output_columns=[],
            tags=[],
            is_public=False,
            user_id=user_id
        )
        
        # 查找预设
        found_preset = await preset_service.get_preset_by_name(name, user_id)
        assert found_preset is not None
        assert found_preset["name"] == name
        assert found_preset["user_id"] == user_id
        
        # 查找不存在的预设
        not_found = await preset_service.get_preset_by_name("不存在的预设", user_id)
        assert not_found is None
        
        # 其他用户无法找到私有预设
        other_user_result = await preset_service.get_preset_by_name(name, "other_user")
        assert other_user_result is None
    
    @pytest.mark.asyncio
    async def test_get_preset_detail_with_permissions(self, preset_service, sample_operation):
        """测试获取预设详情和权限控制"""
        user_id = "user_123"
        other_user_id = "user_456"
        
        # 保存私有预设
        private_preset = await preset_service.save_preset(
            name="私有预设",
            description="只有创建者可访问",
            operations=[sample_operation],
            output_columns=["u.name"],
            tags=["私有"],
            is_public=False,
            user_id=user_id
        )
        
        # 保存公开预设
        public_preset = await preset_service.save_preset(
            name="公开预设",
            description="所有人可访问",
            operations=[sample_operation],
            output_columns=["u.name"],
            tags=["公开"],
            is_public=True,
            user_id=user_id
        )
        
        # 创建者可以访问私有预设
        private_detail = await preset_service.get_preset_detail(
            private_preset.preset_id, user_id
        )
        assert private_detail is not None
        assert private_detail["name"] == "私有预设"
        
        # 其他用户无法访问私有预设
        private_detail_other = await preset_service.get_preset_detail(
            private_preset.preset_id, other_user_id
        )
        assert private_detail_other is None
        
        # 任何人都可以访问公开预设
        public_detail = await preset_service.get_preset_detail(
            public_preset.preset_id, other_user_id
        )
        assert public_detail is not None
        assert public_detail["name"] == "公开预设"
    
    @pytest.mark.asyncio
    async def test_list_presets_with_filters(self, preset_service, sample_operation):
        """测试预设列表查询和过滤"""
        user_id = "user_123"
        other_user_id = "user_456"
        
        # 创建多个预设用于测试
        presets_data = [
            ("用户预设1", "用户相关功能", ["用户", "查询"], False, user_id),
            ("订单预设1", "订单相关功能", ["订单", "统计"], True, user_id),
            ("用户预设2", "用户分析功能", ["用户", "分析"], False, user_id),
            ("其他用户预设", "其他用户的公开预设", ["公开"], True, other_user_id),
        ]
        
        for name, desc, tags, is_public, uid in presets_data:
            await preset_service.save_preset(
                name=name,
                description=desc,
                operations=[sample_operation],
                output_columns=[],
                tags=tags,
                is_public=is_public,
                user_id=uid
            )
        
        # 测试基本列表查询
        result = await preset_service.list_presets(user_id=user_id)
        assert result["total"] >= 4  # 至少包含4个可访问的预设
        
        # 测试搜索过滤
        search_result = await preset_service.list_presets(
            user_id=user_id, search="用户"
        )
        assert search_result["total"] >= 2
        for preset in search_result["presets"]:
            assert "用户" in preset.name or "用户" in (preset.description or "") or "用户" in preset.tags
        
        # 测试标签过滤
        tag_result = await preset_service.list_presets(
            user_id=user_id, tags=["订单"]
        )
        assert tag_result["total"] >= 1
        for preset in tag_result["presets"]:
            assert "订单" in preset.tags
        
        # 测试公开性过滤
        public_result = await preset_service.list_presets(
            user_id=user_id, is_public=True
        )
        assert public_result["total"] >= 2  # 包含自己的公开预设和其他用户的公开预设
        for preset in public_result["presets"]:
            assert preset.is_public
        
        # 测试分页
        page_result = await preset_service.list_presets(
            user_id=user_id, offset=0, limit=2
        )
        assert len(page_result["presets"]) <= 2
        assert page_result["has_more"] == (page_result["total"] > 2)
        
        # 测试排序
        sorted_result = await preset_service.list_presets(
            user_id=user_id, sort_by="name", sort_order="asc"
        )
        names = [p.name for p in sorted_result["presets"]]
        assert names == sorted(names)
    
    @pytest.mark.asyncio
    async def test_update_preset(self, preset_service, sample_operation):
        """测试更新预设"""
        user_id = "user_123"
        other_user_id = "user_456"
        
        # 创建预设
        preset_info = await preset_service.save_preset(
            name="原始预设",
            description="原始描述",
            operations=[sample_operation],
            output_columns=["u.name"],
            tags=["原始"],
            is_public=False,
            user_id=user_id
        )
        
        # 更新预设
        updated_info = await preset_service.update_preset(
            preset_id=preset_info.preset_id,
            name="更新后预设",
            description="更新后描述",
            operations=[sample_operation],
            output_columns=["u.name", "o.amount"],
            tags=["更新"],
            is_public=True,
            user_id=user_id
        )
        
        # 验证更新结果
        assert updated_info.name == "更新后预设"
        assert updated_info.description == "更新后描述"
        assert updated_info.tags == ["更新"]
        assert updated_info.is_public == True
        assert updated_info.preset_id == preset_info.preset_id
        assert updated_info.created_at == preset_info.created_at  # 创建时间不变
        assert updated_info.updated_at != preset_info.updated_at  # 更新时间改变
        
        # 验证预设确实被更新
        updated_detail = await preset_service.get_preset_detail(
            preset_info.preset_id, user_id
        )
        assert updated_detail["name"] == "更新后预设"
        assert updated_detail["output_columns"] == ["u.name", "o.amount"]
        
        # 其他用户无法更新
        with pytest.raises(ValueError, match="只能更新自己创建的预设"):
            await preset_service.update_preset(
                preset_id=preset_info.preset_id,
                name="恶意更新",
                description="",
                operations=[sample_operation],
                output_columns=[],
                tags=[],
                is_public=False,
                user_id=other_user_id
            )
    
    @pytest.mark.asyncio
    async def test_delete_preset(self, preset_service, sample_operation):
        """测试删除预设"""
        user_id = "user_123"
        other_user_id = "user_456"
        
        # 创建预设
        preset_info = await preset_service.save_preset(
            name="待删除预设",
            description="",
            operations=[sample_operation],
            output_columns=[],
            tags=[],
            is_public=False,
            user_id=user_id
        )
        
        # 验证预设存在
        assert await preset_service.get_preset(preset_info.preset_id) is not None
        
        # 其他用户无法删除
        with pytest.raises(ValueError, match="只能删除自己创建的预设"):
            await preset_service.delete_preset(preset_info.preset_id, other_user_id)
        
        # 创建者可以删除
        await preset_service.delete_preset(preset_info.preset_id, user_id)
        
        # 验证预设已删除
        assert await preset_service.get_preset(preset_info.preset_id) is None
        
        # 再次删除会失败
        with pytest.raises(ValueError, match="不存在"):
            await preset_service.delete_preset(preset_info.preset_id, user_id)
    
    @pytest.mark.asyncio
    async def test_clone_preset(self, preset_service, sample_operation):
        """测试克隆预设"""
        user_id = "user_123"
        other_user_id = "user_456"
        
        # 创建公开预设
        public_preset = await preset_service.save_preset(
            name="公开预设",
            description="可被克隆的预设",
            operations=[sample_operation],
            output_columns=["u.name", "o.amount"],
            tags=["公开", "可克隆"],
            is_public=True,
            user_id=user_id
        )
        
        # 创建私有预设
        private_preset = await preset_service.save_preset(
            name="私有预设",
            description="只有创建者可访问",
            operations=[sample_operation],
            output_columns=["u.name"],
            tags=["私有"],
            is_public=False,
            user_id=user_id
        )
        
        # 克隆公开预设
        cloned_public = await preset_service.clone_preset(
            source_preset_id=public_preset.preset_id,
            new_name="克隆的公开预设",
            user_id=other_user_id
        )
        
        # 验证克隆结果
        assert cloned_public.name == "克隆的公开预设"
        assert cloned_public.user_id == other_user_id
        assert cloned_public.is_public == False  # 克隆的预设默认为私有
        assert "克隆" in cloned_public.tags
        assert cloned_public.usage_count == 0
        
        # 验证克隆的预设内容
        cloned_detail = await preset_service.get_preset_detail(
            cloned_public.preset_id, other_user_id
        )
        assert cloned_detail["output_columns"] == ["u.name", "o.amount"]
        assert len(cloned_detail["operations"]) == 1
        
        # 创建者可以克隆自己的私有预设
        cloned_private = await preset_service.clone_preset(
            source_preset_id=private_preset.preset_id,
            new_name="克隆的私有预设",
            user_id=user_id
        )
        assert cloned_private.name == "克隆的私有预设"
        
        # 其他用户无法克隆私有预设
        with pytest.raises(ValueError, match="不存在或无访问权限"):
            await preset_service.clone_preset(
                source_preset_id=private_preset.preset_id,
                new_name="恶意克隆",
                user_id=other_user_id
            )
        
        # 名称冲突检查
        with pytest.raises(ValueError, match="预设名称 '克隆的公开预设' 已存在"):
            await preset_service.clone_preset(
                source_preset_id=public_preset.preset_id,
                new_name="克隆的公开预设",  # 与已存在的克隆预设同名
                user_id=other_user_id
            )
    
    @pytest.mark.asyncio
    async def test_usage_count_tracking(self, preset_service, sample_operation):
        """测试使用次数跟踪"""
        user_id = "user_123"
        
        # 创建预设
        preset_info = await preset_service.save_preset(
            name="使用计数测试",
            description="",
            operations=[sample_operation],
            output_columns=[],
            tags=[],
            is_public=False,
            user_id=user_id
        )
        
        # 初始使用次数为0
        assert preset_info.usage_count == 0
        
        # 增加使用次数
        await preset_service.increment_usage_count(preset_info.preset_id)
        await preset_service.increment_usage_count(preset_info.preset_id)
        
        # 验证使用次数增加
        updated_preset = await preset_service.get_preset(preset_info.preset_id)
        assert updated_preset["usage_count"] == 2
    
    @pytest.mark.asyncio
    async def test_popular_and_recent_presets(self, preset_service, sample_operation):
        """测试热门预设和最近预设功能"""
        user_id = "user_123"
        
        # 创建多个预设
        preset1 = await preset_service.save_preset(
            name="预设1", description="", operations=[sample_operation],
            output_columns=[], tags=[], is_public=True, user_id=user_id
        )
        
        preset2 = await preset_service.save_preset(
            name="预设2", description="", operations=[sample_operation],
            output_columns=[], tags=[], is_public=True, user_id=user_id
        )
        
        # 增加不同的使用次数
        for _ in range(5):
            await preset_service.increment_usage_count(preset1.preset_id)
        
        for _ in range(2):
            await preset_service.increment_usage_count(preset2.preset_id)
        
        # 测试热门预设
        popular = await preset_service.get_popular_presets(user_id, limit=10)
        assert len(popular) >= 2
        # 验证按使用次数降序排列
        usage_counts = [p.usage_count for p in popular]
        assert usage_counts == sorted(usage_counts, reverse=True)
        
        # 测试最近预设
        recent = await preset_service.get_recent_presets(user_id, limit=10)
        assert len(recent) >= 2
        # 验证按创建时间降序排列（最新的在前）
        created_times = [p.created_at for p in recent]
        assert created_times == sorted(created_times, reverse=True)
    
    @pytest.mark.asyncio
    async def test_preset_templates(self, preset_service):
        """测试预设模板功能"""
        templates = await preset_service.get_preset_templates()
        
        # 验证返回模板列表
        assert isinstance(templates, list)
        assert len(templates) > 0
        
        # 验证模板结构
        for template in templates:
            assert "template_id" in template
            assert "name" in template
            assert "description" in template
            assert "category" in template
            assert "operations" in template
            assert "output_columns" in template
            
            # 验证操作结构
            for operation in template["operations"]:
                assert "left_dataset" in operation
                assert "right_dataset" in operation
                assert "join_type" in operation
                assert "conditions" in operation