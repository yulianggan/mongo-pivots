"""
测试性能监控系统
"""
import pytest
import time
import threading
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

from core.performance_monitor import (
    MetricType, AlertLevel, MetricValue, PerformanceThreshold, Alert,
    MetricCollector, SystemMetricsCollector, AlertManager, PerformanceMonitor,
    get_performance_monitor, monitor_performance
)


class TestMetricValue:
    """测试指标值数据结构"""
    
    def test_metric_value_creation(self):
        """测试指标值创建"""
        metric = MetricValue(
            name="test.metric",
            value=42.5,
            metric_type=MetricType.GAUGE,
            tags={"service": "test"},
            unit="bytes",
            description="Test metric"
        )
        
        assert metric.name == "test.metric"
        assert metric.value == 42.5
        assert metric.metric_type == MetricType.GAUGE
        assert metric.tags == {"service": "test"}
        assert metric.unit == "bytes"
        assert metric.description == "Test metric"
        assert isinstance(metric.timestamp, datetime)
    
    def test_metric_value_to_dict(self):
        """测试指标值转换为字典"""
        metric = MetricValue(
            name="test.metric",
            value=100,
            metric_type=MetricType.COUNTER
        )
        
        result = metric.to_dict()
        
        assert result['name'] == "test.metric"
        assert result['value'] == 100
        assert result['type'] == "counter"
        assert 'timestamp' in result
        assert result['tags'] == {}


class TestPerformanceThreshold:
    """测试性能阈值配置"""
    
    def test_threshold_creation(self):
        """测试阈值创建"""
        threshold = PerformanceThreshold(
            metric_name="cpu.usage",
            warning_threshold=70,
            error_threshold=85,
            critical_threshold=95
        )
        
        assert threshold.metric_name == "cpu.usage"
        assert threshold.warning_threshold == 70
        assert threshold.error_threshold == 85
        assert threshold.critical_threshold == 95
        assert threshold.comparison_operator == ">"
        assert threshold.enabled is True
    
    def test_threshold_check_greater_than(self):
        """测试大于操作符的阈值检查"""
        threshold = PerformanceThreshold(
            metric_name="test.metric",
            warning_threshold=70,
            error_threshold=85,
            critical_threshold=95,
            comparison_operator=">"
        )
        
        assert threshold.check_threshold(50) is None
        assert threshold.check_threshold(75) == AlertLevel.WARNING
        assert threshold.check_threshold(90) == AlertLevel.ERROR
        assert threshold.check_threshold(98) == AlertLevel.CRITICAL
    
    def test_threshold_check_less_than(self):
        """测试小于操作符的阈值检查"""
        threshold = PerformanceThreshold(
            metric_name="availability",
            warning_threshold=90,
            error_threshold=80,
            critical_threshold=70,
            comparison_operator="<"
        )
        
        assert threshold.check_threshold(95) is None
        assert threshold.check_threshold(85) == AlertLevel.WARNING
        assert threshold.check_threshold(75) == AlertLevel.ERROR
        assert threshold.check_threshold(65) == AlertLevel.CRITICAL
    
    def test_threshold_disabled(self):
        """测试禁用的阈值"""
        threshold = PerformanceThreshold(
            metric_name="test.metric",
            warning_threshold=70,
            error_threshold=85,
            critical_threshold=95,
            enabled=False
        )
        
        assert threshold.check_threshold(98) is None


