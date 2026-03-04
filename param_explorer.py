#!/usr/bin/env python3
"""
参数探索脚本
测试不同参数组合对服务器稳定性的影响
"""

import itertools
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List
import pandas as pd
from rich.console import Console
from rich.progress import Progress
from rich.table import Table
import requests

from config import *
from stress_tester import StressTester, TestResult

console = Console()

@dataclass
class ParamCombination:
    """参数组合"""
    max_tokens: int
    temperature: float
    concurrent: int
    batch_size: int

class ParamExplorer:
    """参数探索器"""
    
    def __init__(self):
        self.tester = StressTester()
        self.results = []
    
    def explore_parameters(self, 
                          max_tokens_range: List[int] = None,
                          temperature_range: List[float] = None,
                          concurrent_range: List[int] = None,
                          batch_size_range: List[int] = None):
        """
        探索参数空间
        """
        # 使用默认范围
        if max_tokens_range is None:
            max_tokens_range = [10, 50, 100, 200, 500]
        if temperature_range is None:
            temperature_range = [0.1, 0.5, 1.0, 1.5]
        if concurrent_range is None:
            concurrent_range = [1, 5, 10, 20]
        if batch_size_range is None:
            batch_size_range = [1, 2, 5]
        
        console.print("[cyan]🔬 开始参数空间探索[/cyan]")
        console.print(f"max_tokens: {max_tokens_range}")
        console.print(f"temperature: {temperature_range}")
        console.print(f"concurrent: {concurrent_range}")
        console.print(f"batch_size: {batch_size_range}")
        
        # 生成所有参数组合
        all_combinations = list(itertools.product(
            max_tokens_range,
            temperature_range,
            concurrent_range,
            batch_size_range
        ))
        
        console.print(f"\n📊 总共 {len(all_combinations)} 个参数组合需要测试")
        
        # 限制测试数量
        if len(all_combinations) > 20:
            console.print("[yellow]⚠️  参数组合过多，将随机选择20个进行测试[/yellow]")
            import random
            random.shuffle(all_combinations)
            all_combinations = all_combinations[:20]
        
        with Progress() as progress:
            task = progress.add_task("测试参数组合...", total=len(all_combinations))
            
            for combo in all_combinations:
                if self.tester.stop_test:
                    break
                
                max_tokens, temperature, concurrent, batch_size = combo
                
                progress.console.print(f"\n测试组合: tokens={max_tokens}, temp={temperature}, "
                                     f"concurrent={concurrent}, batch={batch_size}")
                
                # 测试当前参数组合
                result = self._test_parameter_combo(
                    max_tokens=max_tokens,
                    temperature=temperature,
                    concurrent=concurrent,
                    batch_size=batch_size
                )
                
                if result:
                    self.results.append(result)
                    
                    # 如果服务器崩溃，停止测试
                    if result.server_crashed:
                        console.print("[red]❌ 服务器崩溃，停止参数探索[/red]")
                        break
                
                progress.update(task, advance=1)
                time.sleep(1)  # 避免请求过快
        
        # 分析结果
        if self.results:
            self._analyze_results()
    
    def _test_parameter_combo(self, 
                             max_tokens: int, 
                             temperature: float, 
                             concurrent: int, 
                             batch_size: int) -> TestResult:
        """
        测试单个参数组合
        """
        total_requests = 20
        results = []
        error_messages = []
        
        try:
            with ThreadPoolExecutor(max_workers=concurrent) as executor:
                futures = []
                for i in range(total_requests):
                    future = executor.submit(
                        self._send_param_request,
                        i + 1,
                        max_tokens,
                        temperature
                    )
                    futures.append(future)
                
                for future in futures:
                    try:
                        result = future.result(timeout=30)
                        results.append(result)
                        if result["error"]:
                            error_messages.append(result["error"])
                    except Exception as e:
                        results.append({
                            "success": False,
                            "latency": 30,
                            "error": str(e)
                        })
            
            # 计算统计
            if results:
                latencies = [r["latency"] for r in results]
                successes = sum(1 for r in results if r["success"])
                
                # 检查服务器是否仍然健康
                server_ok = self.tester.health_check()
                
                result = TestResult(
                    strategy="param_explore",
                    concurrent=concurrent,
                    request_rate=concurrent,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    batch_size=batch_size,
                    total_requests=len(results),
                    successful_requests=successes,
                    failed_requests=len(results) - successes,
                    avg_latency=sum(latencies)/len(latencies) if latencies else 0,
                    max_latency=max(latencies) if latencies else 0,
                    min_latency=min(latencies) if latencies else 0,
                    p95_latency=0,  # 简化计算
                    success_rate=successes/len(results) if results else 0,
                    server_crashed=not server_ok,
                    crash_reason="服务器崩溃" if not server_ok else "",
                    error_messages=error_messages[:5]
                )
                
                return result
        
        except Exception as e:
            console.print(f"[red]测试参数组合时出错: {e}[/red]")
        
        return None
    
    def _send_param_request(self, request_id: int, max_tokens: int, temperature: float) -> Dict:
        """发送参数测试请求"""
        start_time = time.time()
        
        data = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "user", 
                    "content": f"参数测试请求 #{request_id}"
                }
            ],
            "max_tokens": max_tokens,
            "temperature": temperature
        }
        
        try:
            response = requests.post(
                f"{BASE_URL}/v1/chat/completions",
                json=data,
                timeout=30
            )
            end_time = time.time()
            
            if response.status_code == 200:
                return {
                    "success": True,
                    "latency": end_time - start_time,
                    "error": ""
                }
            else:
                return {
                    "success": False,
                    "latency": end_time - start_time,
                    "error": f"HTTP {response.status_code}"
                }
                
        except Exception as e:
            end_time = time.time()
            return {
                "success": False,
                "latency": end_time - start_time,
                "error": str(e)
            }
    
    def _analyze_results(self):
        """分析测试结果"""
        if not self.results:
            return
        
        console.print("\n" + "="*60)
        console.print("[bold cyan]📊 参数探索分析报告[/bold cyan]")
        console.print("="*60)
        
        # 转换为DataFrame便于分析
        import pandas as pd
        df = pd.DataFrame([vars(r) for r in self.results])
        
        # 找出最佳参数组合
        if not df.empty:
            # 按成功率排序
            best_by_success = df.nlargest(3, 'success_rate')
            
            console.print("\n[bold green]🏆 最佳参数组合 (按成功率):[/bold green]")
            for _, row in best_by_success.iterrows():
                console.print(f"  tokens={row['max_tokens']}, temp={row['temperature']}, "
                           f"concurrent={row['concurrent']}: 成功率={row['success_rate']:.1%}")
            
            # 找出导致崩溃的参数
            crash_combinations = df[df['server_crashed']]
            if not crash_combinations.empty:
                console.print("\n[bold red]⚠️  导致崩溃的参数组合:[/bold red]")
                for _, row in crash_combinations.iterrows():
                    console.print(f"  tokens={row['max_tokens']}, temp={row['temperature']}, "
                               f"concurrent={row['concurrent']}")
            
            # 保存结果
            self._save_results(df)
    
    def _save_results(self, df):
        """保存结果"""
        import os
        os.makedirs("results", exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = f"results/param_exploration_{timestamp}.csv"
        json_path = f"results/param_exploration_{timestamp}.json"
        
        df.to_csv(csv_path, index=False, encoding='utf-8')
        df.to_json(json_path, orient='records', force_ascii=False, indent=2)
        
        console.print(f"\n[green]📁 结果已保存:[/green]")
        console.print(f"  CSV: {csv_path}")
        console.print(f"  JSON: {json_path}")

def main():
    """参数探索主函数"""
    explorer = ParamExplorer()
    
    # 检查服务器
    if not explorer.tester.health_check():
        console.print("[red]❌ 服务器不可用[/red]")
        return
    
    console.print("[bold cyan]🔬 vLLM 参数探索工具[/bold cyan]")
    console.print("测试不同参数组合对服务器稳定性的影响")
    
    # 选择探索范围
    console.print("\n请选择探索范围:")
    console.print("1. 快速探索 (少量组合)")
    console.print("2. 详细探索 (更多组合)")
    console.print("3. 自定义范围")
    
    try:
        choice = input("\n请选择 (1-3): ").strip()
    except KeyboardInterrupt:
        console.print("\n👋 已取消")
        return
    
    if choice == "1":
        # 快速探索
        explorer.explore_parameters(
            max_tokens_range=[10, 100, 500],
            temperature_range=[0.1, 0.7, 1.5],
            concurrent_range=[1, 5, 10],
            batch_size_range=[1, 2]
        )
    elif choice == "2":
        # 详细探索
        explorer.explore_parameters(
            max_tokens_range=[10, 50, 100, 200, 500],
            temperature_range=[0.1, 0.3, 0.7, 1.0, 1.5],
            concurrent_range=[1, 2, 5, 10, 20],
            batch_size_range=[1, 2, 5]
        )
    elif choice == "3":
        # 自定义
        print("\n请输入参数范围 (用空格分隔):")
        
        try:
            max_tokens = list(map(int, input("max_tokens: ").split()))
            temperature = list(map(float, input("temperature: ").split()))
            concurrent = list(map(int, input("concurrent: ").split()))
            batch_size = list(map(int, input("batch_size: ").split()))
            
            explorer.explore_parameters(
                max_tokens_range=max_tokens,
                temperature_range=temperature,
                concurrent_range=concurrent,
                batch_size_range=batch_size
            )
        except ValueError:
            console.print("[red]❌ 输入格式错误，使用默认范围[/red]")
            explorer.explore_parameters()
    else:
        console.print("[yellow]使用快速探索[/yellow]")
        explorer.explore_parameters()

if __name__ == "__main__":
    main()