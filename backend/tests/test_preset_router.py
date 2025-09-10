"""
预设配置API路由测试

测试所有预设相关的API端点，包括：
- 保存、更新、删除预设
- 获取预设列表和详情
- 克隆预设
- 预设模板和热门预设
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, AsyncMock

from ..api.main import app
from ..models.api.response_models import PresetInfo
from ..services.preset_service import preset_service


class TestPresetRouter:
    """预设路由测试类"""
    
    @pytest.fixture
    def client(self):
        """创建测试客户端"""
        return TestClient(app)
    
    @pytest.fixture
    def mock_user(self):
        """模拟用户"""
        user = Mock()
        user.user_id = "test_user_123"
        return user
    
    @pytest.fixture(autouse=True)
    def mock_auth(self, monkeypatch, mock_user):
        """模拟身份验证"""
        async def mock_get_current_user():
            return mock_user
        
        monkeypatch.setattr(
            "backend.api.routers.preset.get_current_user",
            mock_get_current_user
        )
    
    @pytest.fixture
    def sample_preset_request(self):
        """示例预设保存请求"""
        return {
            "name": "测试预设",
            "description": "这是一个测试预设",
            "operations": [
                {
                    "left_dataset": {
                        "dataset_id": "ds_users",
                        "alias": "u",
                        "columns": ["id", "name", "email"]
                    },
                    "right_dataset": {
                        "dataset_id": "ds_orders",
                        "alias": "o", 
                        "columns": ["user_id", "amount"]
                    },
                    "join_type": "inner",
                    "conditions": [
                        {
                            "left_column": "id",
                            "right_column": "user_id",
                            "operator": "="
                        }
                    ]
                }
            ],
            "output_columns": ["u.name", "o.amount"],
            "tags": ["测试", "用户订单"],
            "is_public": False
        }
    
    def test_save_preset_success(self, client, sample_preset_request, mock_user):
        """测试成功保存预设"""
        response = client.post("/preset/save", json=sample_preset_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "预设 '测试预设' 保存成功" in data["message"]
        assert "preset" in data
        
        preset = data["preset"]
        assert preset["name"] == "测试预设"
        assert preset["user_id"] == mock_user.user_id
        assert preset["is_public"] == False
        assert preset["tags"] == ["测试", "用户订单"]
        assert preset["usage_count"] == 0
        assert "preset_id" in preset
    
    def test_save_preset_validation_error(self, client):
        """测试保存预设时的验证错误"""
        # 空名称
        invalid_request = {
            "name": "",
            "operations": [],
            "is_public": False
        }
        
        response = client.post("/preset/save", json=invalid_request)
        assert response.status_code == 422  # 验证错误
    
    def test_save_preset_duplicate_name(self, client, sample_preset_request, monkeypatch):
        """测试保存重复名称预设"""
        # 模拟服务抛出ValueError
        async def mock_save_preset(*args, **kwargs):
            raise ValueError("预设名称 '测试预设' 已存在")
        
        monkeypatch.setattr(preset_service, "save_preset", mock_save_preset)
        
        response = client.post("/preset/save", json=sample_preset_request)
        assert response.status_code == 422
        data = response.json()
        assert "预设名称 '测试预设' 已存在" in data["error"]["message"]
    
    def test_list_presets_success(self, client, mock_user):
        """测试获取预设列表"""
        response = client.get("/preset/list")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "total" in data
        assert "offset" in data
        assert "limit" in data
        assert "has_more" in data
        assert "presets" in data
        assert isinstance(data["presets"], list)
    
    def test_list_presets_with_filters(self, client):
        """测试带过滤条件的预设列表"""
        params = {
            "search": "用户",
            "tags": ["用户", "订单"],
            "is_public": True,
            "sort_by": "usage_count",
            "sort_order": "desc",
            "offset": 0,
            "limit": 10
        }
        
        response = client.get("/preset/list", params=params)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
    
    def test_list_presets_invalid_sort(self, client):
        """测试无效排序参数"""
        params = {
            "sort_by": "invalid_field",
            "sort_order": "asc"
        }
        
        response = client.get("/preset/list", params=params)
        assert response.status_code == 422
        data = response.json()
        assert "无效的排序字段" in data["error"]["message"]
    
    def test_get_preset_detail_success(self, client, monkeypatch):
        """测试获取预设详情"""
        preset_id = "preset_123"
        
        # 模拟服务返回预设详情
        mock_preset_detail = {
            "preset_id": preset_id,
            "name": "测试预设",
            "description": "测试描述",
            "user_id": "test_user_123",
            "is_public": False,
            "tags": ["测试"],
            "usage_count": 5,
            "created_at": "2025-09-10T10:00:00Z",
            "updated_at": "2025-09-10T10:00:00Z",
            "operations": [
                {
                    "left_dataset": {"dataset_id": "ds_users"},
                    "right_dataset": {"dataset_id": "ds_orders"},
                    "join_type": "inner",
                    "conditions": [{"left_column": "id", "right_column": "user_id"}]
                }
            ],
            "output_columns": ["u.name", "o.amount"]
        }
        
        async def mock_get_preset_detail(preset_id, user_id):
            return mock_preset_detail
        
        async def mock_increment_usage_count(preset_id):
            pass
        
        monkeypatch.setattr(preset_service, "get_preset_detail", mock_get_preset_detail)
        monkeypatch.setattr(preset_service, "increment_usage_count", mock_increment_usage_count)
        
        response = client.get(f"/preset/{preset_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "preset_info" in data
        assert "operations" in data
        assert "output_columns" in data
        assert data["preset_info"]["name"] == "测试预设"
        assert len(data["operations"]) == 1
    
    def test_get_preset_detail_not_found(self, client, monkeypatch):
        """测试获取不存在的预设详情"""
        preset_id = "nonexistent_preset"
        
        async def mock_get_preset_detail(preset_id, user_id):
            return None
        
        monkeypatch.setattr(preset_service, "get_preset_detail", mock_get_preset_detail)
        
        response = client.get(f"/preset/{preset_id}")
        assert response.status_code == 404
        data = response.json()
        assert "Preset" in data["error"]["message"]
        assert "not found" in data["error"]["message"]
    
    def test_update_preset_success(self, client, sample_preset_request, monkeypatch):
        """测试更新预设"""
        preset_id = "preset_123"
        
        # 修改请求数据
        update_request = sample_preset_request.copy()
        update_request["name"] = "更新后的预设"
        update_request["description"] = "更新后的描述"
        
        # 模拟服务返回更新后的预设
        mock_updated_preset = PresetInfo(
            preset_id=preset_id,
            name="更新后的预设",
            description="更新后的描述",
            user_id="test_user_123",
            is_public=False,
            tags=["测试", "用户订单"],
            usage_count=0,
            created_at="2025-09-10T09:00:00Z",
            updated_at="2025-09-10T10:00:00Z"
        )
        
        async def mock_update_preset(*args, **kwargs):
            return mock_updated_preset
        
        monkeypatch.setattr(preset_service, "update_preset", mock_update_preset)
        
        response = client.put(f"/preset/{preset_id}", json=update_request)
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "更新后的预设' 更新成功" in data["message"]
        assert data["preset"]["name"] == "更新后的预设"
    
    def test_update_preset_permission_denied(self, client, sample_preset_request, monkeypatch):
        """测试更新预设权限拒绝"""
        preset_id = "preset_123"
        
        async def mock_update_preset(*args, **kwargs):
            raise ValueError("只能更新自己创建的预设")
        
        monkeypatch.setattr(preset_service, "update_preset", mock_update_preset)
        
        response = client.put(f"/preset/{preset_id}", json=sample_preset_request)
        assert response.status_code == 422
        data = response.json()
        assert "只能更新自己创建的预设" in data["error"]["message"]
    
    def test_delete_preset_success(self, client, monkeypatch):
        """测试删除预设"""
        preset_id = "preset_123"
        
        async def mock_delete_preset(preset_id, user_id):
            pass  # 成功删除，无返回值
        
        monkeypatch.setattr(preset_service, "delete_preset", mock_delete_preset)
        
        response = client.delete(f"/preset/{preset_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert f"预设 {preset_id} 删除成功" in data["message"]
    
    def test_delete_preset_permission_denied(self, client, monkeypatch):
        """测试删除预设权限拒绝"""
        preset_id = "preset_123"
        
        async def mock_delete_preset(preset_id, user_id):
            raise ValueError("只能删除自己创建的预设")
        
        monkeypatch.setattr(preset_service, "delete_preset", mock_delete_preset)
        
        response = client.delete(f"/preset/{preset_id}")
        assert response.status_code == 422
        data = response.json()
        assert "只能删除自己创建的预设" in data["error"]["message"]
    
    def test_clone_preset_success(self, client, monkeypatch):
        """测试克隆预设"""
        preset_id = "preset_123"
        new_name = "克隆的预设"
        
        mock_cloned_preset = PresetInfo(
            preset_id="preset_cloned_456",
            name=new_name,
            description="克隆自预设 preset_123",
            user_id="test_user_123",
            is_public=False,
            tags=["克隆"],
            usage_count=0,
            created_at="2025-09-10T10:00:00Z",
            updated_at="2025-09-10T10:00:00Z"
        )
        
        async def mock_clone_preset(source_preset_id, new_name, user_id):
            return mock_cloned_preset
        
        monkeypatch.setattr(preset_service, "clone_preset", mock_clone_preset)
        
        response = client.post(f"/preset/{preset_id}/clone", json={"new_name": new_name})
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert f"预设 '{new_name}' 克隆成功" in data["message"]
        assert data["preset"]["name"] == new_name
        assert data["preset"]["preset_id"] == "preset_cloned_456"
    
    def test_clone_preset_name_conflict(self, client, monkeypatch):
        """测试克隆预设名称冲突"""
        preset_id = "preset_123"
        new_name = "已存在的预设名"
        
        async def mock_clone_preset(source_preset_id, new_name, user_id):
            raise ValueError(f"预设名称 '{new_name}' 已存在")
        
        monkeypatch.setattr(preset_service, "clone_preset", mock_clone_preset)
        
        response = client.post(f"/preset/{preset_id}/clone", json={"new_name": new_name})
        assert response.status_code == 422
        data = response.json()
        assert f"预设名称 '{new_name}' 已存在" in data["error"]["message"]
    
    def test_get_preset_templates(self, client, monkeypatch):
        """测试获取预设模板"""
        mock_templates = [
            {
                "template_id": "template_inner_join",
                "name": "内连接模板",
                "description": "两表内连接的基础模板",
                "category": "基础连接",
                "operations": [],
                "output_columns": []
            }
        ]
        
        async def mock_get_preset_templates():
            return mock_templates
        
        monkeypatch.setattr(preset_service, "get_preset_templates", mock_get_preset_templates)
        
        response = client.get("/preset/templates")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "获取预设模板成功" in data["message"]
        assert "templates" in data
        assert len(data["templates"]) == 1
        assert data["templates"][0]["name"] == "内连接模板"
    
    def test_get_popular_presets(self, client, mock_user, monkeypatch):
        """测试获取热门预设"""
        mock_presets = [
            PresetInfo(
                preset_id="preset_1",
                name="热门预设1",
                description="最受欢迎的预设",
                user_id=mock_user.user_id,
                is_public=True,
                tags=["热门"],
                usage_count=100,
                created_at="2025-09-10T09:00:00Z",
                updated_at="2025-09-10T10:00:00Z"
            )
        ]
        
        async def mock_get_popular_presets(user_id, limit):
            return mock_presets
        
        monkeypatch.setattr(preset_service, "get_popular_presets", mock_get_popular_presets)
        
        response = client.get("/preset/popular?limit=5")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "获取热门预设成功" in data["message"]
        assert "presets" in data
        assert len(data["presets"]) == 1
        assert data["presets"][0]["name"] == "热门预设1"
        assert data["presets"][0]["usage_count"] == 100
    
    def test_get_recent_presets(self, client, mock_user, monkeypatch):
        """测试获取最近预设"""
        mock_presets = [
            PresetInfo(
                preset_id="preset_1",
                name="最新预设1", 
                description="最近创建的预设",
                user_id=mock_user.user_id,
                is_public=False,
                tags=["最新"],
                usage_count=0,
                created_at="2025-09-10T10:00:00Z",
                updated_at="2025-09-10T10:00:00Z"
            )
        ]
        
        async def mock_get_recent_presets(user_id, limit):
            return mock_presets
        
        monkeypatch.setattr(preset_service, "get_recent_presets", mock_get_recent_presets)
        
        response = client.get("/preset/recent?limit=5")
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "获取最近预设成功" in data["message"]
        assert "presets" in data
        assert len(data["presets"]) == 1
        assert data["presets"][0]["name"] == "最新预设1"
    
    def test_invalid_preset_operations(self, client):
        """测试无效的预设操作验证"""
        invalid_request = {
            "name": "无效预设",
            "description": "包含无效操作的预设",
            "operations": [],  # 空操作列表
            "is_public": False
        }
        
        response = client.post("/preset/save", json=invalid_request)
        assert response.status_code == 422
        data = response.json()
        assert "预设必须包含至少一个连接操作" in data["error"]["message"]
    
    def test_too_many_operations(self, client, sample_preset_request):
        """测试操作数量超限"""
        # 创建超过限制的操作列表
        operation = sample_preset_request["operations"][0]
        sample_preset_request["operations"] = [operation] * 11  # 超过10个限制
        
        response = client.post("/preset/save", json=sample_preset_request)
        assert response.status_code == 422
        data = response.json()
        assert "连接操作数量不能超过10个" in data["error"]["message"]