class TestMetricCollector:
    """测试指标收集器"""
    
    def setup_method(self):
        """测试设置"""
        self.collector = MetricCollector(max_history=100)
    
    def test_record_counter(self):
        """测试记录计数器"""
        self.collector.record_counter("test.counter", 5)
        self.collector.record_counter("test.counter", 3)
        
        latest_value = self.collector.get_latest_value("test.counter")
        assert latest_value == 8  # 5 + 3
        
        metrics = self.collector.get_metrics("test.counter")
        assert len(metrics) == 2
        assert all(m.metric_type == MetricType.COUNTER for m in metrics)
    
    def test_record_gauge(self):
        """测试记录测量指标"""
        self.collector.record_gauge("test.gauge", 42.5)
        self.collector.record_gauge("test.gauge", 35.7)
        
        latest_value = self.collector.get_latest_value("test.gauge")
        assert latest_value == 35.7  # 最新值
        
        metrics = self.collector.get_metrics("test.gauge")
        assert len(metrics) == 2
        assert all(m.metric_type == MetricType.GAUGE for m in metrics)
    
    def test_record_histogram(self):
        """测试记录直方图"""
        values = [10, 20, 15, 25, 30]
        for value in values:
            self.collector.record_histogram("test.histogram", value)
        
        metrics = self.collector.get_metrics("test.histogram")
        assert len(metrics) == 5
        assert all(m.metric_type == MetricType.HISTOGRAM for m in metrics)
        
        recorded_values = [m.value for m in metrics]
        assert recorded_values == values
    
    def test_timer_context_manager(self):
        """测试计时器上下文管理器"""
        with self.collector.timer("test.timer"):
            time.sleep(0.01)  # 10ms
        
        latest_value = self.collector.get_latest_value("test.timer")
        assert latest_value is not None
        assert latest_value >= 0.01  # 至少10ms
        assert latest_value < 0.1   # 不应超过100ms
        
        metrics = self.collector.get_metrics("test.timer")
        assert len(metrics) == 1
        assert metrics[0].metric_type == MetricType.TIMER
        assert metrics[0].unit == "seconds"
    
    def test_record_timer_direct(self):
        """测试直接记录计时器"""
        self.collector.record_timer("test.timer", 0.025)
        
        latest_value = self.collector.get_latest_value("test.timer")
        assert latest_value == 0.025
    
    def test_get_statistics(self):
        """测试获取统计信息"""
        values = [10, 20, 15, 25, 30]
        for value in values:
            self.collector.record_gauge("test.stats", value)
        
        stats = self.collector.get_statistics("test.stats")
        
        assert stats['count'] == 5
        assert stats['min'] == 10
        assert stats['max'] == 30
        assert stats['avg'] == 20  # (10+20+15+25+30)/5
        assert stats['sum'] == 100
        assert stats['latest'] == 30
    
    def test_get_statistics_empty(self):
        """测试空指标的统计信息"""
        stats = self.collector.get_statistics("nonexistent.metric")
        assert stats == {}
    
    def test_clear_metrics(self):
        """测试清理指标"""
        self.collector.record_gauge("test.metric1", 10)
        self.collector.record_gauge("test.metric2", 20)
        
        # 清理特定指标
        self.collector.clear_metrics("test.metric1")
        
        assert self.collector.get_latest_value("test.metric1") is None
        assert self.collector.get_latest_value("test.metric2") == 20
        
        # 清理所有指标
        self.collector.clear_metrics()
        
        assert self.collector.get_latest_value("test.metric2") is None
    
    def test_max_history_limit(self):
        """测试历史记录限制"""
        collector = MetricCollector(max_history=5)
        
        # 记录超过限制的指标
        for i in range(10):
            collector.record_gauge("test.metric", i)
        
        metrics = collector.get_metrics("test.metric")
        assert len(metrics) == 5  # 只保留最新的5个
        
        # 验证保留的是最新的值
        values = [m.value for m in metrics]
        assert values == [5, 6, 7, 8, 9]


class TestSystemMetricsCollector:
    """测试系统指标收集器"""
    
    def setup_method(self):
        """测试设置"""
        self.collector = MetricCollector()
        self.system_collector = SystemMetricsCollector(self.collector)
        self.system_collector.collection_interval = 0.1  # 快速测试
    
    @patch('core.performance_monitor.psutil')
    def test_collect_system_metrics(self, mock_psutil):
        """测试收集系统指标"""
        # 模拟psutil返回值
        mock_psutil.cpu_percent.return_value = 45.5
        
        mock_memory = Mock()
        mock_memory.used = 1024*1024*1024  # 1GB
        mock_memory.total = 4*1024*1024*1024  # 4GB
        mock_memory.percent = 25.0
        mock_memory.available = 3*1024*1024*1024  # 3GB
        mock_psutil.virtual_memory.return_value = mock_memory
        
        mock_disk = Mock()
        mock_disk.used = 10*1024*1024*1024  # 10GB
        mock_disk.total = 100*1024*1024*1024  # 100GB
        mock_psutil.disk_usage.return_value = mock_disk
        
        # 收集指标
        self.system_collector._collect_system_metrics()
        
        # 验证CPU指标
        cpu_usage = self.collector.get_latest_value("system.cpu.usage_percent")
        assert cpu_usage == 45.5
        
        # 验证内存指标
        memory_used = self.collector.get_latest_value("system.memory.used_bytes")
        assert memory_used == 1024*1024*1024
        
        memory_percent = self.collector.get_latest_value("system.memory.usage_percent")
        assert memory_percent == 25.0
        
        # 验证磁盘指标
        disk_used = self.collector.get_latest_value("system.disk.used_bytes")
        assert disk_used == 10*1024*1024*1024
        
        disk_percent = self.collector.get_latest_value("system.disk.usage_percent")
        assert disk_percent == 10.0
    
    def test_start_stop_collection(self):
        """测试启动和停止收集"""
        assert not self.system_collector._running
        
        self.system_collector.start()
        assert self.system_collector._running
        assert self.system_collector._thread is not None
        
        time.sleep(0.2)  # 等待收集线程运行
        
        self.system_collector.stop()
        assert not self.system_collector._running


