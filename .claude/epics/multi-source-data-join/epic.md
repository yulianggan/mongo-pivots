---
name: multi-source-data-join
status: backlog
created: 2025-09-08T09:57:42Z
progress: 0%
prd: .claude/prds/multi-source-data-join.md
github: https://github.com/yulianggan/mongo-pivots/issues/1
---


# Epic: multi-source-data-join

## Overview

将现有单源透视工具升级为支持任意多源（Mongo/Excel/CSV）连接的企业级数据分析平台。核心是构建一个高性能的数据连接引擎，支持复杂的时间对齐、去重、空值治理和质量报告，最终产生"分析就绪宽表"(AR Table)无缝集成到现有透视界面。

技术路径：后端采用Polars+Redis架构替换pandas，前端升级到React+TypeScript，保持现有拖拽透视交互不变。

## Architecture Decisions

### Core Technology Stack
- **数据处理引擎**: Polars取代pandas，提供10-100倍性能提升和内存优化
- **缓存层**: Redis用于结果缓存和任务状态管理，TTL=72小时
- **前端升级**: React+TypeScript替换vanilla JavaScript，支持复杂状态管理
- **文件处理**: xlsx2csv流式转换+Polars读取，避免内存溢出
- **API设计**: 保持REST风格，新增SSE用于长任务进度推送

### Data Processing Architecture
```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Data      │    │  Join Engine │    │  AR Table   │
│  Sources    │───▶│   (Polars)   │───▶│  Generator  │
│  (6 max)    │    │              │    │             │
└─────────────┘    └──────────────┘    └─────────────┘
       │                   │                   │
       ▼                   ▼                   ▼
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│ Validation  │    │  Quality     │    │   Redis     │
│   & Dedup   │    │  Reporting   │    │   Cache     │
└─────────────┘    └──────────────┘    └─────────────┘
```

### Performance Strategy
- **分块处理**: 200K行/块，大数据集落地Parquet分片
- **内存护栏**: 容器内存60%限制，硬上限8GB
- **任务队列**: 每用户并发≤2，队列深度≤5
- **智能缓存**: 基于Preset+数据指纹的缓存键生成

## Technical Approach

### Backend Services

#### Data Source Connectors
- **MongoConnector**: 利用aggregation pipeline下推，支持$project/$dateTrunc优化
- **FileConnector**: 统一CSV/Excel处理，自动编码检测和流式解析
- **SchemaInferencer**: 智能类型推断，支持时间格式自动识别

#### Join Engine (Core)
- **JoinPlanner**: 分析连接计划，估算资源消耗和风险
- **DeduplicationEngine**: MD5组合键生成，支持多种去重策略
- **TimeAligner**: 时区转换和粒度对齐，支持窗口连接
- **QualityAnalyzer**: 生成详尽质量报告，包含预警和建议

#### API Endpoints
```python
POST /api/dataset/upload      # 文件上传和注册
POST /api/join/preview        # 连接计划预览
POST /api/join/execute        # 执行连接任务
GET  /api/join/status/:taskId # 任务状态查询
GET  /api/join/result/:resultId # 结果分页获取
POST /api/preset/save         # 保存连接配置
GET  /api/preset/list         # 列出已保存配置
```

### Frontend Components

#### Core UI Components
- **DataSourcePanel**: 数据源管理，支持拖放上传和预览
- **JoinWizard**: 步骤式连接向导，字段映射和配置
- **QualityDashboard**: 实时质量指标展示，告警和建议
- **ProgressTracker**: SSE实时进度显示，可取消操作

#### State Management
- **Redux Toolkit**: 管理复杂的连接状态和用户配置
- **React Query**: API调用缓存和状态同步
- **Virtualized Tables**: 大数据集预览性能优化

#### Integration Points
- **PivotBridge**: AR Table到现有透视组件的适配器
- **ConfigPersistence**: Preset版本管理和共享机制
- **ErrorBoundary**: 全局错误处理和用户友好提示

### Infrastructure

#### Deployment Architecture
- **Backend**: 扩展现有FastAPI，新增Polars+Redis依赖
- **Frontend**: 保持现有Docker构建，升级Node.js基础镜像
- **Cache Layer**: 部署Redis实例，支持持久化和集群
- **File Storage**: 本地文件系统，支持清理策略

#### Performance Monitoring
- **Metrics**: 连接任务耗时、内存峰值、缓存命中率
- **Logging**: 结构化日志，包含任务ID和用户上下文
- **Alerting**: 资源使用超阈值告警机制

## Implementation Strategy

### Phase 1: Core Engine (6 weeks)
- Polars集成和基础连接逻辑
- MongoDB/CSV/Excel数据源适配器
- 基础去重和时间对齐功能
- Redis缓存层实现

### Phase 2: Advanced Features (4 weeks)  
- 复杂JOIN逻辑和质量报告
- 空值治理和错误处理
- API完善和SSE进度推送
- 性能优化和内存控制

### Phase 3: Frontend Upgrade (4 weeks)
- React/TypeScript迁移
- 连接向导和配置界面
- 质量报告可视化
- 现有透视集成测试

### Phase 4: Polish & Launch (2 weeks)
- 端到端测试和性能调优
- 用户文档和培训材料
- 监控和告警部署
- 正式发布和反馈收集

