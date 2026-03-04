#!/usr/bin/env python3
"""
vLLM极限压力测试工具 - 修复版
运行: python extreme_test.py
"""

import requests
import threading
import time
import statistics
from concurrent.futures import ThreadPoolExecutor
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
import json
from datetime import datetime
from dataclasses import dataclass, asdict
import os

# 使用配置文件（确保config.py存在）
from config import BASE_URL, MODEL_NAME

console = Console()

@dataclass
class CrashPoint:
    """服务器崩溃点记录"""
    concurrent: int
    success_rate: float
    avg_latency: float
    timestamp: str
    error_message: str = ""
    peak_memory: float = 0
    peak_cpu: float = 0

class ExtremeTester:
    def __init__(self):
        self.server_url = BASE_URL  # 从config.py导入
        self.model = MODEL_NAME
        self.crash_point = None
        self.results = []
        self.stop_test = False
        
        # 设置超时和重试
        self.session = requests.Session()
        self.session.mount('http://', requests.adapters.HTTPAdapter(
            max_retries=3,
            pool_connections=100,
            pool_maxsize=100
        ))
    
    def signal_handler(self, signum, frame):
        """处理中断信号"""
        console.print("\n[yellow] 收到中断信号，正在停止测试...[/yellow]")
        self.stop_test = True
    
    def health_check(self) -> bool:
        """健康检查"""
        try:
            response = self.session.get(
                f"{self.server_url}/health",
                timeout=3
            )
            return response.status_code == 200
        except:
            return False
    
    def test_crash_point(self, max_concurrent: int = 2000, step_size: int = 10):
        """
        测试服务器崩溃点
        :param max_concurrent: 最大测试并发数
        :param step_size: 每次增加的并发数
        """
        console.print(f"\n[bold red] 开始极限崩溃点测试 (最大并发: {max_concurrent})[/bold red]")
        
        crash_points = []
        test_start = datetime.now()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("测试中...", total=max_concurrent//step_size)
            
            for concurrent in range(step_size, max_concurrent + 1, step_size):
                if self.stop_test:
                    break
                
                progress.update(task, description=f"并发数: {concurrent}")
                
                # 执行当前并发测试
                success_rate, avg_latency = self._test_concurrent_level(
                    concurrent=concurrent,
                    requests_per_step=20
                )
                
                # 检查服务器状态
                server_ok = self.health_check()
                
                if not server_ok or success_rate < 0.5:
                    crash_point = CrashPoint(
                        concurrent=concurrent,
                        success_rate=success_rate,
                        avg_latency=avg_latency,
                        timestamp=datetime.now().isoformat(),
                        error_message="服务器崩溃" if not server_ok else f"成功率过低: {success_rate:.1%}"
                    )
                    crash_points.append(crash_point)
                    console.print(f"\n[red] 崩溃点: 并发 {concurrent} | 成功率 {success_rate:.1%} | 延迟 {avg_latency:.2f}s[/red]")
                    break
                else:
                    console.print(f"  并发 {concurrent}: 成功率 {success_rate:.1%} | 延迟 {avg_latency:.2f}s")
                
                progress.update(task, advance=1)
                time.sleep(1)  # 短暂休息
        
        # 保存结果
        if crash_points:
            self._save_crash_report(crash_points, test_start)
            return crash_points[0]
        else:
            console.print(f"\n[green] 服务器在 {max_concurrent} 并发下未崩溃[/green]")
            return None
    
    def test_parameter_impact(self):
        """测试不同参数对性能的影响"""
        console.print("\n[cyan] 参数影响测试[/cyan]")
        
        test_cases = [
            # (max_tokens, temperature, 描述)
            (50, 0.1, "短回答+低随机性"),
            (500, 0.1, "长回答+低随机性"),
            (50, 1.5, "短回答+高随机性"),
            (500, 1.5, "长回答+高随机性"),
            (2000, 0.7, "超长回答+中等随机性")
        ]
        
        results = []
        
        for max_tokens, temp, desc in test_cases:
            console.print(f"\n测试: {desc}")
            console.print(f"  max_tokens={max_tokens}, temperature={temp}")
            
            success_rate, avg_latency = self._test_parameter_set(
                max_tokens=max_tokens,
                temperature=temp,
                concurrent=10,
                requests=20
            )
            
            results.append({
                "max_tokens": max_tokens,
                "temperature": temp,
                "description": desc,
                "success_rate": success_rate,
                "avg_latency": avg_latency,
                "qps": 1/avg_latency if avg_latency > 0 else 0
            })
            
            console.print(f"  结果: 成功率 {success_rate:.1%} | 延迟 {avg_latency:.2f}s | QPS {1/avg_latency:.1f}")
        
        self._save_parameter_results(results)
        return results
    
    def test_memory_pressure(self, concurrent: int = 50, duration: int = 60):
        """内存压力测试"""
        console.print(f"\n[red] 内存压力测试 (并发: {concurrent}, 时长: {duration}s)[/red]")
        
        long_text = ("这是一段用于内存压力测试的长文本。" * 50)[:5000]  # ~5KB文本
        results = []
        start_time = time.time()
        
        def memory_worker(worker_id):
            data = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": f"{long_text}\n请总结这段文本的主要内容。请求ID: {worker_id}"
                    }
                ],
                "max_tokens": 1000,
                "temperature": 0.7
            }
            
            try:
                start = time.time()
                r = self.session.post(
                    f"{self.server_url}/v1/chat/completions",
                    json=data,
                    timeout=30
                )
                end = time.time()
                
                return {
                    "success": r.status_code == 200,
                    "latency": end - start,
                    "worker_id": worker_id
                }
            except Exception as e:
                return {
                    "success": False,
                    "latency": 30,
                    "error": str(e),
                    "worker_id": worker_id
                }
        
        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            futures = []
            request_id = 0
            
            while time.time() - start_time < duration and not self.stop_test:
                if len(futures) < concurrent:
                    request_id += 1
                    futures.append(executor.submit(memory_worker, request_id))
                
                # 收集结果
                for future in futures[:]:
                    if future.done():
                        try:
                            results.append(future.result())
                            futures.remove(future)
                        except:
                            pass
                
                # 显示进度
                elapsed = time.time() - start_time
                if results:
                    success_count = sum(1 for r in results if r["success"])
                    console.print(
                        f"  进度: {elapsed:.0f}/{duration}s | "
                        f"成功率: {success_count}/{len(results)} ({success_count/len(results):.1%})",
                        end="\r"
                    )
                
                time.sleep(0.1)
        
        # 分析结果
        if results:
            success_rate = sum(1 for r in results if r["success"]) / len(results)
            avg_latency = statistics.mean(
                r["latency"] for r in results if r["success"]
            ) if any(r["success"] for r in results) else 0
            
            console.print(f"\n 测试完成: 成功率 {success_rate:.1%} | 平均延迟 {avg_latency:.2f}s")
            return {
                "concurrent": concurrent,
                "duration": duration,
                "success_rate": success_rate,
                "avg_latency": avg_latency,
                "total_requests": len(results)
            }
        else:
            console.print("\n 未收集到有效结果")
            return None
    
    def _test_concurrent_level(self, concurrent: int, requests_per_step: int) -> tuple[float, float]:
        """测试指定并发级别"""
        results = []
        
        def worker(request_id):
            data = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": f"并发测试请求 #{request_id}"
                    }
                ],
                "max_tokens": 50,
                "temperature": 0.7
            }
            
            try:
                start = time.time()
                r = self.session.post(
                    f"{self.server_url}/v1/chat/completions",
                    json=data,
                    timeout=10
                )
                end = time.time()
                
                return {
                    "success": r.status_code == 200,
                    "latency": end - start
                }
            except Exception as e:
                return {
                    "success": False,
                    "latency": 10,
                    "error": str(e)
                }
        
        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            futures = [
                executor.submit(worker, i)
                for i in range(requests_per_step)
            ]
            
            for future in futures:
                try:
                    results.append(future.result(timeout=15))
                except:
                    results.append({
                        "success": False,
                        "latency": 15,
                        "error": "future timeout"
                    })
        
        # 计算成功率
        success_rate = (
            sum(1 for r in results if r["success"]) / len(results)
            if results else 0
        )
        
        # 计算平均延迟（仅成功请求）
        avg_latency = statistics.mean(
            r["latency"] for r in results if r["success"]
        ) if any(r["success"] for r in results) else 0
        
        return success_rate, avg_latency
    
    def _test_parameter_set(self, max_tokens: int, temperature: float, concurrent: int, requests: int) -> tuple[float, float]:
        """测试特定参数组合"""
        results = []
        
        def worker(request_id):
            data = {
                "model": self.model,
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
                start = time.time()
                r = self.session.post(
                    f"{self.server_url}/v1/chat/completions",
                    json=data,
                    timeout=30
                )
                end = time.time()
                
                return {
                    "success": r.status_code == 200,
                    "latency": end - start
                }
            except Exception as e:
                return {
                    "success": False,
                    "latency": 30,
                    "error": str(e)
                }
        
        with ThreadPoolExecutor(max_workers=concurrent) as executor:
            futures = [
                executor.submit(worker, i)
                for i in range(requests)
            ]
            
            for future in futures:
                try:
                    results.append(future.result(timeout=35))
                except:
                    results.append({
                        "success": False,
                        "latency": 35,
                        "error": "future timeout"
                    })
        
        # 计算统计
        success_rate = (
            sum(1 for r in results if r["success"]) / len(results)
            if results else 0
        )
        
        avg_latency = statistics.mean(
            r["latency"] for r in results if r["success"]
        ) if any(r["success"] for r in results) else 0
        
        return success_rate, avg_latency
    
    def _save_crash_report(self, crash_points: list[CrashPoint], test_start: datetime):
        """保存崩溃报告"""
        os.makedirs("results", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"results/crash_report_{timestamp}.json"
        
        report = {
            "test_start": test_start.isoformat(),
            "test_end": datetime.now().isoformat(),
            "crash_points": [asdict(cp) for cp in crash_points],
            "recommendations": {
                "max_safe_concurrent": max(1, crash_points[0].concurrent - 10),
                "optimal_concurrent": max(1, crash_points[0].concurrent // 2),
                "action_items": [
                    "增加服务器资源" if crash_points[0].concurrent < 100 else "优化模型配置",
                    "设置并发限制",
                    "监控内存使用"
                ]
            }
        }
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        console.print(f"\n 崩溃报告已保存: [green]{filename}[/green]")
    
    def _save_parameter_results(self, results: list[dict]):
        """保存参数测试结果"""
        os.makedirs("results", exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"results/parameter_results_{timestamp}.json"
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        
        console.print(f"\n 参数测试结果已保存: [green]{filename}[/green]")

def main():
    """主函数"""
    import signal
    
    console.print("[bold red]🔥 vLLM极限压力测试工具[/bold red]")
    console.print("=" * 50)
    console.print(f"服务器: [cyan]{BASE_URL}[/cyan]")
    console.print(f"模型: [cyan]{MODEL_NAME}[/cyan]")
    
    # 检查连接
    tester = ExtremeTester()
    if not tester.health_check():
        console.print("\n[red] 无法连接到服务器[/red]")
        console.print("请检查:")
        console.print(f"1. 服务器地址: {BASE_URL}")
        console.print("2. 防火墙设置")
        console.print("3. vLLM服务是否运行")
        return
    
    console.print("\n[green] 服务器连接正常[/green]")
    
    # 注册信号处理器
    signal.signal(signal.SIGINT, tester.signal_handler)
    
    # 选择测试模式
    console.print("\n[bold]请选择测试模式:[/bold]")
    console.print("1. 极限崩溃点测试")
    console.print("2. 参数影响测试")
    console.print("3. 内存压力测试")
    console.print("4. 完整测试套件")
    
    try:
        choice = input("\n选择 (1-4): ").strip()
    except KeyboardInterrupt:
        console.print("\n[yellow] 测试已取消[/yellow]")
        return
    
    try:
        if choice == "1":
            max_conc = input("最大并发数 (默认2000): ").strip()
            max_conc = int(max_conc) if max_conc else 2000
            tester.test_crash_point(max_conc)
        elif choice == "2":
            tester.test_parameter_impact()
        elif choice == "3":
            conc = input("并发数 (默认50): ").strip()
            conc = int(conc) if conc else 50
            duration = input("持续时间秒 (默认60): ").strip()
            duration = int(duration) if duration else 60
            tester.test_memory_pressure(conc, duration)
        elif choice == "4":
            console.print("\n[cyan] 运行完整测试套件[/cyan]")
            
            # 崩溃点测试
            console.print("\n[bold red]阶段1: 极限崩溃点测试[/bold red]")
            crash_point = tester.test_crash_point(300)
            
            # 参数测试
            console.print("\n[bold cyan]阶段2: 参数影响测试[/bold cyan]")
            tester.test_parameter_impact()
            
            # 内存测试
            console.print("\n[bold magenta]阶段3: 内存压力测试[/bold magenta]")
            tester.test_memory_pressure(30, 30)
        else:
            console.print("[yellow]使用默认崩溃点测试[/yellow]")
            tester.test_crash_point()
    except Exception as e:
        console.print(f"\n[red] 测试过程中发生错误: {e}[/red]")
    finally:
        console.print("\n[green] 测试完成！[/green]")

if __name__ == "__main__":
    main()