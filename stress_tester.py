#!/usr/bin/env python3
"""
服务器压力测试脚本 - 修复版
模拟各种极端条件测试服务器稳定性
运行: python stress_tester.py [策略]
"""

import requests
import json
import time
import threading
import sys
import signal
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, asdict
import statistics
import pandas as pd
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.panel import Panel
from rich.live import Live
from rich.text import Text

from config import *

console = Console()

@dataclass
class TestResult:
    """测试结果数据类"""
    strategy: str
    concurrent: int
    request_rate: int
    max_tokens: int
    temperature: float
    batch_size: int
    total_requests: int
    successful_requests: int
    failed_requests: int
    avg_latency: float
    max_latency: float
    min_latency: float
    p95_latency: float
    success_rate: float
    server_crashed: bool
    crash_reason: str = ""
    timestamp: str = ""
    peak_memory: float = 0
    peak_cpu: float = 0
    error_messages: List[str] = None
    
    def __post_init__(self):
        if self.error_messages is None:
            self.error_messages = []
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

class StressTester:
    """压力测试器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "User-Agent": "StressTester/1.0"
        })
        self.results = []
        self.stop_test = False
        self.test_start_time = None
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        """处理中断信号"""
        console.print("\n[yellow]  收到中断信号，正在停止测试...[/yellow]")
        self.stop_test = True
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            response = self.session.get(
                f"{BASE_URL}/health",
                timeout=5
            )
            return response.status_code == 200
        except:
            return False
    
    def send_request(self, request_id: int, params: Dict) -> Dict:
        """
        发送单个请求
        
        Returns:
            Dict包含结果和统计信息
        """
        start_time = time.time()
        error_msg = ""
        success = False
        latency = 0
        
        data = {
            "model": MODEL_NAME,
            "messages": [
                {
                    "role": "user", 
                    "content": f"压力测试请求 #{request_id}，当前时间: {datetime.now().isoformat()}"
                }
            ],
            "max_tokens": params.get("max_tokens", 50),
            "temperature": params.get("temperature", 0.7)
        }
        
        try:
            response = self.session.post(
                f"{BASE_URL}/v1/chat/completions",
                json=data,
                timeout=30
            )
            end_time = time.time()
            latency = end_time - start_time
            
            if response.status_code == 200:
                success = True
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:100]}"
                success = False
                
        except requests.exceptions.Timeout:
            error_msg = "请求超时(30秒)"
            end_time = time.time()
            latency = end_time - start_time
        except requests.exceptions.ConnectionError:
            error_msg = "连接错误(服务器可能已崩溃)"
            end_time = time.time()
            latency = end_time - start_time
        except Exception as e:
            error_msg = f"未知错误: {str(e)}"
            end_time = time.time()
            latency = end_time - start_time
        
        return {
            "success": success,
            "latency": latency,
            "error": error_msg,
            "request_id": request_id
        }
    
    def get_system_metrics(self) -> Dict:
        """获取系统指标"""
        try:
            import psutil
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=0.5)
            
            # 内存使用
            memory = psutil.virtual_memory()
            memory_percent = memory.percent
            
            return {
                "cpu_percent": cpu_percent,
                "memory_percent": memory_percent,
                "memory_used_gb": memory.used / 1024**3
            }
        except:
            return {"cpu_percent": 0, "memory_percent": 0, "memory_used_gb": 0}
    
    def gradual_stress_test(self, 
                           max_concurrent: int = 100,
                           step_size: int = 5,
                           requests_per_step: int = 50) -> TestResult:
        """
        渐进式压力测试
        逐步增加并发数，直到服务器崩溃
        """
        console.print("[cyan] 开始渐进式压力测试[/cyan]")
        console.print(f"目标并发数: {max_concurrent}")
        console.print(f"每步增加: {step_size}个并发")
        console.print(f"每步请求数: {requests_per_step}")
        
        crash_point = None
        crash_reason = ""
        all_results = []
        error_messages = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("测试中...", total=max_concurrent//step_size)
            
            for concurrent in range(step_size, max_concurrent + 1, step_size):
                if self.stop_test:
                    break
                
                progress.update(task, description=f"测试并发数: {concurrent}")
                
                # 执行当前并发级别的测试
                step_results = self._run_threaded_test(
                    concurrent_count=concurrent,
                    total_requests=requests_per_step
                )
                
                all_results.extend(step_results)
                
                # 检查服务器是否崩溃
                server_ok = self.health_check()
                success_rate = sum(1 for r in step_results if r["success"]) / len(step_results)
                
                if not server_ok or success_rate < 0.5:
                    crash_point = concurrent
                    crash_reason = "服务器崩溃" if not server_ok else f"成功率过低: {success_rate:.1%}"
                    console.print(f"[red] 服务器在并发数 {concurrent} 时崩溃: {crash_reason}[/red]")
                    break
                else:
                    avg_latency = statistics.mean(r["latency"] for r in step_results)
                    console.print(f"  并发 {concurrent}: 成功率 {success_rate:.1%}, 平均延迟 {avg_latency:.2f}s")
                
                progress.update(task, advance=1)
                
                # 短暂休息
                if concurrent < max_concurrent:
                    time.sleep(2)
        
        # 计算统计数据
        if all_results:
            latencies = [r["latency"] for r in all_results]
            successes = sum(1 for r in all_results if r["success"])
            errors = [r["error"] for r in all_results if r["error"]]
            
            result = TestResult(
                strategy="gradual",
                concurrent=crash_point or max_concurrent,
                request_rate=step_size,
                max_tokens=50,
                temperature=0.7,
                batch_size=1,
                total_requests=len(all_results),
                successful_requests=successes,
                failed_requests=len(all_results) - successes,
                avg_latency=statistics.mean(latencies) if latencies else 0,
                max_latency=max(latencies) if latencies else 0,
                min_latency=min(latencies) if latencies else 0,
                p95_latency=statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else 0,
                success_rate=successes/len(all_results) if all_results else 0,
                server_crashed=crash_point is not None,
                crash_reason=crash_reason,
                error_messages=errors[:10]  # 只保存前10个错误
            )
            
            return result
        else:
            return None
    
    def spike_stress_test(self, 
                         spike_concurrent: int = 100,
                         spike_duration: int = 10,
                         pre_warm: bool = True) -> TestResult:
        """
        突发流量冲击测试
        模拟突然的大流量冲击
        """
        console.print("[cyan]⚡ 开始突发流量冲击测试[/cyan]")
        console.print(f"突发并发数: {spike_concurrent}")
        console.print(f"持续时间: {spike_duration}秒")
        
        # 预热
        if pre_warm:
            console.print("预热服务器...")
            self._run_threaded_test(concurrent_count=5, total_requests=20)
            time.sleep(2)
        
        all_results = []
        error_messages = []
        start_time = time.time()
        request_counter = 0
        
        with console.status(f"[bold red] 突发流量冲击: {spike_concurrent}并发[/bold red]"):
            while time.time() - start_time < spike_duration and not self.stop_test:
                # 使用多线程发送并发请求
                batch_results = self._run_threaded_test(
                    concurrent_count=spike_concurrent,
                    total_requests=spike_concurrent
                )
                all_results.extend(batch_results)
                
                for result in batch_results:
                    if result["error"]:
                        error_messages.append(result["error"])
        
        # 检查服务器状态
        server_crashed = not self.health_check()
        crash_reason = "服务器崩溃" if server_crashed else ""
        
        if all_results:
            latencies = [r["latency"] for r in all_results]
            successes = sum(1 for r in all_results if r["success"])
            
            result = TestResult(
                strategy="spike",
                concurrent=spike_concurrent,
                request_rate=spike_concurrent,
                max_tokens=100,
                temperature=0.7,
                batch_size=1,
                total_requests=len(all_results),
                successful_requests=successes,
                failed_requests=len(all_results) - successes,
                avg_latency=statistics.mean(latencies) if latencies else 0,
                max_latency=max(latencies) if latencies else 0,
                min_latency=min(latencies) if latencies else 0,
                p95_latency=statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else 0,
                success_rate=successes/len(all_results) if all_results else 0,
                server_crashed=server_crashed,
                crash_reason=crash_reason,
                error_messages=error_messages[:10]
            )
            
            return result
        else:
            return None
    
    def sustained_stress_test(self,
                            concurrent: int = 20,
                            duration: int = 60) -> TestResult:
        """
        持续高负载测试
        保持恒定负载运行一段时间
        """
        console.print("[cyan] 开始持续高负载测试[/cyan]")
        console.print(f"并发数: {concurrent}")
        console.print(f"持续时间: {duration}秒")
        
        all_results = []
        error_messages = []
        start_time = time.time()
        request_counter = 0
        
        # 监控指标
        peak_cpu = 0
        peak_memory = 0
        
        with Progress() as progress:
            task = progress.add_task("持续负载中...", total=duration)
            
            while time.time() - start_time < duration and not self.stop_test:
                # 更新系统指标
                metrics = self.get_system_metrics()
                peak_cpu = max(peak_cpu, metrics["cpu_percent"])
                peak_memory = max(peak_memory, metrics["memory_percent"])
                
                # 发送一批请求
                batch_results = self._run_threaded_test(
                    concurrent_count=concurrent,
                    total_requests=concurrent
                )
                
                all_results.extend(batch_results)
                
                for result in batch_results:
                    if result["error"]:
                        error_messages.append(result["error"])
                
                # 检查服务器是否仍然响应
                if not self.health_check():
                    console.print("[red] 服务器在持续负载测试中崩溃[/red]")
                    break
                
                # 计算当前批次的统计数据
                if batch_results:
                    batch_success = sum(1 for r in batch_results if r["success"])
                    batch_success_rate = batch_success / len(batch_results)
                    avg_latency = statistics.mean(r["latency"] for r in batch_results)
                    
                    progress.console.print(
                        f"  批次: 成功率 {batch_success_rate:.1%}, 延迟 {avg_latency:.2f}s, "
                        f"CPU: {metrics['cpu_percent']:.1f}%, 内存: {metrics['memory_percent']:.1f}%"
                    )
                
                progress.update(task, advance=1)
                time.sleep(1)
        
        # 最终检查
        server_crashed = not self.health_check()
        crash_reason = "服务器在测试过程中崩溃" if server_crashed else ""
        
        if all_results:
            latencies = [r["latency"] for r in all_results]
            successes = sum(1 for r in all_results if r["success"])
            
            result = TestResult(
                strategy="sustained",
                concurrent=concurrent,
                request_rate=concurrent,
                max_tokens=50,
                temperature=0.7,
                batch_size=1,
                total_requests=len(all_results),
                successful_requests=successes,
                failed_requests=len(all_results) - successes,
                avg_latency=statistics.mean(latencies) if latencies else 0,
                max_latency=max(latencies) if latencies else 0,
                min_latency=min(latencies) if latencies else 0,
                p95_latency=statistics.quantiles(latencies, n=20)[18] if len(latencies) >= 20 else 0,
                success_rate=successes/len(all_results) if all_results else 0,
                server_crashed=server_crashed,
                crash_reason=crash_reason,
                peak_cpu=peak_cpu,
                peak_memory=peak_memory,
                error_messages=error_messages[:10]
            )
            
            return result
        else:
            return None
    
    def mixed_stress_test(self) -> TestResult:
        """
        混合模式测试
        结合多种压力模式
        """
        console.print("[cyan] 开始混合模式压力测试[/cyan]")
        
        all_results = []
        error_messages = []
        
        # 第一阶段：渐进式增加
        console.print("\n[bold]阶段1: 渐进式负载[/bold]")
        result1 = self.gradual_stress_test(max_concurrent=30, step_size=5, requests_per_step=20)
        if result1:
            all_results.append(result1)
            if result1.server_crashed:
                return result1
        
        time.sleep(5)
        
        # 第二阶段：持续负载
        console.print("\n[bold]阶段2: 持续负载[/bold]")
        result2 = self.sustained_stress_test(concurrent=15, duration=30)
        if result2:
            all_results.append(result2)
            if result2.server_crashed:
                return result2
        
        time.sleep(5)
        
        # 第三阶段：突发冲击
        console.print("\n[bold]阶段3: 突发冲击[/bold]")
        result3 = self.spike_stress_test(spike_concurrent=50, spike_duration=5)
        if result3:
            all_results.append(result3)
        
        # 合并结果
        if all_results:
            # 取最后一个结果作为最终结果
            final_result = all_results[-1]
            final_result.strategy = "mixed"
            return final_result
        
        return None
    
    def _run_threaded_test(self, concurrent_count: int, total_requests: int) -> List[Dict]:
        """使用多线程运行指定并发的测试"""
        results = []
        threads = []
        results_lock = threading.Lock()
        
        def worker(worker_id: int):
            result = self.send_request(
                worker_id + 1,
                {"max_tokens": 50, "temperature": 0.7}
            )
            with results_lock:
                results.append(result)
        
        # 创建并启动线程
        for i in range(total_requests):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
        
        # 分批启动线程，避免创建过多线程
        batch_size = min(50, concurrent_count)
        for i in range(0, len(threads), batch_size):
            batch = threads[i:i + batch_size]
            
            # 启动批次线程
            for t in batch:
                t.start()
            
            # 等待批次线程完成
            for t in batch:
                t.join(timeout=30)
        
        return results
    
    def save_results(self, result: TestResult, filename: str = None):
        """保存测试结果"""
        import os
        
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"stress_test_result_{timestamp}.json"
        
        # 创建结果目录
        os.makedirs("results", exist_ok=True)
        filepath = os.path.join("results", filename)
        
        # 转换为字典
        result_dict = asdict(result)
        
        # 保存为JSON
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result_dict, f, ensure_ascii=False, indent=2, default=str)
        
        # 也保存为CSV便于分析
        csv_path = os.path.join("results", f"stress_test_results.csv")
        
        # 检查CSV文件是否存在
        if os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            df = pd.concat([df, pd.DataFrame([result_dict])], ignore_index=True)
        else:
            df = pd.DataFrame([result_dict])
        
        df.to_csv(csv_path, index=False, encoding='utf-8')
        
        console.print(f"[green] 结果已保存到: {filepath}[/green]")
        console.print(f"[green] 汇总数据已更新到: {csv_path}[/green]")
    
    def display_results(self, result: TestResult):
        """显示测试结果"""
        if result is None:
            console.print("[red] 测试未产生有效结果[/red]")
            return
        
        console.print("\n" + "="*60)
        console.print("[bold cyan] 压力测试结果报告[/bold cyan]")
        console.print("="*60)
        
        table = Table(title="测试概况", show_header=False)
        table.add_column("指标", style="cyan", width=20)
        table.add_column("值", style="green")
        
        table.add_row("测试策略", result.strategy)
        table.add_row("测试时间", result.timestamp)
        table.add_row("并发数", str(result.concurrent))
        table.add_row("请求速率", f"{result.request_rate}/秒")
        table.add_row("总请求数", str(result.total_requests))
        table.add_row("成功请求数", str(result.successful_requests))
        table.add_row("失败请求数", str(result.failed_requests))
        table.add_row("成功率", f"{result.success_rate:.1%}")
        table.add_row("服务器状态", " 已崩溃" if result.server_crashed else " 正常运行")
        
        if result.server_crashed:
            table.add_row("崩溃原因", result.crash_reason)
        
        console.print(table)
        
        # 性能指标
        perf_table = Table(title="性能指标")
        perf_table.add_column("指标", style="cyan")
        perf_table.add_column("值", style="green")
        perf_table.add_column("说明", style="yellow")
        
        perf_table.add_row("平均延迟", f"{result.avg_latency:.3f}s", "平均响应时间")
        perf_table.add_row("最小延迟", f"{result.min_latency:.3f}s", "最快响应时间")
        perf_table.add_row("最大延迟", f"{result.max_latency:.3f}s", "最慢响应时间")
        perf_table.add_row("P95延迟", f"{result.p95_latency:.3f}s", "95%请求在此时间内")
        perf_table.add_row("QPS", f"{(1/result.avg_latency if result.avg_latency>0 else 0):.1f}", "每秒查询数")
        perf_table.add_row("峰值CPU", f"{result.peak_cpu:.1f}%", "测试期间最高CPU使用率")
        perf_table.add_row("峰值内存", f"{result.peak_memory:.1f}%", "测试期间最高内存使用率")
        
        console.print(perf_table)
        
        # 显示错误信息
        if result.error_messages:
            console.print("\n[bold yellow]  常见错误信息:[/bold yellow]")
            for i, error in enumerate(result.error_messages[:5], 1):
                console.print(f"  {i}. {error}")
        
        # 给出建议
        console.print("\n[bold cyan]💡 优化建议:[/bold yellow]")
        if result.server_crashed:
            console.print(f"   服务器在并发数 {result.concurrent} 时崩溃")
            console.print(f"   建议将最大并发限制在 {max(1, result.concurrent//2)} 以下")
        elif result.success_rate < 0.9:
            console.print(f"    成功率较低 ({result.success_rate:.1%})")
            console.print(f"   建议优化服务器配置或降低并发数")
        elif result.avg_latency > 3:
            console.print(f"    延迟较高 ({result.avg_latency:.1f}s)")
            console.print("   建议优化模型加载或增加计算资源")
        else:
            console.print("   服务器表现良好，可考虑适当增加负载")

def main():
    """主函数"""
    console.print("[bold cyan] vLLM 服务器压力测试工具[/bold cyan]")
    console.print(f"[yellow]目标服务器: {BASE_URL}[/yellow]")
    console.print(f"[yellow]测试模型: {MODEL_NAME}[/yellow]")
    
    # 检查服务器连接
    console.print("\n 检查服务器连接...", end="")
    tester = StressTester()
    if tester.health_check():
        console.print(" 连接成功")
    else:
        console.print(" 连接失败")
        console.print("[red]请检查服务器是否运行，网络是否通畅[/red]")
        return
    
    # 选择测试策略
    console.print("\n[bold cyan]请选择压力测试策略:[/bold cyan]")
    console.print("1. 渐进式压力测试 (逐步增加并发)")
    console.print("2. 突发流量冲击测试 (模拟流量高峰)")
    console.print("3. 持续高负载测试 (长时间稳定负载)")
    console.print("4. 混合模式测试 (综合测试)")
    console.print("5. 自定义参数测试")
    
    try:
        choice = input("\n请选择 (1-5): ").strip()
    except KeyboardInterrupt:
        console.print("\n[yellow] 测试已取消[/yellow]")
        return
    
    result = None
    
    try:
        if choice == "1":
            # 渐进式测试
            max_concurrent = input("最大并发数 (默认100): ").strip()
            max_concurrent = int(max_concurrent) if max_concurrent else 100
            
            result = tester.gradual_stress_test(
                max_concurrent=max_concurrent,
                step_size=5,
                requests_per_step=20
            )
            
        elif choice == "2":
            # 突发冲击测试
            spike_concurrent = input("突发并发数 (默认100): ").strip()
            spike_concurrent = int(spike_concurrent) if spike_concurrent else 100
            
            spike_duration = input("持续时间(秒) (默认10): ").strip()
            spike_duration = int(spike_duration) if spike_duration else 10
            
            result = tester.spike_stress_test(
                spike_concurrent=spike_concurrent,
                spike_duration=spike_duration
            )
            
        elif choice == "3":
            # 持续负载测试
            concurrent = input("并发数 (默认20): ").strip()
            concurrent = int(concurrent) if concurrent else 20
            
            duration = input("持续时间(秒) (默认60): ").strip()
            duration = int(duration) if duration else 60
            
            result = tester.sustained_stress_test(
                concurrent=concurrent,
                duration=duration
            )
            
        elif choice == "4":
            # 混合模式
            result = tester.mixed_stress_test()
            
        elif choice == "5":
            # 自定义参数测试
            print("\n自定义参数测试")
            strategy = input("策略 (gradual/spike/sustained): ").strip()
            concurrent = int(input("并发数: ").strip())
            duration = int(input("持续时间(秒): ").strip())
            
            if strategy == "gradual":
                result = tester.gradual_stress_test(
                    max_concurrent=concurrent,
                    step_size=5,
                    requests_per_step=20
                )
            elif strategy == "spike":
                result = tester.spike_stress_test(
                    spike_concurrent=concurrent,
                    spike_duration=duration
                )
            elif strategy == "sustained":
                result = tester.sustained_stress_test(
                    concurrent=concurrent,
                    duration=duration
                )
            else:
                console.print("[red] 无效的策略[/red]")
                return
        else:
            console.print("[yellow]使用默认渐进式测试[/yellow]")
            result = tester.gradual_stress_test()
        
        # 显示结果
        if result:
            tester.display_results(result)
            tester.save_results(result)
        else:
            console.print("[red] 测试未完成或无结果[/red]")
        
    except KeyboardInterrupt:
        console.print("\n[yellow]  测试被用户中断[/yellow]")
    except Exception as e:
        console.print(f"[red] 测试过程中发生错误: {e}[/red]")
        import traceback
        console.print(traceback.format_exc())
    finally:
        # 最终检查服务器状态
        console.print("\n 最终服务器状态检查...", end="")
        if tester.health_check():
            console.print(" 服务器正常运行")
        else:
            console.print(" 服务器已崩溃或不可用")
        
        console.print("\n 压力测试完成！")

if __name__ == "__main__":
    main()