### Risk Mitigation
- **技术风险**: Polars API变更 → 版本锁定+兼容层
- **性能风险**: 内存溢出 → 分块处理+护栏机制
- **兼容性风险**: 前端破坏性变更 → 渐进式迁移
- **数据质量风险**: 连接错误 → 质量报告+人工审核

### Testing Strategy
- **单元测试**: Polars引擎和连接逻辑（90%覆盖率）
- **集成测试**: 端到端数据流测试，多种数据源组合
- **性能测试**: 大数据集压力测试，内存和时间限制验证
- **用户测试**: 真实场景模拟，易用性和错误处理验证

## Task Breakdown Preview

高级任务分类（总计8个主要任务）：

- [ ] **Backend Data Engine**: Polars集成、数据源连接器、基础连接逻辑
- [ ] **Advanced Join Features**: 去重算法、时间对齐、空值处理、质量分析
- [ ] **Caching & Performance**: Redis集成、任务队列、内存管理、性能优化
- [ ] **API Layer**: REST endpoints、SSE进度推送、错误处理、参数验证
- [ ] **Frontend Architecture**: React迁移、状态管理、组件库升级
- [ ] **Join Wizard UI**: 数据源面板、连接配置界面、预览和验证
- [ ] **Quality Dashboard**: 报告可视化、告警展示、用户指导
- [ ] **Integration & Testing**: 透视集成、端到端测试、性能调优

## Dependencies

### External Dependencies
- **Polars**: 0.20.x版本，性能关键依赖
- **Redis**: 6.0+，支持Streams和TTL功能
- **xlsx2csv**: Excel文件流式转换工具
- **React**: 18.x，支持并发特性
- **TypeScript**: 5.x，严格类型检查

### Internal Dependencies
- **Current Pivot Engine**: 需要扩展支持AR Table格式
- **File Upload System**: 需要支持大文件分块上传
- **User Management**: Preset权限和共享机制
- **Monitoring Stack**: 扩展支持新的性能指标

### Team Dependencies
- **Backend Team**: Polars引擎开发、API设计（2人，核心开发）
- **Frontend Team**: React迁移、UI组件开发（1人，专注前端）
- **DevOps Team**: Redis部署、监控配置（共享资源）
- **QA Team**: 测试用例设计、性能验证（共享资源）

## Success Criteria (Technical)

### Performance Benchmarks
- **连接速度**: 100万行×2表 < 30秒，300万行×3表 < 15分钟
- **内存使用**: 峰值 < 容器内存60%，无OOM错误
- **缓存效果**: 相同配置二次执行 < 5秒，缓存命中率 > 70%
- **并发处理**: 支持每用户2个并发任务，队列响应 < 10秒

### Quality Gates
- **代码质量**: 90%测试覆盖率，0个严重安全漏洞
- **API稳定性**: 99.9%可用性，平均响应时间 < 2秒
- **错误处理**: 100%已知错误场景有友好提示
- **数据准确性**: 连接结果与手工验证100%一致

### Acceptance Criteria
- **功能完整性**: PRD中所有核心功能100%实现
- **用户体验**: 学习成本 < 10分钟，满意度 > 4.5/5
- **系统稳定性**: 7×24小时运行无重启，资源泄漏检测通过
- **扩展性**: 支持数据源和连接类型扩展，API向后兼容

## Estimated Effort

### Overall Timeline
- **总计**: 16周（4个月）完整实现
- **MVP**: 10周后可提供基础连接功能
- **Production Ready**: 14周后可正式发布
- **优化完善**: 16周达到企业级稳定性

### Resource Requirements  
- **后端开发**: 2人×16周 = 32人周（核心引擎和API）
- **前端开发**: 1人×12周 = 12人周（UI组件和集成）
- **测试验证**: 0.5人×8周 = 4人周（专项测试）
- **运维支持**: 0.3人×16周 = 5人周（部署和监控）
- **总计**: 53人周 ≈ 13.2人月

### Critical Path Items
1. **Polars引擎集成**（3周）- 阻塞所有后续开发
2. **连接核心逻辑**（4周）- 影响API设计和前端开发  
3. **React架构迁移**（3周）- 前端开发的基础
4. **透视集成适配**（2周）- 用户体验的关键
5. **性能调优验证**（2周）- 发布前必须完成

### 风险缓冲
- 技术风险缓冲：2周（处理未预见的集成问题）
- 测试缓冲：1周（处理发现的质量问题）  
- 发布缓冲：1周（处理生产环境问题）

## Tasks Created
- [ ] #2 - Polars数据引擎集成和基础架构 (parallel: false)
- [ ] #3 - 多数据源连接器开发(Mongo/CSV/Excel) (parallel: false)
- [ ] #4 - 高级连接功能(去重/时间对齐/空值处理) (parallel: true)
- [ ] #5 - Redis缓存系统和性能优化 (parallel: false)
- [ ] #6 - REST API和SSE进度推送开发 (parallel: true  # API开发可以与002-004部分并行)
- [ ] #7 - React/TypeScript前端架构迁移 (parallel: true)
- [ ] #8 - 连接向导UI和质量报告界面 (parallel: false)
- [ ] #9 - 透视集成和端到端测试 (parallel: false)

**Total tasks**:        8
**Parallel tasks**:        3 (can be worked on simultaneously)
**Sequential tasks**: 5 (have dependencies)
**Estimated total effort**: 596 hours
