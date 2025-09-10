"""
编码自动检测器
使用chardet检测文件编码，提供置信度和回退策略
"""
import chardet
from typing import Optional, Dict, Any, List, Tuple
import logging
import os


class EncodingDetector:
    """文件编码自动检测器"""
    
    # 常见编码优先级
    COMMON_ENCODINGS = [
        'utf-8',
        'utf-8-sig',  # BOM
        'gbk',
        'gb2312',
        'gb18030',
        'big5',
        'iso-8859-1',
        'latin-1',
        'cp1252',
        'ascii'
    ]
    
    def __init__(self):
        self._logger = logging.getLogger(self.__class__.__name__)
    
    def detect_encoding(
        self, 
        file_path: str, 
        sample_size: int = 10000,
        min_confidence: float = 0.7
    ) -> Dict[str, Any]:
        """检测文件编码
        
        Args:
            file_path: 文件路径
            sample_size: 检测采样大小（字节）
            min_confidence: 最小置信度阈值
            
        Returns:
            Dict[str, Any]: 编码检测结果
                - encoding: 检测到的编码
                - confidence: 置信度 (0-1)
                - method: 检测方法 ('chardet', 'bom', 'fallback')
                - alternatives: 备选编码列表
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # 读取文件样本
        with open(file_path, 'rb') as f:
            raw_data = f.read(sample_size)
        
        if not raw_data:
            return {
                'encoding': 'utf-8',
                'confidence': 1.0,
                'method': 'empty_file',
                'alternatives': []
            }
        
        # 1. 检查BOM
        bom_encoding = self._detect_bom(raw_data)
        if bom_encoding:
            return {
                'encoding': bom_encoding,
                'confidence': 1.0,
                'method': 'bom',
                'alternatives': []
            }
        
        # 2. 使用chardet检测
        chardet_result = self._detect_with_chardet(raw_data, min_confidence)
        if chardet_result['encoding']:
            # 添加验证结果
            chardet_result['validation_passed'] = self.validate_encoding(file_path, chardet_result['encoding'])
            return chardet_result
        
        # 3. 尝试常见编码
        fallback_result = self._detect_with_fallback(raw_data)
        fallback_result['validation_passed'] = self.validate_encoding(file_path, fallback_result['encoding'])
        return fallback_result
    
    def detect_encoding_from_bytes(
        self, 
        data: bytes, 
        min_confidence: float = 0.7
    ) -> Dict[str, Any]:
        """从字节数据检测编码"""
        if not data:
            return {
                'encoding': 'utf-8',
                'confidence': 1.0,
                'method': 'empty_data',
                'alternatives': []
            }
        
        # 1. 检查BOM
        bom_encoding = self._detect_bom(data)
        if bom_encoding:
            return {
                'encoding': bom_encoding,
                'confidence': 1.0,
                'method': 'bom',
                'alternatives': []
            }
        
        # 2. 使用chardet检测
        chardet_result = self._detect_with_chardet(data, min_confidence)
        if chardet_result['encoding']:
            return chardet_result
        
        # 3. 尝试常见编码
        fallback_result = self._detect_with_fallback(data)
        return fallback_result
    
    def _detect_bom(self, data: bytes) -> Optional[str]:
        """检测BOM（字节顺序标记）"""
        if data.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'
        elif data.startswith(b'\xff\xfe'):
            return 'utf-16-le'
        elif data.startswith(b'\xfe\xff'):
            return 'utf-16-be'
        elif data.startswith(b'\xff\xfe\x00\x00'):
            return 'utf-32-le'
        elif data.startswith(b'\x00\x00\xfe\xff'):
            return 'utf-32-be'
        return None
    
    def _detect_with_chardet(
        self, 
        data: bytes, 
        min_confidence: float
    ) -> Dict[str, Any]:
        """使用chardet检测编码"""
        try:
            result = chardet.detect(data)
            encoding = result.get('encoding')
            confidence = result.get('confidence', 0.0)
            
            # 标准化编码名称
            if encoding:
                encoding = self._normalize_encoding(encoding)
            
            # 检查置信度
            if encoding and confidence >= min_confidence:
                # 获取备选方案
                alternatives = self._get_alternatives(data, encoding)
                
                return {
                    'encoding': encoding,
                    'confidence': confidence,
                    'method': 'chardet',
                    'alternatives': alternatives
                }
            else:
                self._logger.warning(
                    f"chardet confidence too low: {confidence:.2f} for {encoding}"
                )
                
        except Exception as e:
            self._logger.error(f"chardet detection failed: {e}")
        
        return {
            'encoding': None,
            'confidence': 0.0,
            'method': 'chardet_failed',
            'alternatives': []
        }
    
    def _detect_with_fallback(self, data: bytes) -> Dict[str, Any]:
        """使用备选编码尝试解码"""
        working_encodings = []
        
        for encoding in self.COMMON_ENCODINGS:
            try:
                decoded = data.decode(encoding)
                # 简单验证：检查是否包含过多控制字符
                if self._is_valid_text(decoded):
                    working_encodings.append(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
        
        if working_encodings:
            # 优先选择UTF-8
            if 'utf-8' in working_encodings:
                primary_encoding = 'utf-8'
            else:
                primary_encoding = working_encodings[0]
            
            return {
                'encoding': primary_encoding,
                'confidence': 0.8,  # 较高的经验置信度
                'method': 'fallback',
                'alternatives': working_encodings[1:] if len(working_encodings) > 1 else []
            }
        
        # 最后回退到latin-1（几乎总是能解码）
        return {
            'encoding': 'latin-1',
            'confidence': 0.1,
            'method': 'last_resort',
            'alternatives': []
        }
    
    def _normalize_encoding(self, encoding: str) -> str:
        """标准化编码名称"""
        encoding = encoding.lower()
        
        # 常见映射
        mapping = {
            'gb2312': 'gbk',  # GBK是GB2312的超集
            'windows-1252': 'cp1252',
            'iso-8859-1': 'latin-1'
        }
        
        return mapping.get(encoding, encoding)
    
    def _get_alternatives(self, data: bytes, primary_encoding: str) -> List[str]:
        """获取备选编码"""
        alternatives = []
        
        for encoding in self.COMMON_ENCODINGS:
            if encoding == primary_encoding:
                continue
            
            try:
                data.decode(encoding)
                alternatives.append(encoding)
                if len(alternatives) >= 3:  # 限制备选数量
                    break
            except (UnicodeDecodeError, LookupError):
                continue
        
        return alternatives
    
    def _is_valid_text(self, text: str, max_control_ratio: float = 0.1) -> bool:
        """验证文本是否合理"""
        if not text:
            return True
        
        # 统计控制字符比例
        control_chars = sum(1 for c in text if ord(c) < 32 and c not in '\t\n\r')
        control_ratio = control_chars / len(text)
        
        return control_ratio <= max_control_ratio
    
    def validate_encoding(self, file_path: str, encoding: str) -> bool:
        """验证编码是否适用于文件"""
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                # 尝试读取前1000个字符
                f.read(1000)
            return True
        except (UnicodeDecodeError, LookupError, IOError):
            return False
    
    def get_file_encoding_info(self, file_path: str) -> Dict[str, Any]:
        """获取文件编码详细信息"""
        result = self.detect_encoding(file_path)
        
        # 添加文件信息
        file_stats = os.stat(file_path)
        result.update({
            'file_size': file_stats.st_size,
            'file_path': file_path,
            'detection_time': file_stats.st_mtime
        })
        
        # 验证检测结果
        if result['encoding']:
            result['validation_passed'] = self.validate_encoding(file_path, result['encoding'])
        else:
            result['validation_passed'] = False
        
        return result


# 全局编码检测器实例
encoding_detector = EncodingDetector()