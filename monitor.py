venv\Scripts\activate#!/usr/bin/env python3
"""
实时监控脚本
在压力测试期间监控服务器状态
"""

import time
import psutil
import requests
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from threading import Thread
import json

from config import *

console = Console()

class ServerMonitor:
    """服务器监控器"""
    
    def __init__(self, server_url: str):
        self.server_url = server_url
        self.metrics_history = []
        self.max_history = 100
        self.running = False
        
    def start(self):
        """开始监控"""
        self.running = True
        self.thread = Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """停止监控"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
    
    def _monitor_loop(self):
        """监控循环"""
        while self.running:
            metrics = self.collect_metrics()
            self.metrics_history.append(metrics)
            
            # 保持历史记录长度
            if len(self.metrics_history) > self.max_history:
                self.metrics_history.pop(0)
            
            time.sleep(MONITOR_INTERVAL)
    
    def collect_metrics(self) -> dict:
        """收集监控指标"""
        timestamp = datetime.now().isoformat()
        
        # 系统指标
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        
        # 服务器指标
        server_metrics = self._get_server_metrics()
        
        # 网络指标
        net_io = psutil.net_io_counters()
        
        return {
            "timestamp": timestamp,
            "cpu_percent": cpu_percent,
            "memory_percent": memory_percent,
            "memory_used_gb": memory.used / 1024**3,
            "bytes_sent": net_io.bytes_sent,
            "bytes_recv": net_io.bytes_recv,
            **server_metrics
        }
    
    def _get_server_metrics(self) -> dict:
        """获取服务器指标"""
        try:
            # 健康检查
            health_response = requests.get(f"{self.server_url}/health", timeout=2)
            health_ok = health_response.status_code == 200
            
            # 如果有metrics端点
            try:
                metrics_response = requests.get(f"{self.server_url}/metrics", timeout=2)
                metrics_data = metrics_response.text if metrics_response.status_code == 200 else ""
            except:
                metrics_data = ""
            
            # 测试API响应
            start_time = time.time()
            try:
                test_response = requests.get(f"{self.server_url}/v1/models", timeout=5)
                api_latency = time.time() - start_time
                api_ok = test_response.status_code == 200
            except:
                api_latency = 5
                api_ok = False
            
            return {
                "server_health": health_ok,
                "api_available": api_ok,
                "api_latency": api_latency,
                "metrics_data": metrics_data[:100]  # 只取前100字符
            }
            
        except Exception as e:
            return {
                "server_health": False,
                "api_available": False,
                "api_latency": 5,
                "error": str(e)
            }
    
    def get_summary(self) -> dict:
        """获取摘要统计"""
        if not self.metrics_history:
            return {}
        
        recent = self.metrics_history[-10:]  # 最近10个样本
        
        return {
            "avg_cpu": sum(m["cpu_percent"] for m in recent) / len(recent),
            "avg_memory": sum(m["memory_percent"] for m in recent) / len(recent),
            "server_health": recent[-1]["server_health"] if recent else False,
            "avg_api_latency": sum(m.get("api_latency", 0) for m in recent) / len(recent),
            "sample_count": len(self.metrics_history)
        }
    
    def save_history(self, filename: str = None):
        """保存历史数据"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"monitor_history_{timestamp}.json"
        
        import os
        os.makedirs("results", exist_ok=True)
        filepath = os.path.join("results", filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.metrics_history, f, indent=2, default=str)
        
        console.print(f"[green]📁 监控数据已保存到: {filepath}[/green]")
        
        # 也保存摘要
        summary = self.get_summary()
        summary_file = filepath.replace(".json", "_summary.json")
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2)
        
        return filepath

