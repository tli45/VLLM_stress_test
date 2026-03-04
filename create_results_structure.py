#!/usr/bin/env python3
"""
一键创建完整的results目录结构
运行: python create_results_structure.py
"""

import os
import json
import csv
from datetime import datetime

def create_directory_structure():
    """创建目录结构"""
    directories = [
        "results",
        "results/csv_results", 
        "results/json_results",
        "results/logs",
        "results/charts"
    ]
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f" 创建目录: {directory}/")

def create_files():
    """创建所有文件"""
    
    # 1. README文件
    readme_content = """# 压力测试结果目录说明

## 📊 文件结构
## 使用流程
1. 运行压力测试 → 自动保存到csv_results/
2. 分析结果 → 生成threshold_analysis.csv
3. 查看日志 → 排查问题
"""
    
    with open("results/README.md", "w", encoding="utf-8") as f:
        f.write(readme_content)
    print(" 创建 results/README.md")

    # 2. performance_results.csv
    csv_header = [
        "timestamp", "strategy", "concurrent", "request_rate", 
        "max_tokens", "temperature", "batch_size", "total_requests",
        "successful_requests", "failed_requests", "avg_latency", 
        "max_latency", "min_latency", "p95_latency", "success_rate",
        "server_crashed", "crash_reason", "peak_cpu", "peak_memory", "error_messages"
    ]
    
    with open("results/csv_results/performance_results.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(csv_header)
    print(" 创建 results/csv_results/performance_results.csv")

    # 3. threshold_analysis.csv
    threshold_data = [
        ["threshold_type", "concurrent_level", "value", "status", "recommendation"],
        ["max_safe_concurrent", "10", "0.96", "SAFE", "可安全使用"],
        ["warning_threshold", "15", "0.44", "WARNING", "接近崩溃点"],
        ["crash_point", "20", "0.12", "CRASH", "服务器崩溃"],
        ["optimal_performance", "5", "1.0", "OPTIMAL", "最佳性能"]
    ]
    
    with open("results/csv_results/threshold_analysis.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(threshold_data)
    print(" 创建 results/csv_results/threshold_analysis.csv")

    # 4. test_config.json
    test_config = {
        "server_config": {
            "server_ip": "8.136.34.60",
            "server_port": 80,
            "model_name": "/home/models/Qwen3-4B",
            "base_url": "http://8.136.34.60:80"
        },
        "test_strategies": {
            "gradual": {
                "description": "渐进式增加负载",
                "parameters": {
                    "start_concurrent": 1,
                    "max_concurrent": 100,
                    "step_size": 5,
                    "requests_per_step": 20
                }
            }
        },
        "performance_thresholds": {
            "critical": {
                "success_rate": 0.5,
                "avg_latency": 5.0,
                "max_latency": 10.0
            },
            "warning": {
                "success_rate": 0.8, 
                "avg_latency": 3.0,
                "max_latency": 5.0
            },
            "optimal": {
                "success_rate": 0.95,
                "avg_latency": 1.0,
                "max_latency": 2.0
            }
        }
    }
    
    with open("results/json_results/test_config.json", "w", encoding="utf-8") as f:
        json.dump(test_config, f, indent=2, ensure_ascii=False)
    print("✅ 创建 results/json_results/test_config.json")

    # 5. 创建其他JSON文件（简化版）
    performance_thresholds = {
        "summary": {
            "max_safe_concurrent": 0,
            "recommended_concurrent": 0,
            "total_tests": 0
        },
        "crash_points": [],
        "warning_points": []
    }
    
    with open("results/json_results/performance_thresholds.json", "w", encoding="utf-8") as f:
        json.dump(performance_thresholds, f, indent=2, ensure_ascii=False)
    print(" 创建 results/json_results/performance_thresholds.json")

    # 6. 创建日志文件
    with open("results/logs/stress_test.log", "w", encoding="utf-8") as f:
        f.write("# 压力测试日志文件\n")
        f.write(f"# 创建时间: {datetime.now().isoformat()}\n")
    print(" 创建 results/logs/stress_test.log")

    # 7. 创建图表数据文件
    chart_data = {
        "performance_chart": {
            "concurrent_levels": [1, 5, 10, 15, 20],
            "success_rates": [1.0, 1.0, 0.96, 0.76, 0.12],
            "avg_latencies": [0.12, 0.45, 0.78, 3.2, 8.45]
        }
    }
    
    with open("results/charts/chart_data.json", "w", encoding="utf-8") as f:
        json.dump(chart_data, f, indent=2, ensure_ascii=False)
    print(" 创建 results/charts/chart_data.json")

def main():
    """主函数"""
    print(" 开始创建results目录结构...")
    
    try:
        create_directory_structure()
        create_files()
        
        print("\n results目录结构创建完成！")
        
        # 显示目录结构
        print("\n 最终目录结构:")
        for root, dirs, files in os.walk("results"):
            level = root.replace("results", "").count(os.sep)
            indent = " " * 2 * level
            print(f"{indent}{os.path.basename(root)}/")
            subindent = " " * 2 * (level + 1)
            for file in files:
                print(f"{subindent}{file}")
                
    except Exception as e:
        print(f" 创建失败: {e}")

if __name__ == "__main__":
    main()