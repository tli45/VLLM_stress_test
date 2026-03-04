#!/usr/bin/env python3
"""
参数调优测试脚本
"""

import requests
import time
import json
from concurrent.futures import ThreadPoolExecutor

def test_parameters(config, concurrent=5, requests_count=10):
    """测试参数组合性能"""
    results = []
    
    def send_request(request_id):
        data = {
            "model": "/home/models/Qwen3-4B",
            "messages": [{"role": "user", "content": f"测试参数 {request_id}"}],
            **config
        }
        
        start = time.time()
        try:
            r = requests.post(
                "http://47.98.186.172:80/v1/chat/completions",
                json=data,
                timeout=30
            )
            end = time.time()
            
            return {
                "success": r.status_code == 200,
                "latency": end - start,
                "config": config
            }
        except:
            return {"success": False, "latency": 30, "config": config}
    
    with ThreadPoolExecutor(max_workers=concurrent) as executor:
        futures = [executor.submit(send_request, i) for i in range(requests_count)]
        for future in futures:
            results.append(future.result())
    
    return results

# 测试不同参数组合
test_cases = [
    {"max_tokens": 1000, "temperature": 0.7},
    {"max_tokens": 1000, "temperature": 0.3},
    {"max_tokens": 1000, "temperature": 0.9},
    {"max_tokens": 2000, "temperature": 0.7},
    {"max_tokens": 500, "temperature": 0.7},
]

for config in test_cases:
    print(f"测试配置: {config}")
    results = test_parameters(config, concurrent=3, requests_count=5)
    success_rate = sum(1 for r in results if r["success"]) / len(results)
    avg_latency = sum(r["latency"] for r in results if r["success"]) / len([r for r in results if r["success"]])
    print(f"  成功率: {success_rate:.1%}, 平均延迟: {avg_latency:.2f}s")
    print()