def realtime_monitor(server_url: str = BASE_URL, duration: int = 60):
    """实时监控面板"""
    monitor = ServerMonitor(server_url)
    monitor.start()
    
    console.clear()
    console.print("[bold cyan]🖥️  vLLM 服务器实时监控面板[/bold cyan]")
    console.print(f"[yellow]监控目标: {server_url}[/yellow]")
    console.print("[yellow]按 Ctrl+C 停止监控[/yellow]\n")
    
    try:
        with Live(refresh_per_second=2, console=console, screen=True) as live:
            start_time = time.time()
            
            while time.time() - start_time < duration:
                if not monitor.running:
                    break
                
                # 获取最新数据
                if monitor.metrics_history:
                    latest = monitor.metrics_history[-1]
                    summary = monitor.get_summary()
                    
                    # 创建布局
                    layout = Layout()
                    
                    # 顶部：概览
                    overview = Table(title="📊 系统概览", show_header=False, box=None)
                    overview.add_column("指标", style="cyan", width=20)
                    overview.add_column("值", style="green")
                    
                    overview.add_row("时间", datetime.now().strftime("%H:%M:%S"))
                    overview.add_row("运行时长", f"{time.time() - start_time:.0f}秒")
                    overview.add_row("服务器健康", "✅" if latest.get("server_health") else "❌")
                    overview.add_row("API延迟", f"{latest.get('api_latency', 0):.2f}秒")
                    overview.add_row("历史样本数", str(len(monitor.metrics_history)))
                    
                    # 系统资源
                    system_table = Table(title="💻 系统资源", box=None)
                    system_table.add_column("指标", style="cyan")
                    system_table.add_column("当前值", style="green")
                    system_table.add_column("平均值", style="yellow")
                    
                    system_table.add_row(
                        "CPU使用率", 
                        f"{latest['cpu_percent']:.1f}%", 
                        f"{summary.get('avg_cpu', 0):.1f}%"
                    )
                    system_table.add_row(
                        "内存使用率", 
                        f"{latest['memory_percent']:.1f}%", 
                        f"{summary.get('avg_memory', 0):.1f}%"
                    )
                    system_table.add_row(
                        "内存使用量", 
                        f"{latest['memory_used_gb']:.2f}GB", 
                        "-"
                    )
                    
                    # 网络
                    net_table = Table(title="🌐 网络流量", box=None)
                    net_table.add_column("指标", style="cyan")
                    net_table.add_column("发送", style="green")
                    net_table.add_column("接收", style="green")
                    
                    bytes_sent_mb = latest.get("bytes_sent", 0) / 1024 / 1024
                    bytes_recv_mb = latest.get("bytes_recv", 0) / 1024 / 1024
                    
                    net_table.add_row(
                        "总流量", 
                        f"{bytes_sent_mb:.1f}MB", 
                        f"{bytes_recv_mb:.1f}MB"
                    )
                    
                    # 计算速率
                    if len(monitor.metrics_history) > 1:
                        prev = monitor.metrics_history[-2]
                        time_diff = MONITOR_INTERVAL
                        sent_rate = (latest["bytes_sent"] - prev["bytes_sent"]) / time_diff / 1024
                        recv_rate = (latest["bytes_recv"] - prev["bytes_recv"]) / time_diff / 1024
                        
                        net_table.add_row(
                            "实时速率", 
                            f"{sent_rate:.1f}KB/s", 
                            f"{recv_rate:.1f}KB/s"
                        )
                    
                    # 服务器状态
                    server_panel = Panel(
                        f"健康状态: {'✅ 正常' if latest.get('server_health') else '❌ 异常'}\n"
                        f"API延迟: {latest.get('api_latency', 0):.3f}秒\n"
                        f"API可用: {'✅' if latest.get('api_available') else '❌'}",
                        title="🖥️ 服务器状态",
                        border_style="green" if latest.get("server_health") else "red"
                    )
                    
                    # 组合布局
                    layout.split_column(
                        Layout(Panel(overview, title="概览", border_style="cyan")),
                        Layout(system_table),
                        Layout.split_row(
                            Layout(net_table),
                            Layout(server_panel)
                        )
                    )
                    
                    live.update(layout)
                
                time.sleep(MONITOR_INTERVAL)
                
    except KeyboardInterrupt:
        console.print("\n[yellow]⏹️  监控已停止[/yellow]")
    finally:
        monitor.stop()
        
        # 保存数据
        if monitor.metrics_history:
            data_file = monitor.save_history()
            console.print(f"\n[green]📈 监控数据已保存，共 {len(monitor.metrics_history)} 个样本[/green]")
            
            # 显示摘要
            summary = monitor.get_summary()
            console.print(f"[cyan]平均CPU: {summary.get('avg_cpu', 0):.1f}%[/cyan]")
            console.print(f"[cyan]平均内存: {summary.get('avg_memory', 0):.1f}%[/cyan]")
            console.print(f"[cyan]平均API延迟: {summary.get('avg_api_latency', 0):.3f}秒[/cyan]")

