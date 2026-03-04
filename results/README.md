## 文件说明

### performance_results.csv
- 每次压力测试的详细记录
- 包含并发数、延迟、成功率等指标

### performance_thresholds.json
- 服务器性能阈值配置
- 安全并发数、崩溃点等关键数据

## 使用流程
1. 运行压力测试 → 自动保存到csv_results/
2. 分析结果 → 生成threshold_analysis.csv
3. 查看日志 → 排查问题