class TestAlertManager:
    """测试告警管理器"""
    
    def setup_method(self):
        """测试设置"""
        self.collector = MetricCollector()
        self.alert_manager = AlertManager(self.collector)
        self.alert_manager.check_interval = 0.1  # 快速测试
    
    def test_add_remove_threshold(self):
        """测试添加和移除阈值"""
        threshold = PerformanceThreshold(
            metric_name="test.metric",
            warning_threshold=70,
            error_threshold=85,
            critical_threshold=95
        )
        
        self.alert_manager.add_threshold(threshold)
        assert "test.metric" in self.alert_manager.thresholds
        
        self.alert_manager.remove_threshold("test.metric")
        assert "test.metric" not in self.alert_manager.thresholds
    
    def test_alert_callback(self):
        """测试告警回调"""
        callback_alerts = []
        
        def test_callback(alert: Alert):
            callback_alerts.append(alert)
        
        self.alert_manager.add_alert_callback(test_callback)
        
        # 添加阈值
        threshold = PerformanceThreshold(
            metric_name="test.metric",
            warning_threshold=70,
            error_threshold=85,
            critical_threshold=95,
            min_samples=1
        )
        self.alert_manager.add_threshold(threshold)
        
        # 记录超过阈值的指标
        self.collector.record_gauge("test.metric", 90)
        
        # 手动检查阈值
        self.alert_manager._check_thresholds()
        
        # 验证回调被调用
        assert len(callback_alerts) == 1
        assert callback_alerts[0].level == AlertLevel.ERROR
        assert callback_alerts[0].value == 90
    
    def test_start_stop_monitoring(self):
        """测试启动和停止监控"""
        assert not self.alert_manager._monitoring
        
        self.alert_manager.start_monitoring()
        assert self.alert_manager._monitoring
        assert self.alert_manager._thread is not None
        
        time.sleep(0.2)  # 等待监控线程运行
        
        self.alert_manager.stop_monitoring()
        assert not self.alert_manager._monitoring
    
    def test_get_active_alerts(self):
        """测试获取活跃告警"""
        # 添加阈值
        threshold = PerformanceThreshold(
            metric_name="test.metric",
            warning_threshold=70,
            error_threshold=85,
            critical_threshold=95,
            min_samples=1
        )
        self.alert_manager.add_threshold(threshold)
        
        # 记录超过阈值的指标
        self.collector.record_gauge("test.metric", 90)
        self.alert_manager._check_thresholds()
        
        active_alerts = self.alert_manager.get_active_alerts()
        assert len(active_alerts) == 1
        assert active_alerts[0].level == AlertLevel.ERROR
    
    def test_resolve_alerts(self):
        """测试解决告警"""
        # 添加阈值
        threshold = PerformanceThreshold(
            metric_name="test.metric",
            warning_threshold=70,
            error_threshold=85,
            critical_threshold=95,
            min_samples=1
        )
        self.alert_manager.add_threshold(threshold)
        
        # 记录超过阈值的指标
        self.collector.record_gauge("test.metric", 90)
        self.alert_manager._check_thresholds()
        
        assert len(self.alert_manager.get_active_alerts()) == 1
        
        # 记录正常指标
        self.collector.record_gauge("test.metric", 50)
        self.alert_manager._check_thresholds()
        
        # 告警应该被解决
        assert len(self.alert_manager.get_active_alerts()) == 0


