"""
性能监控配置系统
实现指标收集、性能分析和监控报告功能
"""

import time
import threading
import asyncio
import psutil
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field, asdict
from collections import defaultdict, deque
from enum import Enum
import json
from contextlib import contextmanager


logger = logging.getLogger(__name__)


class MetricType(Enum):
    """指标类型枚举"""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TIMER = "timer"


class AlertLevel(Enum):
    """告警级别枚举"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class MetricValue:
    """指标值数据结构"""
    name: str
    value: Union[int, float]
    metric_type: MetricType
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)
    unit: str = ""
    description: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'name': self.name,
            'value': self.value,
            'type': self.metric_type.value,
            'timestamp': self.timestamp.isoformat(),
            'tags': self.tags,
            'unit': self.unit,
            'description': self.description
        }


@dataclass
class PerformanceThreshold:
    """性能阈值配置"""
    metric_name: str
    warning_threshold: float
    error_threshold: float
    critical_threshold: float
    comparison_operator: str = ">"  # >, <, >=, <=, ==, !=
    time_window_minutes: int = 5
    min_samples: int = 3
    enabled: bool = True
    
    def check_threshold(self, value: float) -> Optional[AlertLevel]:
        """检查阈值违规"""
        if not self.enabled:
            return None
        
        if self._compare_value(value, self.critical_threshold):
            return AlertLevel.CRITICAL
        elif self._compare_value(value, self.error_threshold):
            return AlertLevel.ERROR
        elif self._compare_value(value, self.warning_threshold):
            return AlertLevel.WARNING
        
        return None
    
    def _compare_value(self, value: float, threshold: float) -> bool:
        """比较值和阈值"""
        if self.comparison_operator == ">":
            return value > threshold
        elif self.comparison_operator == "<":
            return value < threshold
        elif self.comparison_operator == ">=":
            return value >= threshold
        elif self.comparison_operator == "<=":
            return value <= threshold
        elif self.comparison_operator == "==":
            return value == threshold
        elif self.comparison_operator == "!=":
            return value != threshold
        return False


@dataclass
class Alert:
    """告警数据结构"""
    id: str
    metric_name: str
    level: AlertLevel
    message: str
    value: float
    threshold: float
    timestamp: datetime = field(default_factory=datetime.now)
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'id': self.id,
            'metric_name': self.metric_name,
            'level': self.level.value,
            'message': self.message,
            'value': self.value,
            'threshold': self.threshold,
            'timestamp': self.timestamp.isoformat(),
            'resolved': self.resolved,
            'resolved_at': self.resolved_at.isoformat() if self.resolved_at else None,
            'metadata': self.metadata
        }


class MetricCollector:
    """指标收集器"""
    
    def __init__(self, max_history: int = 10000):
        self.max_history = max_history
        self._metrics: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_history))
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._timers: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def record_counter(self, name: str, value: float = 1, tags: Optional[Dict[str, str]] = None):
        """记录计数器指标"""
        with self._lock:
            self._counters[name] += value
            metric = MetricValue(
                name=name,
                value=self._counters[name],
                metric_type=MetricType.COUNTER,
                tags=tags or {}
            )
            self._metrics[name].append(metric)
    
    def record_gauge(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """记录测量指标"""
        with self._lock:
            self._gauges[name] = value
            metric = MetricValue(
                name=name,
                value=value,
                metric_type=MetricType.GAUGE,
                tags=tags or {}
            )
            self._metrics[name].append(metric)
    
    def record_histogram(self, name: str, value: float, tags: Optional[Dict[str, str]] = None):
        """记录直方图指标"""
        with self._lock:
            metric = MetricValue(
                name=name,
                value=value,
                metric_type=MetricType.HISTOGRAM,
                tags=tags or {}
            )
            self._metrics[name].append(metric)
    
    @contextmanager
    def timer(self, name: str, tags: Optional[Dict[str, str]] = None):
        """计时器上下文管理器"""
        start_time = time.time()
        try:
            yield
        finally:
            elapsed = time.time() - start_time
            self.record_timer(name, elapsed, tags)
    
    def record_timer(self, name: str, elapsed_seconds: float, tags: Optional[Dict[str, str]] = None):
        """记录计时器指标"""
        with self._lock:
            self._timers[name].append(elapsed_seconds)
            # 保持最近1000个计时样本
            if len(self._timers[name]) > 1000:
                self._timers[name] = self._timers[name][-1000:]
            
            metric = MetricValue(
                name=name,
                value=elapsed_seconds,
                metric_type=MetricType.TIMER,
                tags=tags or {},
                unit="seconds"
            )
            self._metrics[name].append(metric)
    
    def get_metrics(self, name: Optional[str] = None) -> List[MetricValue]:
        """获取指标"""
        with self._lock:
            if name:
                return list(self._metrics.get(name, []))
            
            all_metrics = []
            for metric_list in self._metrics.values():
                all_metrics.extend(metric_list)
            return all_metrics
    
    def get_latest_value(self, name: str) -> Optional[float]:
        """获取最新指标值"""
        with self._lock:
            metrics = self._metrics.get(name, [])
            if metrics:
                return metrics[-1].value
            return None
    
    def get_statistics(self, name: str, time_window_minutes: int = 5) -> Dict[str, float]:
        """获取指标统计信息"""
        with self._lock:
            metrics = self._metrics.get(name, [])
            if not metrics:
                return {}
            
            # 过滤时间窗口内的指标
            cutoff_time = datetime.now() - timedelta(minutes=time_window_minutes)
            recent_metrics = [m for m in metrics if m.timestamp >= cutoff_time]
            
            if not recent_metrics:
                return {}
            
            values = [m.value for m in recent_metrics]
            
            return {
                'count': len(values),
                'min': min(values),
                'max': max(values),
                'avg': sum(values) / len(values),
                'sum': sum(values),
                'latest': values[-1] if values else 0
            }
    
    def clear_metrics(self, name: Optional[str] = None):
        """清理指标"""
        with self._lock:
            if name:
                if name in self._metrics:
                    self._metrics[name].clear()
                if name in self._counters:
                    del self._counters[name]
                if name in self._gauges:
                    del self._gauges[name]
                if name in self._timers:
                    del self._timers[name]
            else:
                self._metrics.clear()
                self._counters.clear()
                self._gauges.clear()
                self._timers.clear()


class SystemMetricsCollector:
    """系统指标收集器"""
    
    def __init__(self, collector: MetricCollector):
        self.collector = collector
        self.collection_interval = 10  # 秒
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self):
        """启动系统指标收集"""
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()
        logger.info("System metrics collection started")
    
    def stop(self):
        """停止系统指标收集"""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("System metrics collection stopped")
    
    def _collect_loop(self):
        """收集循环"""
        while self._running:
            try:
                self._collect_system_metrics()
                time.sleep(self.collection_interval)
            except Exception as e:
                logger.error(f"Error collecting system metrics: {e}")
                time.sleep(self.collection_interval)
    
    def _collect_system_metrics(self):
        """收集系统指标"""
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            self.collector.record_gauge("system.cpu.usage_percent", cpu_percent)
            
            # 内存使用情况
            memory = psutil.virtual_memory()
            self.collector.record_gauge("system.memory.used_bytes", memory.used)
            self.collector.record_gauge("system.memory.total_bytes", memory.total)
            self.collector.record_gauge("system.memory.usage_percent", memory.percent)
            self.collector.record_gauge("system.memory.available_bytes", memory.available)
            
            # 磁盘使用情况
            disk = psutil.disk_usage('/')
            self.collector.record_gauge("system.disk.used_bytes", disk.used)
            self.collector.record_gauge("system.disk.total_bytes", disk.total)
            self.collector.record_gauge("system.disk.usage_percent", disk.used / disk.total * 100)
            
            # 网络IO
            net_io = psutil.net_io_counters()
            if net_io:
                self.collector.record_counter("system.network.bytes_sent", net_io.bytes_sent)
                self.collector.record_counter("system.network.bytes_recv", net_io.bytes_recv)
                self.collector.record_counter("system.network.packets_sent", net_io.packets_sent)
                self.collector.record_counter("system.network.packets_recv", net_io.packets_recv)
            
            # 磁盘IO
            disk_io = psutil.disk_io_counters()
            if disk_io:
                self.collector.record_counter("system.disk.bytes_read", disk_io.read_bytes)
                self.collector.record_counter("system.disk.bytes_write", disk_io.write_bytes)
                self.collector.record_counter("system.disk.reads", disk_io.read_count)
                self.collector.record_counter("system.disk.writes", disk_io.write_count)
            
            # 进程信息
            process = psutil.Process()
            self.collector.record_gauge("process.memory.rss_bytes", process.memory_info().rss)
            self.collector.record_gauge("process.memory.vms_bytes", process.memory_info().vms)
            self.collector.record_gauge("process.cpu.usage_percent", process.cpu_percent())
            self.collector.record_gauge("process.threads.count", process.num_threads())
            
        except Exception as e:
            logger.error(f"Error collecting specific system metrics: {e}")


class AlertManager:
    """告警管理器"""
    
    def __init__(self, collector: MetricCollector):
        self.collector = collector
        self.thresholds: Dict[str, PerformanceThreshold] = {}
        self.alerts: Dict[str, Alert] = {}
        self.alert_callbacks: List[Callable[[Alert], None]] = []
        self._monitoring = False
        self._thread: Optional[threading.Thread] = None
        self.check_interval = 30  # 秒
    
    def add_threshold(self, threshold: PerformanceThreshold):
        """添加性能阈值"""
        self.thresholds[threshold.metric_name] = threshold
        logger.info(f"Added threshold for metric: {threshold.metric_name}")
    
    def remove_threshold(self, metric_name: str):
        """移除性能阈值"""
        if metric_name in self.thresholds:
            del self.thresholds[metric_name]
            logger.info(f"Removed threshold for metric: {metric_name}")
    
    def add_alert_callback(self, callback: Callable[[Alert], None]):
        """添加告警回调"""
        self.alert_callbacks.append(callback)
    
    def start_monitoring(self):
        """启动告警监控"""
        if self._monitoring:
            return
        
        self._monitoring = True
        self._thread = threading.Thread(target=self._monitoring_loop, daemon=True)
        self._thread.start()
        logger.info("Alert monitoring started")
    
    def stop_monitoring(self):
        """停止告警监控"""
        self._monitoring = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("Alert monitoring stopped")
    
    def _monitoring_loop(self):
        """监控循环"""
        while self._monitoring:
            try:
                self._check_thresholds()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Error in alert monitoring: {e}")
                time.sleep(self.check_interval)
    
    def _check_thresholds(self):
        """检查所有阈值"""
        for metric_name, threshold in self.thresholds.items():
            try:
                stats = self.collector.get_statistics(
                    metric_name, 
                    threshold.time_window_minutes
                )
                
                if not stats or stats['count'] < threshold.min_samples:
                    continue
                
                # 使用平均值进行阈值检查
                avg_value = stats['avg']
                alert_level = threshold.check_threshold(avg_value)
                
                if alert_level:
                    self._create_alert(metric_name, alert_level, avg_value, threshold)
                else:
                    # 检查是否需要解决现有告警
                    self._resolve_alerts(metric_name)
                    
            except Exception as e:
                logger.error(f"Error checking threshold for {metric_name}: {e}")
    
    def _create_alert(self, metric_name: str, level: AlertLevel, value: float, threshold: PerformanceThreshold):
        """创建告警"""
        alert_id = f"{metric_name}_{level.value}_{int(time.time())}"
        
        # 检查是否已存在相同的告警
        existing_alert_key = f"{metric_name}_{level.value}"
        if existing_alert_key in self.alerts and not self.alerts[existing_alert_key].resolved:
            return  # 避免重复告警
        
        # 获取对应的阈值
        if level == AlertLevel.CRITICAL:
            threshold_value = threshold.critical_threshold
        elif level == AlertLevel.ERROR:
            threshold_value = threshold.error_threshold
        else:
            threshold_value = threshold.warning_threshold
        
        alert = Alert(
            id=alert_id,
            metric_name=metric_name,
            level=level,
            message=f"Metric {metric_name} {threshold.comparison_operator} {threshold_value} (current: {value:.2f})",
            value=value,
            threshold=threshold_value,
            metadata={
                'threshold_config': asdict(threshold),
                'comparison_operator': threshold.comparison_operator
            }
        )
        
        self.alerts[existing_alert_key] = alert
        
        # 触发回调
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")
        
        logger.warning(f"Alert created: {alert.message}")
    
    def _resolve_alerts(self, metric_name: str):
        """解决告警"""
        resolved_keys = []
        for key, alert in self.alerts.items():
            if alert.metric_name == metric_name and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = datetime.now()
                resolved_keys.append(key)
                logger.info(f"Alert resolved: {alert.message}")
        
        # 清理已解决的告警
        for key in resolved_keys:
            if key in self.alerts:
                del self.alerts[key]
    
    def get_active_alerts(self) -> List[Alert]:
        """获取活跃告警"""
        return [alert for alert in self.alerts.values() if not alert.resolved]
    
    def get_alert_history(self, hours: int = 24) -> List[Alert]:
        """获取告警历史"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        return [
            alert for alert in self.alerts.values() 
            if alert.timestamp >= cutoff_time
        ]