def main():
    """监控主函数"""
    console.print("[bold cyan]🖥️  vLLM 服务器监控工具[/bold cyan]")
    console.print(f"[yellow]目标服务器: {BASE_URL}[/yellow]")
    
    # 检查服务器
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        if response.status_code == 200:
            console.print("[green]✅ 服务器可访问[/green]")
        else:
            console.print(f"[yellow]⚠️  服务器响应异常: {response.status_code}[/yellow]")
    except:
        console.print("[red]❌ 无法连接到服务器[/red]")
        return
    
    # 选择模式
    console.print("\n请选择监控模式:")
    console.print("1. 实时监控面板")
    console.print("2. 后台监控 (配合压力测试)")
    console.print("3. 快速健康检查")
    
    try:
        choice = input("\n请选择 (1-3): ").strip()
    except KeyboardInterrupt:
        console.print("\n👋 已取消")
        return
    
    if choice == "1":
        duration = input("监控时长(秒, 默认60): ").strip()
        duration = int(duration) if duration else 60
        realtime_monitor(BASE_URL, duration)
    elif choice == "2":
        console.print("[yellow]后台监控模式[/yellow]")
        console.print("在另一个终端运行压力测试，本监控会持续运行")
        console.print("按 Ctrl+C 停止监控")
        
        monitor = ServerMonitor(BASE_URL)
        monitor.start()
        
        try:
            while True:
                summary = monitor.get_summary()
                if summary:
                    console.print(f"\r监控中... 样本数: {summary.get('sample_count', 0)}, "
                                f"CPU: {summary.get('avg_cpu', 0):.1f}%, "
                                f"内存: {summary.get('avg_memory', 0):.1f}%, "
                                f"服务器: {'✅' if summary.get('server_health') else '❌'}",
                                end="")
                time.sleep(2)
        except KeyboardInterrupt:
            console.print("\n[yellow]⏹️  监控已停止[/yellow]")
        finally:
            monitor.stop()
            if monitor.metrics_history:
                monitor.save_history()
    elif choice == "3":
        console.print("\n[cyan]🔍 快速健康检查[/cyan]")
        monitor = ServerMonitor(BASE_URL)
        metrics = monitor.collect_metrics()
        
        table = Table(title="健康检查结果", show_header=False)
        table.add_column("项目", style="cyan")
        table.add_column("状态", style="green")
        
        table.add_row("服务器健康", "✅ 正常" if metrics.get("server_health") else "❌ 异常")
        table.add_row("API可用", "✅ 正常" if metrics.get("api_available") else "❌ 异常")
        table.add_row("API延迟", f"{metrics.get('api_latency', 0):.3f}秒")
        table.add_row("CPU使用率", f"{metrics.get('cpu_percent', 0):.1f}%")
        table.add_row("内存使用率", f"{metrics.get('memory_percent', 0):.1f}%")
        
        console.print(table)
    else:
        console.print("[yellow]使用实时监控[/yellow]")
        realtime_monitor(BASE_URL, 60)

if __name__ == "__main__":
    main()