class TestPerformanceMonitor:
    """测试性能监控主类"""
    
    def setup_method(self):
        """测试设置"""
        self.monitor = PerformanceMonitor({
            'enable_system_metrics': False,
            'enable_alerts': False
        })
    
    def test_record_different_metric_types(self):
        """测试记录不同类型的指标"""
        # 计数器
        self.monitor.record_metric("test.counter", 5, MetricType.COUNTER)
        assert self.monitor.collector.get_latest_value("test.counter") == 5
        
        # 测量值
        self.monitor.record_metric("test.gauge", 42.5, MetricType.GAUGE)
        assert self.monitor.collector.get_latest_value("test.gauge") == 42.5
        
        # 直方图
        self.monitor.record_metric("test.histogram", 100, MetricType.HISTOGRAM)
        assert self.monitor.collector.get_latest_value("test.histogram") == 100
        
        # 计时器
        self.monitor.record_metric("test.timer", 0.025, MetricType.TIMER)
        assert self.monitor.collector.get_latest_value("test.timer") == 0.025
    
    def test_timer_context_manager(self):
        """测试计时器上下文管理器"""
        with self.monitor.timer("test.operation"):
            time.sleep(0.01)
        
        value = self.monitor.collector.get_latest_value("test.operation")
        assert value is not None
        assert value >= 0.01
    
    def test_get_metrics_summary(self):
        """测试获取指标汇总"""
        # 记录一些指标
        self.monitor.record_metric("system.cpu.usage_percent", 45.5, MetricType.GAUGE)
        self.monitor.record_metric("system.memory.usage_percent", 60.0, MetricType.GAUGE)
        
        summary = self.monitor.get_metrics_summary()
        
        assert 'timestamp' in summary
        assert 'system_metrics' in summary
        assert summary['system_metrics']['cpu_usage'] == 45.5
        assert summary['system_metrics']['memory_usage'] == 60.0
        assert 'active_alerts' in summary
        assert 'total_metrics' in summary
    
    def test_get_performance_report(self):
        """测试生成性能报告"""
        # 记录一些指标
        self.monitor.record_metric("system.cpu.usage_percent", 45.5, MetricType.GAUGE)
        
        report = self.monitor.get_performance_report(hours=1)
        
        assert 'timestamp' in report
        assert 'time_range_hours' in report
        assert report['time_range_hours'] == 1
        assert 'metrics' in report
        assert 'alerts' in report
        assert 'summary' in report
    
    def test_add_custom_threshold(self):
        """测试添加自定义阈值"""
        threshold = PerformanceThreshold(
            metric_name="custom.metric",
            warning_threshold=50,
            error_threshold=75,
            critical_threshold=90
        )
        
        self.monitor.add_custom_threshold(threshold)
        
        assert "custom.metric" in self.monitor.alert_manager.thresholds
        assert self.monitor.alert_manager.thresholds["custom.metric"] == threshold
    
    def test_export_metrics(self):
        """测试导出指标"""
        # 记录一些指标
        self.monitor.record_metric("test.metric1", 10, MetricType.GAUGE)
        self.monitor.record_metric("test.metric2", 20, MetricType.COUNTER)
        
        exported = self.monitor.export_metrics(format="json")
        
        assert isinstance(exported, str)
        assert '"timestamp"' in exported
        assert '"metrics"' in exported
        assert '"count"' in exported
        assert '"test.metric1"' in exported
        assert '"test.metric2"' in exported


class TestGlobalFunctions:
    """测试全局函数"""
    
    def test_get_performance_monitor(self):
        """测试获取全局性能监控实例"""
        monitor1 = get_performance_monitor()
        monitor2 = get_performance_monitor()
        
        # 应该返回相同的实例
        assert monitor1 is monitor2
        assert isinstance(monitor1, PerformanceMonitor)
    
    def test_monitor_performance_decorator(self):
        """测试性能监控装饰器"""
        
        @monitor_performance("test_function")
        def test_function(x, y):
            time.sleep(0.01)
            return x + y
        
        # 调用被装饰的函数
        result = test_function(3, 5)
        assert result == 8
        
        # 验证指标被记录
        monitor = get_performance_monitor()
        
        # 检查计时器指标
        timer_value = monitor.collector.get_latest_value("function.test_function")
        assert timer_value is not None
        assert timer_value >= 0.01
        
        # 检查成功计数器
        success_count = monitor.collector.get_latest_value("function.test_function.success")
        assert success_count == 1
    
    def test_monitor_performance_decorator_with_exception(self):
        """测试带异常的性能监控装饰器"""
        
        @monitor_performance("failing_function")
        def failing_function():
            raise ValueError("Test error")
        
        # 调用应该抛出异常
        with pytest.raises(ValueError):
            failing_function()
        
        # 验证错误计数器被记录
        monitor = get_performance_monitor()
        error_count = monitor.collector.get_latest_value("function.failing_function.error")
        assert error_count == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])