class PerformanceMonitor:
    """性能监控主类"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or self._default_config()
        self.collector = MetricCollector(self.config.get('max_history', 10000))
        self.system_collector = SystemMetricsCollector(self.collector)
        self.alert_manager = AlertManager(self.collector)
        
        self._setup_default_thresholds()
        self._setup_alert_callbacks()
    
    def _default_config(self) -> Dict[str, Any]:
        """默认配置"""
        return {
            'max_history': 10000,
            'system_collection_interval': 10,
            'alert_check_interval': 30,
            'enable_system_metrics': True,
            'enable_alerts': True
        }
    
    def _setup_default_thresholds(self):
        """设置默认阈值"""
        default_thresholds = [
            PerformanceThreshold(
                metric_name="system.cpu.usage_percent",
                warning_threshold=70,
                error_threshold=85,
                critical_threshold=95
            ),
            PerformanceThreshold(
                metric_name="system.memory.usage_percent",
                warning_threshold=80,
                error_threshold=90,
                critical_threshold=95
            ),
            PerformanceThreshold(
                metric_name="system.disk.usage_percent",
                warning_threshold=80,
                error_threshold=90,
                critical_threshold=95
            ),
            PerformanceThreshold(
                metric_name="process.memory.rss_bytes",
                warning_threshold=1024*1024*1024,  # 1GB
                error_threshold=2*1024*1024*1024,  # 2GB
                critical_threshold=4*1024*1024*1024  # 4GB
            )
        ]
        
        for threshold in default_thresholds:
            self.alert_manager.add_threshold(threshold)
    
    def _setup_alert_callbacks(self):
        """设置告警回调"""
        def log_alert(alert: Alert):
            level_map = {
                AlertLevel.INFO: logger.info,
                AlertLevel.WARNING: logger.warning,
                AlertLevel.ERROR: logger.error,
                AlertLevel.CRITICAL: logger.critical
            }
            log_func = level_map.get(alert.level, logger.info)
            log_func(f"Performance Alert: {alert.message}")
        
        self.alert_manager.add_alert_callback(log_alert)
    
    def start(self):
        """启动性能监控"""
        if self.config.get('enable_system_metrics', True):
            self.system_collector.start()
        
        if self.config.get('enable_alerts', True):
            self.alert_manager.start_monitoring()
        
        logger.info("Performance monitoring started")
    
    def stop(self):
        """停止性能监控"""
        self.system_collector.stop()
        self.alert_manager.stop_monitoring()
        logger.info("Performance monitoring stopped")
    
    def record_metric(self, name: str, value: float, metric_type: MetricType = MetricType.GAUGE, 
                      tags: Optional[Dict[str, str]] = None):
        """记录指标"""
        if metric_type == MetricType.COUNTER:
            self.collector.record_counter(name, value, tags)
        elif metric_type == MetricType.GAUGE:
            self.collector.record_gauge(name, value, tags)
        elif metric_type == MetricType.HISTOGRAM:
            self.collector.record_histogram(name, value, tags)
        elif metric_type == MetricType.TIMER:
            self.collector.record_timer(name, value, tags)
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标汇总"""
        return {
            'timestamp': datetime.now().isoformat(),
            'system_metrics': {
                'cpu_usage': self.collector.get_latest_value('system.cpu.usage_percent'),
                'memory_usage': self.collector.get_latest_value('system.memory.usage_percent'),
                'disk_usage': self.collector.get_latest_value('system.disk.usage_percent'),
                'process_memory': self.collector.get_latest_value('process.memory.rss_bytes')
            },
            'active_alerts': len(self.alert_manager.get_active_alerts()),
            'total_metrics': len(self.collector.get_metrics())
        }
    
    def get_performance_report(self, hours: int = 1) -> Dict[str, Any]:
        """生成性能报告"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'time_range_hours': hours,
            'metrics': {},
            'alerts': {
                'active': [alert.to_dict() for alert in self.alert_manager.get_active_alerts()],
                'history': [alert.to_dict() for alert in self.alert_manager.get_alert_history(hours)]
            },
            'summary': self.get_metrics_summary()
        }
        
        # 添加关键指标的统计信息
        key_metrics = [
            'system.cpu.usage_percent',
            'system.memory.usage_percent',
            'system.disk.usage_percent',
            'process.memory.rss_bytes'
        ]
        
        for metric_name in key_metrics:
            stats = self.collector.get_statistics(metric_name, hours * 60)
            if stats:
                report['metrics'][metric_name] = stats
        
        return report
    
    @contextmanager
    def timer(self, name: str, tags: Optional[Dict[str, str]] = None):
        """计时器上下文管理器"""
        with self.collector.timer(name, tags):
            yield
    
    def add_custom_threshold(self, threshold: PerformanceThreshold):
        """添加自定义阈值"""
        self.alert_manager.add_threshold(threshold)
    
    def export_metrics(self, format: str = "json") -> str:
        """导出指标"""
        metrics = self.collector.get_metrics()
        metrics_data = [metric.to_dict() for metric in metrics]
        
        if format == "json":
            return json.dumps({
                'timestamp': datetime.now().isoformat(),
                'metrics': metrics_data,
                'count': len(metrics_data)
            }, indent=2)
        
        # 可以扩展支持其他格式
        return str(metrics_data)


# 全局性能监控实例
_performance_monitor: Optional[PerformanceMonitor] = None


def get_performance_monitor() -> PerformanceMonitor:
    """获取全局性能监控实例"""
    global _performance_monitor
    if _performance_monitor is None:
        _performance_monitor = PerformanceMonitor()
        _performance_monitor.start()
    return _performance_monitor


def is_monitoring_available() -> bool:
    """检查性能监控是否可用"""
    try:
        monitor = get_performance_monitor()
        return monitor is not None
    except Exception:
        return False


# 方便的装饰器
def monitor_performance(metric_name: str, tags: Optional[Dict[str, str]] = None):
    """性能监控装饰器"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            monitor = get_performance_monitor()
            with monitor.timer(f"function.{metric_name}", tags):
                try:
                    result = func(*args, **kwargs)
                    monitor.record_metric(f"function.{metric_name}.success", 1, MetricType.COUNTER, tags)
                    return result
                except Exception as e:
                    monitor.record_metric(f"function.{metric_name}.error", 1, MetricType.COUNTER, tags)
                    raise
        return wrapper
    return decorator