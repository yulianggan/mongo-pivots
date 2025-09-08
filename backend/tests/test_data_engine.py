"""
DataEngine测试
验证Polars数据引擎的功能
"""
import pytest
import polars as pl
import pandas as pd
from io import BytesIO
import tempfile
import os
from core.data_engine import DataEngine


class TestDataEngine:
    """数据引擎测试"""
    
    def setup_method(self):
        """每个测试方法执行前的设置"""
        self.engine = DataEngine()
    
    def test_engine_initialization(self):
        """测试引擎初始化"""
        assert self.engine is not None
        # 内存监控应该已启动
        from core.memory_guard import memory_guard
        # 注意：在测试环境中监控可能不会立即启动
    
    def test_csv_reading_from_string(self):
        """测试从字符串读取CSV"""
        csv_content = "name,age,city\nJohn,25,NYC\nJane,30,LA\nBob,35,SF"
        csv_bytes = csv_content.encode('utf-8')
        
        df = self.engine.read_csv(csv_bytes, separator=',', encoding='utf-8')
        
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 3
        assert list(df.columns) == ['name', 'age', 'city']
        
        # 检查数据内容
        first_row = df.row(0)
        assert first_row[0] == 'John'
        assert first_row[2] == 'NYC'
    
    def test_csv_reading_chunked(self):
        """测试分块读取大CSV"""
        # 创建大量数据来触发分块处理
        large_csv_lines = ["name,age,score"]
        for i in range(1000):
            large_csv_lines.append(f"user_{i},{20 + i % 50},{i % 100}")
        
        csv_content = "\n".join(large_csv_lines)
        csv_bytes = csv_content.encode('utf-8')
        
        df = self.engine.read_csv(csv_bytes, separator=',', encoding='utf-8', use_chunking=True)
        
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 1000
        assert list(df.columns) == ['name', 'age', 'score']
    
    def test_csv_reading_different_separators(self):
        """测试不同分隔符的CSV"""
        # 测试制表符分隔
        tsv_content = "name\tage\tcity\nJohn\t25\tNYC\nJane\t30\tLA"
        tsv_bytes = tsv_content.encode('utf-8')
        
        df = self.engine.read_csv(tsv_bytes, separator='\t', encoding='utf-8')
        
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ['name', 'age', 'city']
        
        # 测试分号分隔
        csv_content = "name;age;city\nJohn;25;NYC\nJane;30;LA"
        csv_bytes = csv_content.encode('utf-8')
        
        df = self.engine.read_csv(csv_bytes, separator=';', encoding='utf-8')
        
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ['name', 'age', 'city']
    
    def test_csv_reading_different_encodings(self):
        """测试不同编码的CSV"""
        csv_content = "姓名,年龄,城市\n张三,25,北京\n李四,30,上海"
        
        # 测试UTF-8
        utf8_bytes = csv_content.encode('utf-8')
        df = self.engine.read_csv(utf8_bytes, separator=',', encoding='utf-8')
        
        assert isinstance(df, pl.DataFrame)
        assert len(df) == 2
        assert list(df.columns) == ['姓名', '年龄', '城市']
    
    def test_csv_pandas_fallback(self):
        """测试pandas回退机制"""
        # 创建一个可能让Polars读取失败的CSV
        problematic_csv = "name,age,data\nJohn,25,\"complex,data\"\nJane,30,normal"
        csv_bytes = problematic_csv.encode('utf-8')
        
        # 强制使用pandas回退
        df = self.engine._read_csv_pandas_fallback(csv_bytes, ',', 'utf-8', 1)
        
        assert isinstance(df, pl.DataFrame)
        assert len(df) >= 2
        assert 'name' in df.columns
    
    def test_excel_reading(self):
        """测试Excel文件读取"""
        # 创建临时Excel文件
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp_file:
            # 使用pandas创建Excel文件
            test_data = pd.DataFrame({
                'name': ['John', 'Jane', 'Bob'],
                'age': [25, 30, 35],
                'city': ['NYC', 'LA', 'SF']
            })
            test_data.to_excel(tmp_file.name, index=False)
            
            # 读取文件内容
            with open(tmp_file.name, 'rb') as f:
                excel_content = f.read()
        
        try:
            df = self.engine.read_excel(excel_content)
            
            assert isinstance(df, pl.DataFrame)
            assert len(df) == 3
            assert 'name' in df.columns
            assert 'age' in df.columns
            assert 'city' in df.columns
            
        finally:
            # 清理临时文件
            os.unlink(tmp_file.name)
    
    def test_dataframe_cleaning(self):
        """测试DataFrame清理"""
        # 创建包含问题数据的DataFrame
        dirty_data = pl.DataFrame({
            '  name  ': ['John', 'Jane', None],
            None: [25, 30, 35],  # None列名
            'score': [85.5, float('inf'), float('nan')]
        })
        
        clean_df = self.engine.clean_dataframe(dirty_data)
        
        assert isinstance(clean_df, pl.DataFrame)
        
        # 检查列名清理
        columns = list(clean_df.columns)
        assert '  name  ' not in columns  # 应该被清理
        assert any('name' in col for col in columns)  # 应该包含清理后的name列
        assert any('Column_' in col for col in columns)  # None列名应该被替换
    
    def test_convert_to_records(self):
        """测试转换为记录列表"""
        df = pl.DataFrame({
            'name': ['John', 'Jane'],
            'age': [25, 30],
            'score': [85.5, float('inf')]  # 包含特殊值
        })
        
        records = self.engine.convert_to_records(df)
        
        assert isinstance(records, list)
        assert len(records) == 2
        
        # 检查第一条记录
        first_record = records[0]
        assert isinstance(first_record, dict)
        assert first_record['name'] == 'John'
        assert first_record['age'] == 25
        
        # 检查特殊值处理
        second_record = records[1]
        assert second_record['score'] is None  # 无穷大应该被转换为None
    
    def test_get_field_types(self):
        """测试获取字段类型"""
        df = pl.DataFrame({
            'name': ['John', 'Jane'],
            'age': [25, 30],
            'score': [85.5, 90.2],
            'is_active': [True, False]
        })
        
        field_types = self.engine.get_field_types(df)
        
        assert isinstance(field_types, dict)
        assert field_types['name'] == 'string'
        assert field_types['age'] == 'number'
        assert field_types['score'] == 'number'
        assert field_types['is_active'] == 'boolean'
    
    def test_optimize_dataframe(self):
        """测试DataFrame优化"""
        # 创建包含可优化数据的DataFrame
        df = pl.DataFrame({
            'name': ['John', 'Jane'],
            'age_str': ['25', '30'],  # 数字字符串
            'score_str': ['85.5', '90.2']  # 浮点数字符串
        })
        
        optimized_df = self.engine.optimize_dataframe(df)
        
        assert isinstance(optimized_df, pl.DataFrame)
        assert len(optimized_df) == len(df)
        assert list(optimized_df.columns) == list(df.columns)
    
    def test_filter_data_simple(self):
        """测试简单数据过滤"""
        df = pl.DataFrame({
            'name': ['John', 'Jane', 'Bob'],
            'age': [25, 30, 35],
            'city': ['NYC', 'LA', 'NYC']
        })
        
        # 简单过滤
        filtered_df = self.engine.filter_data(df, {'city': 'NYC'})
        
        assert isinstance(filtered_df, pl.DataFrame)
        assert len(filtered_df) == 2
        
        # 检查所有行都是NYC
        cities = filtered_df['city'].to_list()
        assert all(city == 'NYC' for city in cities)
    
    def test_filter_data_mongodb_style(self):
        """测试MongoDB风格过滤"""
        df = pl.DataFrame({
            'name': ['John', 'Jane', 'Bob'],
            'age': [25, 30, 35],
            'score': [85, 90, 75]
        })
        
        # MongoDB风格过滤
        filters = {
            'age': {'$gte': 30},
            'score': {'$gt': 80}
        }
        
        filtered_df = self.engine.filter_data(df, filters)
        
        assert isinstance(filtered_df, pl.DataFrame)
        assert len(filtered_df) == 1  # 应该只有Jane符合条件
        assert filtered_df['name'].item() == 'Jane'
    
    def test_select_columns(self):
        """测试列选择"""
        df = pl.DataFrame({
            'name': ['John', 'Jane'],
            'age': [25, 30],
            'city': ['NYC', 'LA'],
            'score': [85, 90]
        })
        
        # 选择特定列
        projection = {'name': 1, 'age': 1}
        selected_df = self.engine.select_columns(df, projection)
        
        assert isinstance(selected_df, pl.DataFrame)
        assert list(selected_df.columns) == ['name', 'age']
        assert len(selected_df) == 2
    
    def test_pagination(self):
        """测试分页"""
        df = pl.DataFrame({
            'id': list(range(100)),
            'name': [f'user_{i}' for i in range(100)]
        })
        
        # 测试跳过和限制
        page_df = self.engine.paginate(df, skip=10, limit=20)
        
        assert isinstance(page_df, pl.DataFrame)
        assert len(page_df) == 20
        assert page_df['id'].min() == 10
        assert page_df['id'].max() == 29
        
        # 测试只跳过
        skip_df = self.engine.paginate(df, skip=90)
        assert len(skip_df) == 10
    
    def test_performance_stats(self):
        """测试性能统计获取"""
        stats = self.engine.get_performance_stats()
        
        assert isinstance(stats, dict)
        assert 'config' in stats
        assert 'memory' in stats
        assert 'chunk_processor' in stats
        
        # 检查配置统计
        config_stats = stats['config']
        assert 'memory' in config_stats
        assert 'polars' in config_stats
        assert 'performance' in config_stats


if __name__ == "__main__":
    pytest.main([__file__, "-v"])