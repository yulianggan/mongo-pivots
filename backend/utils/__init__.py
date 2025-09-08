"""
Utils - 通用工具模块
提供数据处理、文件操作等通用功能
"""

from typing import Dict, Any, Union, List

# 导入现有的工具函数
def flatten_value(v: Any) -> Any:
    """扁平化值，处理复杂数据类型"""
    if v is None:
        return None
    if isinstance(v, (list, tuple, set)):
        return ', '.join(map(str, v))
    if isinstance(v, dict):
        return str(v)
    return v


def flatten_doc(doc: Dict[str, Any]) -> Dict[str, Any]:
    """扁平化文档，将复杂值转换为字符串"""
    return {k: flatten_value(v) for k, v in doc.items()}


# 新增的数据源通用工具函数

def validate_connection_params(params: Dict[str, Any], required_params: List[str]) -> None:
    """验证连接参数
    
    Args:
        params: 连接参数字典
        required_params: 必需参数列表
        
    Raises:
        ValueError: 缺少必需参数时抛出
    """
    missing_params = [param for param in required_params if param not in params]
    if missing_params:
        raise ValueError(f"Missing required connection parameters: {missing_params}")


def safe_get_nested_value(data: Dict[str, Any], path: str, default: Any = None) -> Any:
    """安全获取嵌套字典值
    
    Args:
        data: 源数据字典
        path: 点分隔的路径，如 'a.b.c'
        default: 默认值
        
    Returns:
        Any: 获取的值或默认值
    """
    try:
        keys = path.split('.')
        value = data
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        return default


def normalize_column_name(name: str) -> str:
    """规范化列名
    
    Args:
        name: 原始列名
        
    Returns:
        str: 规范化后的列名
    """
    if not name or not isinstance(name, str):
        return "unnamed_column"
    
    # 移除特殊字符，替换为下划线
    import re
    normalized = re.sub(r'[^\w\u4e00-\u9fff]', '_', name)
    
    # 移除连续的下划线
    normalized = re.sub(r'_+', '_', normalized)
    
    # 移除首尾下划线
    normalized = normalized.strip('_')
    
    # 如果为空，使用默认名称
    if not normalized:
        return "unnamed_column"
    
    return normalized


def estimate_memory_usage(
    rows: int, 
    columns: int, 
    avg_string_length: int = 50,
    overhead_factor: float = 1.2
) -> int:
    """估算数据内存使用量
    
    Args:
        rows: 行数
        columns: 列数
        avg_string_length: 平均字符串长度
        overhead_factor: 内存开销因子
        
    Returns:
        int: 估算的内存使用量（字节）
    """
    # 假设一半是数值列（8字节），一半是字符串列
    numeric_columns = columns // 2
    string_columns = columns - numeric_columns
    
    numeric_memory = numeric_columns * rows * 8
    string_memory = string_columns * rows * avg_string_length
    
    total_memory = int((numeric_memory + string_memory) * overhead_factor)
    
    return total_memory


def format_bytes(bytes_size: int) -> str:
    """格式化字节大小显示
    
    Args:
        bytes_size: 字节大小
        
    Returns:
        str: 格式化的大小字符串
    """
    if bytes_size == 0:
        return "0 B"
    
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(bytes_size)
    unit_index = 0
    
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    
    return f"{size:.1f} {units[unit_index]}"


def create_error_context(
    operation: str,
    source_id: str,
    error: Exception,
    additional_info: Dict[str, Any] = None
) -> Dict[str, Any]:
    """创建错误上下文信息
    
    Args:
        operation: 操作名称
        source_id: 数据源ID
        error: 异常对象
        additional_info: 额外信息
        
    Returns:
        Dict[str, Any]: 错误上下文
    """
    context = {
        'operation': operation,
        'source_id': source_id,
        'error_type': type(error).__name__,
        'error_message': str(error),
        'timestamp': __import__('time').time()
    }
    
    if additional_info:
        context.update(additional_info)
    
    return context


# 导出主要接口
__all__ = [
    'flatten_value',
    'flatten_doc', 
    'validate_connection_params',
    'safe_get_nested_value',
    'normalize_column_name',
    'estimate_memory_usage',
    'format_bytes',
    'create_error_context'
]