import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import time
import json
import os
import random
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from collections import defaultdict
import requests
import csv
import logging
import sys

class HyperliquidTradingBot:
    def __init__(self, root):
        self.root = root
        self.root.title("Hyperliquid 多策略自动化交易程序 by：8280998")
        self.root.geometry("1400x900")

        # 交易状态变量
        self.trading_active = False
        self.current_positions = {}
        self.strategy_signals = {}
        self.config_file = "trading_config.json"
        self.price_cache = {}
        self.historical_data = {}
        self.data_update_thread = None
        self.auto_update_active = False
        self.connection_status = False
        self.exchange = None
        self.info = None
        

        # 挂单跟踪
        self.pending_orders = {}  # 跟踪所有挂单
        self.order_timeout = 300  # 5分钟超时
        
        # 初始化日志系统
        self.setup_logging()
        
        # 策略权重预设配置
        self.preset_weights = {
            '趋势跟踪型': "2.0,1.0,1.5,1.0",
            '震荡市型': "0.8,2.0,0.8,1.5", 
            '平衡稳健型': "1.5,1.2,1.0,0.8",
            '激进交易型': "1.0,1.8,1.5,0.5",
            '保守稳健型': "2.0,1.0,0.5,1.5",
            '自定义': ""
        }
        
        # 策略权重配置
        self.strategy_weights_config = {
            'ma': 0.3,
            'rsi': 0.25, 
            'macd': 0.25,
            'bollinger': 0.2
        }
        
        self.trade_retry_count = 1
        
        # 创建界面
        self.create_widgets()
        
        # 加载配置
        self.load_config()
        self.coin_config = self.load_coin_config()
        self.initialize_state_recovery()


    def setup_logging(self):
        """设置完整的日志系统"""
        try:
            # 创建logs目录
            log_dir = "logs"
            if not os.path.exists(log_dir):
                os.makedirs(log_dir)
        
            # 按日期创建日志文件
            current_date = datetime.now().strftime("%Y%m%d")
            log_filename = f"{log_dir}/trading_log_{current_date}.txt"
        
            # 配置logging
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(log_filename, encoding='utf-8'),
                    logging.StreamHandler(sys.stdout)
                ]
            )
        
            self.logger = logging.getLogger(__name__)
            self.logger.info("=" * 60)
            self.logger.info(" Hyperliquid 交易程序启动")
            self.logger.info(f"启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            self.logger.info("=" * 60)
        
        except Exception as e:
            print(f"设置日志系统时出错: {str(e)}")

    def log_message(self, message, level="info"):
        """统一的日志记录方法"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"{timestamp} - {message}"
        
        # 输出到GUI日志框
        self.log_text.insert(tk.END, f"{log_entry}\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
        
        # 根据级别记录到文件
        if hasattr(self, 'logger'):
            if level == "error":
                self.logger.error(message)
            elif level == "warning":
                self.logger.warning(message)
            elif level == "debug":
                self.logger.debug(message)
            else:
                self.logger.info(message)

    def log_trade(self, symbol, action, size, price, status, details=""):
        """记录交易详情"""
        try:
            size = float(size)
            price = float(price)
        except ValueError:
            self.log_message(f"日志参数转换失败: size={size}, price={price}", "warning")
            size = 0.0
            price = 0.0

        trade_log = f"交易 {action} | {symbol} | 数量: {size:.4f} | 价格: ${price:.4f} | 状态: {status} | {details}"
        self.log_message(trade_log, "info")

    def log_signal(self, symbol, signals, final_signal, strength):
        """记录策略信号"""
        signal_log = f" 信号 {symbol} | 最终: {final_signal} | 强度: 买{strength.get('buy_strength', 0):.2f}/卖{strength.get('sell_strength', 0):.2f}"
        self.log_message(signal_log, "info")

    def log_risk(self, symbol, status, details=""):
        """记录风险检查"""
        risk_log = f" 风险 {symbol} | {status} | {details}"
        self.log_message(risk_log, "warning" if status != "通过" else "info")

    def create_widgets(self):
        """创建GUI组件"""
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding="5")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # 第一行：API设置
        top_frame = ttk.Frame(main_frame)
        top_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        
        api_frame = ttk.LabelFrame(top_frame, text="Hyperliquid API设置", padding="5")
        api_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E))
        
        ttk.Label(api_frame, text="主账户地址:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.wallet_address = ttk.Entry(api_frame, width=30)
        self.wallet_address.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        
        ttk.Label(api_frame, text="API私钥:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.private_key = ttk.Entry(api_frame, width=30, show="*")
        self.private_key.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        
        ttk.Label(api_frame, text="网络:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.network_var = tk.StringVar(value="testnet")
        network_frame = ttk.Frame(api_frame)
        network_frame.grid(row=2, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        ttk.Radiobutton(network_frame, text="测试网", variable=self.network_var, value="testnet").grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(network_frame, text="主网", variable=self.network_var, value="mainnet").grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        
        config_frame = ttk.Frame(api_frame)
        config_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=2)
        
        ttk.Button(config_frame, text="连接", command=self.connect_exchange, width=8).grid(row=0, column=0, padx=(0, 5))
        ttk.Button(config_frame, text="保存", command=self.save_config, width=8).grid(row=0, column=1, padx=(0, 5))
        ttk.Button(config_frame, text="调试连接", command=self.debug_connection, width=8).grid(row=0, column=2, padx=(5, 0))

        # 第二行：交易配置、风险控制、当前持仓
        middle_frame = ttk.Frame(main_frame)
        middle_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))
        middle_frame.columnconfigure(0, weight=1)
        middle_frame.columnconfigure(1, weight=1)
        middle_frame.columnconfigure(2, weight=1)
        
        # 左侧：交易配置
        left_frame = ttk.LabelFrame(middle_frame, text="交易配置", padding="5")
        left_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(0, 5))
        
        ttk.Label(left_frame, text="交易代币:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.tokens_entry = ttk.Entry(left_frame, width=20)
        self.tokens_entry.grid(row=0, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        
        #  “K线设置” (row=1)
        ttk.Label(left_frame, text="K线设置:").grid(row=1, column=0, sticky=tk.W, pady=2)
        kline_frame = ttk.Frame(left_frame)
        kline_frame.grid(row=1, column=1, sticky=tk.W, pady=2, padx=(5, 0))

        # Radio buttons for 固定周期
        self.kline_interval_var = tk.StringVar(value="30m")  # 默认30m
        ttk.Radiobutton(kline_frame, text="5m", variable=self.kline_interval_var, value="5m").grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(kline_frame, text="30m", variable=self.kline_interval_var, value="30m").grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        ttk.Radiobutton(kline_frame, text="1h", variable=self.kline_interval_var, value="1h").grid(row=0, column=2, sticky=tk.W, padx=(10, 0))
        ttk.Radiobutton(kline_frame, text="6h", variable=self.kline_interval_var, value="6h").grid(row=0, column=3, sticky=tk.W, padx=(10, 0))
        ttk.Radiobutton(kline_frame, text="12h", variable=self.kline_interval_var, value="12h").grid(row=0, column=4, sticky=tk.W, padx=(10, 0))
        ttk.Radiobutton(kline_frame, text="1d", variable=self.kline_interval_var, value="1d").grid(row=0, column=5, sticky=tk.W, padx=(10, 0))

        
        ttk.Label(left_frame, text="策略:").grid(row=2, column=0, sticky=tk.W, pady=2)
        strategy_frame = ttk.Frame(left_frame)
        strategy_frame.grid(row=2, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        
        self.ma_strategy_var = tk.BooleanVar(value=True)
        self.rsi_strategy_var = tk.BooleanVar(value=True)
        self.macd_strategy_var = tk.BooleanVar(value=True)
        self.bollinger_strategy_var = tk.BooleanVar(value=True)
        
        ttk.Checkbutton(strategy_frame, text="均线", variable=self.ma_strategy_var).grid(row=0, column=0, sticky=tk.W)
        ttk.Checkbutton(strategy_frame, text="RSI", variable=self.rsi_strategy_var).grid(row=0, column=1, sticky=tk.W, padx=(5, 0))
        ttk.Checkbutton(strategy_frame, text="MACD", variable=self.macd_strategy_var).grid(row=0, column=2, sticky=tk.W, padx=(5, 0))
        ttk.Checkbutton(strategy_frame, text="布林", variable=self.bollinger_strategy_var).grid(row=0, column=3, sticky=tk.W, padx=(5, 0))
        
        ttk.Label(left_frame, text="模式:").grid(row=3, column=0, sticky=tk.W, pady=2)
        mode_frame = ttk.Frame(left_frame)
        mode_frame.grid(row=3, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        
        self.execution_mode_var = tk.StringVar(value="weighted")
        ttk.Radiobutton(mode_frame, text="权重", variable=self.execution_mode_var, value="weighted").grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(mode_frame, text="严格", variable=self.execution_mode_var, value="strict").grid(row=0, column=1, sticky=tk.W, padx=(5, 0))
        ttk.Radiobutton(mode_frame, text="多数", variable=self.execution_mode_var, value="majority").grid(row=0, column=2, sticky=tk.W, padx=(5, 0))
        
        ttk.Label(left_frame, text="权重预设:").grid(row=4, column=0, sticky=tk.W, pady=2)
        weight_preset_frame = ttk.Frame(left_frame)
        weight_preset_frame.grid(row=4, column=1, sticky=(tk.W, tk.E), pady=2, padx=(5, 0))
        
        self.weight_preset_var = tk.StringVar(value="平衡稳健型")
        self.weight_preset_combo = ttk.Combobox(weight_preset_frame, 
                                              textvariable=self.weight_preset_var,
                                              values=list(self.preset_weights.keys()),
                                              state="readonly",
                                              width=15)
        self.weight_preset_combo.grid(row=0, column=0, sticky=tk.W)
        self.weight_preset_combo.bind('<<ComboboxSelected>>', self.on_weight_preset_selected)
        
        ttk.Label(left_frame, text="权重值:").grid(row=5, column=0, sticky=tk.W, pady=2)
        self.strategy_weights = ttk.Entry(left_frame, width=12)
        self.strategy_weights.insert(0, "1.5,1.2,1.0,0.8")
        self.strategy_weights.grid(row=5, column=1, sticky=tk.W, pady=2, padx=(5, 0))
        
        ttk.Label(left_frame, text="信号阈值:").grid(row=5, column=2, sticky=tk.W, pady=2, padx=(5, 0))
        self.signal_threshold = ttk.Entry(left_frame, width=6)
        self.signal_threshold.insert(0, "0.6")
        self.signal_threshold.grid(row=5, column=3, sticky=tk.W, pady=1, padx=(2, 0))
        
        # 中间：风险控制
        center_frame = ttk.LabelFrame(middle_frame, text="风险控制", padding="5")
        center_frame.grid(row=0, column=1, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 5))

        ttk.Label(center_frame, text="单币最大仓位(%):").grid(row=5, column=0, sticky=tk.W, pady=1)
        self.single_coin_max_pct = ttk.Entry(center_frame, width=8)
        self.single_coin_max_pct.insert(0, "40")
        self.single_coin_max_pct.grid(row=5, column=1, sticky=tk.W, pady=1, padx=(2, 0))

        # 止盈信号阈值
        ttk.Label(center_frame, text="止盈信号阈值:").grid(row=5, column=2, sticky=tk.W, pady=1, padx=(5, 0))
        self.profit_signal_threshold = ttk.Entry(center_frame, width=8)
        self.profit_signal_threshold.insert(0, "0.7")
        self.profit_signal_threshold.grid(row=5, column=3, sticky=tk.W, pady=1, padx=(2, 0))
        
        ttk.Label(center_frame, text="单仓保证金比例(%):").grid(row=0, column=0, sticky=tk.W, pady=1)
        self.max_margin_pct = ttk.Entry(center_frame, width=8)
        self.max_margin_pct.grid(row=0, column=1, sticky=tk.W, pady=1, padx=(2, 0))
        
        ttk.Label(center_frame, text="总保证金比例(%):").grid(row=0, column=2, sticky=tk.W, pady=1, padx=(5, 0))
        self.total_margin_pct = ttk.Entry(center_frame, width=8)
        self.total_margin_pct.grid(row=0, column=3, sticky=tk.W, pady=1, padx=(2, 0))
        
        ttk.Label(center_frame, text="最大币种:").grid(row=1, column=0, sticky=tk.W, pady=1)
        self.max_coins = ttk.Entry(center_frame, width=8)
        self.max_coins.grid(row=1, column=1, sticky=tk.W, pady=1, padx=(2, 0))
        
        ttk.Label(center_frame, text="止盈(%):").grid(row=1, column=2, sticky=tk.W, pady=1, padx=(5, 0))
        self.take_profit_pct = ttk.Entry(center_frame, width=8)
        self.take_profit_pct.grid(row=1, column=3, sticky=tk.W, pady=1, padx=(2, 0))
        
        ttk.Label(center_frame, text="止损(%):").grid(row=2, column=0, sticky=tk.W, pady=1)
        self.stop_loss_pct = ttk.Entry(center_frame, width=8)
        self.stop_loss_pct.grid(row=2, column=1, sticky=tk.W, pady=1, padx=(2, 0))
        
        ttk.Label(center_frame, text="保证金止损(%):").grid(row=2, column=2, sticky=tk.W, pady=1, padx=(5, 0))
        self.margin_stop_pct = ttk.Entry(center_frame, width=8)
        self.margin_stop_pct.grid(row=2, column=3, sticky=tk.W, pady=1, padx=(2, 0))
        
        ttk.Label(center_frame, text="保证金:").grid(row=3, column=0, sticky=tk.W, pady=1)
        self.margin_size = ttk.Entry(center_frame, width=8)
        self.margin_size.grid(row=3, column=1, sticky=tk.W, pady=1, padx=(2, 0))
        
        ttk.Label(center_frame, text="杠杆倍数:").grid(row=3, column=2, sticky=tk.W, pady=1, padx=(5, 0))
        self.leverage = ttk.Entry(center_frame, width=8)
        self.leverage.grid(row=3, column=3, sticky=tk.W, pady=1, padx=(2, 0))
        
        ttk.Label(center_frame, text="间隔(秒):").grid(row=4, column=0, sticky=tk.W, pady=1)
        self.check_interval = ttk.Entry(center_frame, width=8)
        self.check_interval.grid(row=4, column=1, sticky=tk.W, pady=1, padx=(2, 0))
        
        self.auto_rebalance_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(center_frame, text="自动调仓", variable=self.auto_rebalance_var).grid(row=4, column=2, columnspan=2, sticky=tk.W, pady=1, padx=(5, 0))
        
        # 右侧：当前持仓
        right_frame = ttk.LabelFrame(middle_frame, text="当前持仓", padding="5")
        right_frame.grid(row=0, column=2, sticky=(tk.W, tk.E, tk.N, tk.S), padx=(5, 0))
        right_frame.columnconfigure(0, weight=1)
        right_frame.rowconfigure(0, weight=1)
        
        position_columns = ("币种", "持仓数量", "入场价格", "当前价格", "盈亏", "盈亏率")
        self.position_tree = ttk.Treeview(right_frame, columns=position_columns, show="headings", height=6)
        
        position_widths = {
            "币种": 80, "持仓数量": 100, "入场价格": 90, 
            "当前价格": 90, "盈亏": 90, "盈亏率": 80
        }
        
        for col in position_columns:
            self.position_tree.heading(col, text=col)
            self.position_tree.column(col, width=position_widths.get(col, 80))
        
        position_scrollbar = ttk.Scrollbar(right_frame, orient=tk.VERTICAL, command=self.position_tree.yview)
        self.position_tree.configure(yscrollcommand=position_scrollbar.set)
        
        self.position_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        position_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 第三行：控制按钮
        control_frame = ttk.Frame(main_frame)
        control_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 5))

        ttk.Button(control_frame, text="重载配置", command=self.reload_coin_config, width=10).grid(row=0, column=7, padx=(0, 5))
        
        self.start_button = ttk.Button(control_frame, text="开始交易", command=self.start_trading, width=12)
        self.start_button.grid(row=0, column=0, padx=(0, 5))
        
        self.stop_button = ttk.Button(control_frame, text="停止交易", command=self.stop_trading, state="disabled", width=12)
        self.stop_button.grid(row=0, column=1, padx=(0, 5))
        
        ttk.Button(control_frame, text="获取余额", command=self.get_balance, width=10).grid(row=0, column=2, padx=(0, 5))
        ttk.Button(control_frame, text="测试策略", command=self.test_strategies, width=10).grid(row=0, column=3, padx=(0, 5))

        ttk.Button(control_frame, text="回测策略", command=self.run_backtest, width=10).grid(row=0, column=4, padx=(0, 5))
        
        # 日志级别控制
        log_control_frame = ttk.Frame(control_frame)
        log_control_frame.grid(row=0, column=8, sticky=tk.W, padx=(10, 0))
        
        ttk.Label(log_control_frame, text="日志级别:").grid(row=0, column=0, sticky=tk.W)
        self.log_level_var = tk.StringVar(value="INFO")
        log_level_combo = ttk.Combobox(log_control_frame, textvariable=self.log_level_var, 
                                     values=["DEBUG", "INFO", "WARNING", "ERROR"], 
                                     state="readonly", width=10)
        log_level_combo.grid(row=0, column=1, sticky=tk.W, padx=(5, 0))
        log_level_combo.bind('<<ComboboxSelected>>', self.change_log_level)
        
        ttk.Button(control_frame, text="清空日志", command=self.clear_logs, width=8).grid(row=0, column=9, padx=(5, 0))
        
        # 第四行：策略信号监控
        signal_frame = ttk.LabelFrame(main_frame, text="策略信号监控", padding="5")
        signal_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        main_frame.rowconfigure(3, weight=1)
        signal_frame.columnconfigure(0, weight=1)
        signal_frame.rowconfigure(0, weight=1)
        
        columns = ("币种", "当前价格", "持仓状态", "均线", "RSI", "MACD", "布林", "执行模式", "最终信号", "操作建议")
        self.signal_tree = ttk.Treeview(signal_frame, columns=columns, show="headings", height=8)
        
        column_widths = {
            "币种": 80, "当前价格": 90, "持仓状态": 80,
            "均线": 60, "RSI": 60, "MACD": 60, "布林": 60,
            "执行模式": 80, "最终信号": 80, "操作建议": 100
        }
        
        for col in columns:
            self.signal_tree.heading(col, text=col)
            self.signal_tree.column(col, width=column_widths.get(col, 80))
        
        scrollbar = ttk.Scrollbar(signal_frame, orient=tk.VERTICAL, command=self.signal_tree.yview)
        self.signal_tree.configure(yscrollcommand=scrollbar.set)
        
        self.signal_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        
        # 第五行：交易日志
        log_frame = ttk.LabelFrame(main_frame, text="交易日志", padding="5")
        log_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        main_frame.rowconfigure(4, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=8, width=100)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 状态栏
        self.status_var = tk.StringVar(value="准备就绪")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.grid(row=5, column=0, columnspan=2, sticky=(tk.W, tk.E))

    def change_log_level(self, event):
        """更改日志级别"""
        level = self.log_level_var.get()
        if hasattr(self, 'logger'):
            if level == "DEBUG":
                self.logger.setLevel(logging.DEBUG)
            elif level == "INFO":
                self.logger.setLevel(logging.INFO)
            elif level == "WARNING":
                self.logger.setLevel(logging.WARNING)
            elif level == "ERROR":
                self.logger.setLevel(logging.ERROR)
        self.log_message(f"日志级别已更改为: {level}", "info")

    def clear_logs(self):
        """清空日志显示"""
        self.log_text.delete(1.0, tk.END)
        self.log_message("日志显示已清空", "info")

    def load_coin_config(self):
        """加载币种配置文件"""
        config_file = "coins.json"
        default_config = {
            "supported_coins": ["ETH", "BTC", "SOL", "ADA"],
            "trading_config": {
                "ADA": {
                    "max_leverage": 3,
                    "price_precision": 4,
                    "size_precision": 0,
                    "min_size": 1
                },
                "BTC": {
                    "max_leverage": 20,
                    "price_precision": 2,
                    "size_precision": 3,
                    "min_size": 0.001
                },
                "ETH": {
                    "max_leverage": 20,
                    "price_precision": 2,
                    "size_precision": 3,
                    "min_size": 0.001
                },
                "SOL": {
                    "max_leverage": 10,
                    "price_precision": 3,
                    "size_precision": 2,
                    "min_size": 0.01
                },
                "DEFAULT": {
                    "max_leverage": 5,
                    "price_precision": 4,
                    "size_precision": 2,
                    "min_size": 0.01
                }
            }
        }
        
        try:
            if os.path.exists(config_file):
                with open(config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    merged_config = {**default_config, **loaded_config}
                    return merged_config
            else:
                with open(config_file, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=2, ensure_ascii=False)
                return default_config
        except Exception as e:
            self.log_message(f"加载币种配置时出错: {str(e)}", "error")
            return default_config

    def on_weight_preset_selected(self, event):
        """权重预设选择事件处理"""
        selected_preset = self.weight_preset_var.get()
        if selected_preset in self.preset_weights:
            weights_value = self.preset_weights[selected_preset]
            self.strategy_weights.delete(0, tk.END)
            if weights_value:
                self.strategy_weights.insert(0, weights_value)
                self.log_message(f"✅ 已选择权重预设: {selected_preset} - {weights_value}", "info")
                self.parse_strategy_weights(weights_value)
            else:
                self.log_message("自定义权重模式，请手动输入权重值", "info")
        else:
            self.log_message(" 未知的权重预设", "error")

    def connect_exchange(self):
        """连接Hyperliquid交易所"""
        try:
            wallet_address = self.wallet_address.get().strip()
            private_key = self.private_key.get().strip()
        
            if not wallet_address or not private_key:
                self.log_message("请填写完整的主账户地址和API私钥", "error")
                return
        
            self.log_message(f"尝试连接交易所 - 钱包: {wallet_address[:10]}...", "info")
        
            try:
                from hyperliquid.exchange import Exchange
                from hyperliquid.info import Info
                from hyperliquid.utils import constants
                from eth_account import Account
            except ImportError:
                self.log_message("请先安装必要的依赖: pip install hyperliquid-python eth-account", "error")
                return
        
            if self.network_var.get() == "testnet":
                base_url = constants.TESTNET_API_URL
                self.log_message("正在连接测试网...", "info")
            else:
                base_url = constants.MAINNET_API_URL
                self.log_message("正在连接主网...", "info")
        
            try:
                if not private_key.startswith('0x'):
                    private_key = '0x' + private_key
                
                account = Account.from_key(private_key)
                self.log_message(f"✅ 创建账户对象成功: {account.address}", "info")
            
                if base_url == constants.TESTNET_API_URL:
                    self.exchange = Exchange(account, base_url=base_url)
                else:
                    self.exchange = Exchange(account)
                
                self.info = Info(base_url, skip_ws=True)
                self.log_message("✅ 对象创建成功，正在获取用户状态...", "info")
            
                user_state = self.info.user_state(wallet_address)
            
                if user_state:
                    margin_summary = user_state.get('marginSummary', {})
                    account_value = margin_summary.get('accountValue', 'N/A')
                
                    self.log_message(f"✅ 连接成功! 网络: {self.network_var.get()}", "info")
                    self.log_message(f"💰 账户余额: {account_value} USDC", "info")
                
                    self.connection_status = True
                    self.start_button.config(state="normal")
                    self.update_real_positions()
                else:
                    self.log_message("❌ 连接失败，请检查API配置", "error")
                
            except Exception as e:
                self.log_message(f"❌ 连接时出错: {str(e)}", "error")
                self.connection_status = False
                
        except Exception as e:
            self.log_message(f"❌ 连接时出错: {str(e)}", "error")
            self.connection_status = False

    def save_config(self):
        """保存配置到文件"""
        try:
            config = {
                'wallet_address': self.wallet_address.get(),
                'private_key': self.private_key.get(),
                'single_coin_max_pct': self.single_coin_max_pct.get(),
                'profit_signal_threshold': self.profit_signal_threshold.get(),
                'network': self.network_var.get(),
                'tokens': self.tokens_entry.get(),
                'execution_mode': self.execution_mode_var.get(),
                'weight_preset': self.weight_preset_var.get(),
                'strategy_weights': self.strategy_weights.get(),
                'signal_threshold': self.signal_threshold.get(),
                'max_margin_pct': self.max_margin_pct.get(),
                'total_margin_pct': self.total_margin_pct.get(),
                'max_coins': self.max_coins.get(),
                'take_profit_pct': self.take_profit_pct.get(),
                'stop_loss_pct': self.stop_loss_pct.get(),
                'margin_stop_pct': self.margin_stop_pct.get(),
                'margin_size': self.margin_size.get(),
                'leverage': self.leverage.get(),
                'check_interval': self.check_interval.get(),
                'auto_rebalance': self.auto_rebalance_var.get(),
                'kline_interval': self.kline_interval_var.get(),
                'save_time': datetime.now().isoformat()
            }
        
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        
            self.log_message("✅ 配置已保存到文件", "info")
        
        except Exception as e:
            self.log_message(f" 保存配置时出错: {str(e)}", "error")

    def debug_connection(self):
        """调试连接状态"""
        if not hasattr(self, 'info') or not self.info:
            self.log_message(" Info对象未初始化", "error")
            return
        
        try:
            self.log_message("🔍 开始连接调试...", "info")
            
            all_mids = self.info.all_mids()
            self.log_message(f"市场数据: {len(all_mids)}个交易对", "info")
            if all_mids:
                sample_pairs = list(all_mids.items())[:3]
                for pair, price in sample_pairs:
                    self.log_message(f"  {pair}: {price}", "debug")
            
            meta = self.info.meta()
            universe = meta.get('universe', [])
            self.log_message(f"元数据: {len(universe)}个资产", "info")
            if universe:
                sample_assets = universe[:3]
                for asset in sample_assets:
                    self.log_message(f"  资产: {asset.get('name', 'N/A')}", "debug")
            
            wallet_address = self.wallet_address.get().strip()
            if wallet_address and wallet_address != "0xYourWalletAddressHere":
                user_state = self.info.user_state(wallet_address)
                self.log_message(f"用户状态: {bool(user_state)}", "info")
                if user_state:
                    margin_summary = user_state.get('marginSummary', {})
                    self.log_message(f"  账户价值: {margin_summary.get('accountValue', 'N/A')}", "info")
            else:
                self.log_message("请先设置有效的钱包地址", "warning")
            
            self.log_message("✅ 连接调试完成", "info")
            
        except Exception as e:
            self.log_message(f"❌ 连接调试失败: {str(e)}", "error")

    def update_real_positions(self):
        """从交易所获取真实持仓"""
        if not self.connection_status:
            return
            
        try:
            wallet_address = self.wallet_address.get().strip()
            user_state = self.info.user_state(wallet_address)
        
            if user_state:
                asset_positions = user_state.get('assetPositions', [])
            
                self.current_positions = {}
                for position in asset_positions:
                    position_data = position.get('position', {})
                    symbol = position_data.get('coin', '').replace('-PERP', '')
                    if symbol:
                        self.current_positions[symbol] = {
                            'size': float(position_data.get('szi', 0)),
                            'entry_price': float(position_data.get('entryPx', 0)),
                            'unrealized_pnl': float(position_data.get('unrealizedPnl', 0))
                        }
            
                self.update_position_display()
                self.log_message("持仓信息已更新", "debug")
            
        except Exception as e:
            self.log_message(f"获取持仓时出错: {str(e)}", "error")

    def get_price_precision(self, symbol):
        """从配置获取价格精度 (优先 SDK meta pxDecimals, fallback coins.json)"""
        try:
            # 优先 SDK meta
            if self.connection_status and hasattr(self, 'info'):
                meta = self.info.meta()
                coin = f"{symbol.upper()}"
            
                if 'universe' in meta:
                    for asset in meta['universe']:
                        if asset.get('name') == coin:
                            px_decimals = asset.get('pxDecimals', 4)
                            return px_decimals
            
            # Fallback coins.json
            trading_config = self.coin_config.get("trading_config", {})
            symbol_config = trading_config.get(symbol.upper(), {})
        
            if "price_precision" in symbol_config:
                precision = symbol_config["price_precision"]
                return precision
        
            if not hasattr(self, '_price_precisions'):
                self._price_precisions = {}
        
            if symbol in self._price_precisions:
                return self._price_precisions[symbol]
        
            # 默认
            default_precision = 4
            self._price_precisions[symbol] = default_precision
            return default_precision
        
        except Exception as e:
            self.log_message(f"获取价格精度失败 {symbol}: {str(e)}", "error")
            return 4

    def enhanced_risk_check(self, token, is_opening_new_position=False):
        """增强的风险检查"""
        try:
            if not self.connection_status:
                return False, "未连接交易所", 0

            wallet_address = self.wallet_address.get().strip()
            user_state = self.info.user_state(wallet_address)
            margin_summary = user_state.get('marginSummary', {})
            total_margin_used = float(margin_summary.get('totalMarginUsed', 0))
            account_value = float(margin_summary.get('accountValue', 0))

            if account_value <= 0:
                return False, "账户价值为0", 0

            # 计算当前保证金使用率
            current_ratio = (total_margin_used / account_value) * 100
            total_margin_limit = float(self.total_margin_pct.get() or 60)
        
            # 第一层防护：检查当前是否已经超过总限制
            if current_ratio >= total_margin_limit:
                return False, f"当前保证金使用率{current_ratio:.1f}%已超过限制{total_margin_limit}%", 0

            # 计算可用保证金
            max_total_margin = account_value * (total_margin_limit / 100)
            available_margin = max(0, max_total_margin - total_margin_used)
            available_ratio = (available_margin / account_value) * 100

            # 第二层防护：如果可用保证金很少，直接拒绝新开仓
            if is_opening_new_position and available_ratio < 5:  # 可用少于5%时拒绝
                return False, f"可用保证金过少({available_ratio:.1f}%)，无法开新仓", available_margin

            # 单币保证金限制
            single_margin_pct = float(self.max_margin_pct.get() or 20)
            single_coin_max_margin = account_value * (single_margin_pct / 100)
        
            # 关键修复：实际可用的保证金 = min(单币限制, 总剩余额度)
            actual_available_margin = min(single_coin_max_margin, available_margin)
            actual_available_ratio = (actual_available_margin / account_value) * 100

            # 持仓数量检查
            if is_opening_new_position:
                positions_count = len(self.current_positions)
                max_coins = int(self.max_coins.get() or 5)
                if positions_count >= max_coins:
                    return False, f"持仓数量{positions_count}已达上限{max_coins}", actual_available_margin

            # 详细日志记录
            self.log_message(
                f" {token} 风险分析:\n"
                f"  当前使用: {current_ratio:.1f}% / {total_margin_limit}%\n"
                f"  总可用: {available_ratio:.1f}%\n"
                f"  单币限制: {single_margin_pct}% = ${single_coin_max_margin:.2f}\n"
                f"  实际可用: {actual_available_ratio:.1f}% = ${actual_available_margin:.2f}",
                "debug"
            )

            # 第三层防护：决策逻辑
            if not is_opening_new_position:
                # 对于平仓或调仓操作，风险检查较宽松
                return True, "通过", actual_available_margin
        
            # 对于新开仓操作，严格检查
            if actual_available_margin <= 0:
                return False, "无可用保证金额度", 0
        
            # 如果有可用保证金但接近限制，给出警告但仍允许
            if available_ratio < 10:  # 可用少于10%时警告
                self.log_risk(token, "额度紧张", f"可用仅{available_ratio:.1f}%")
                return True, f"额度紧张({available_ratio:.1f}%)", actual_available_margin
        
            return True, "通过", actual_available_margin

        except Exception as e:
            self.log_message(f"❌ 风险检查出错: {str(e)}", "error")
            return False, "检查出错", 0

    def calculate_position_size(self, symbol, is_long=True, available_margin=None, current_position_size=0):
        """计算仓位大小 - 支持增量加仓 + 确认 json 配置"""
        try:
            if not self.connection_status:
                return 0

            #确保current_position_size是浮点数
            if isinstance(current_position_size, str):
                current_position_size = float(current_position_size)


            
            # 获取账户信息
            wallet_address = self.wallet_address.get().strip()
            user_state = self.info.user_state(wallet_address)
            margin_summary = user_state.get('marginSummary', {})
            account_value = float(margin_summary.get('accountValue', 100))
            total_margin_used = float(margin_summary.get('totalMarginUsed', 0))
            
            # 前置检查：总保证金限制
            total_margin_limit = float(self.total_margin_pct.get() or 60)
            current_ratio = (total_margin_used / account_value) * 100
            if current_ratio >= total_margin_limit:
                self.log_message(f" {symbol} 当前保证金使用率{current_ratio:.1f}%已达限制", "warning")
                return 0
            
            # 计算最大可用保证金
            max_total_margin = account_value * (total_margin_limit / 100)
            total_available_margin = max(0, max_total_margin - total_margin_used)
            if available_margin is None:
                available_margin = total_available_margin
            available_margin = min(available_margin, total_available_margin)
            if available_margin <= 0:
                self.log_message(f" {symbol} 无可用保证金", "warning")
                return 0
            
            # 从 coins.json 获取配置 + 日志确认
            trading_config = self.coin_config.get("trading_config", {})
            symbol_config = trading_config.get(symbol.upper(), trading_config.get("DEFAULT", {}))
            self.log_message(f"🔍 {symbol} 配置加载: {symbol_config}", "debug")
            
            configured_leverage = float(self.leverage.get() or 3)
            max_allowed_leverage = symbol_config.get("max_leverage", 5)
            used_leverage = min(configured_leverage, max_allowed_leverage)
            if configured_leverage > max_allowed_leverage:
                self.log_message(f" {symbol} 配置杠杆{configured_leverage}x超过最大允许{max_allowed_leverage}x，已使用{used_leverage}x", "warning")
            
            # 单币保证金限制
            max_margin_pct = float(self.max_margin_pct.get() or 20)
            single_coin_max_margin = account_value * (max_margin_pct / 100)
            
            # 修复：计算当前仓位已用单币保证金（增量）
            current_price_data = self.get_stable_real_time_price(symbol)
            if not current_price_data:
                return 0
            current_price = float(current_price_data['price'])
            current_position_value = abs(current_position_size) * current_price
            current_margin_used = current_position_value / used_leverage
            remaining_single_margin = max(0, single_coin_max_margin - current_margin_used)
            
            # 实际可用 = min(单币剩余, 总可用)
            actual_max_margin = min(remaining_single_margin, available_margin)
            if actual_max_margin <= 0:
                self.log_message(f" {symbol} 无剩余可用保证金 (当前已用: ${current_margin_used:.2f})", "warning")
                return 0
            
            # 计算基础仓位
            base_position_size = actual_max_margin / current_price
            position_size = base_position_size * used_leverage
            if not is_long:
                position_size = -position_size

            # 从 json 获取精度/最小
            price_precision = symbol_config.get("price_precision", 4)
            size_precision = symbol_config.get("size_precision", 2)
            min_size = symbol_config.get("min_size", 0.01)
            position_size = round(position_size, size_precision)
            
            # 确保最小
            if abs(position_size) < min_size:
                position_size = min_size * (1 if is_long else -1)
                position_size = round(position_size, size_precision)
            
            # 整数精度
            if size_precision == 0:
                position_size = int(position_size)
                if position_size == 0:
                    position_size = 1 if is_long else -1
            
            # 交易后预测检查
            used_after_trade = total_margin_used + actual_max_margin
            used_ratio_after = (used_after_trade / account_value) * 100
            
            # 如果交易后超过限制，调整仓位
            if used_ratio_after > total_margin_limit:
                self.log_message(
                    f"🔄 {symbol} 交易后使用率将达{used_ratio_after:.1f}%，调整仓位",
                    "warning"
                )
                # 重新计算，确保不超过总限制
                max_allowable_margin = total_available_margin
                adjusted_base_size = max_allowable_margin / current_price
                position_size = adjusted_base_size * used_leverage
                if not is_long:
                    position_size = -position_size
                position_size = round(position_size, size_precision)
                
                # 再次确保整数精度
                if size_precision == 0:
                    position_size = int(position_size)
                    if position_size == 0:
                        position_size = 1 if is_long else -1
                
                # 重新计算交易后使用率
                used_after_trade = total_margin_used + max_allowable_margin
                used_ratio_after = (used_after_trade / account_value) * 100
            
            # 最终验证
            if used_ratio_after > total_margin_limit:
                self.log_message(
                    f"{symbol} 最终检查仍超限{used_ratio_after:.1f}%，取消交易",
                    "error"
                )
                return 0
            
            # 记录
            self.log_message(
                f" {symbol} 仓位计算 (当前size: {current_position_size}):\n"
                f"  当前: {current_ratio:.1f}% / {total_margin_limit}%\n"
                f"  配置杠杆: {configured_leverage}x | 允许: {max_allowed_leverage}x | 使用: {used_leverage}x\n"
                f"  单币限制: {max_margin_pct}% = ${single_coin_max_margin:.2f}\n"
                f"  当前单币已用: ${current_margin_used:.2f} | 剩余: ${remaining_single_margin:.2f}\n"
                f"  实际使用: ${actual_max_margin:.2f}\n"
                f"  交易后: {used_ratio_after:.1f}% / {total_margin_limit}%\n"
                f"  最终仓位: {position_size} (精度: {size_precision}, 最小: {min_size})",
                "info"
            )
            
            # 确保返回的仓位大小是浮点数
            position_size = round(position_size, size_precision)
            if isinstance(position_size, str):
                position_size = float(position_size)

            return position_size

        except Exception as e:
            self.log_message(f"计算仓位大小时出错: {str(e)}", "error")
            return 0

    # 挂单管理相关方法
    def has_pending_order_for_symbol(self, symbol, side):
        """检查是否已有相同方向的挂单 - 增强检查"""
        if not hasattr(self, 'pending_orders') or not self.pending_orders:
            return False
            
        current_time = time.time()
        pending_count = 0
        
        for order_id, order_info in list(self.pending_orders.items()):
            # 清理过期的挂单记录（超过10分钟）
            if current_time - order_info['timestamp'] > 600:
                self.log_message(f" 清理过期挂单记录: {symbol} {order_info['side']}", "debug")
                del self.pending_orders[order_id]
                continue
                
            if (order_info['symbol'] == symbol and 
                order_info['side'] == side and 
                order_info['status'] == 'pending'):
                pending_count += 1
                self.log_message(f"发现已有挂单: {symbol} {side} (共{pending_count}个)", "debug")
        
        return pending_count > 0

    def track_pending_order(self, symbol, order_id, side, size, price):
        """跟踪挂单"""
        if not hasattr(self, 'pending_orders'):
            self.pending_orders = {}
    
        self.pending_orders[order_id] = {
            'symbol': symbol,
            'side': side,
            'size': size,
            'price': price,
            'timestamp': time.time(),
            'status': 'pending'
        }
        self.log_message(f"开始跟踪挂单 {symbol} {side} {size} @ {price}", "info")

    def check_pending_orders(self):
        """检查所有挂单状态 - 更频繁检查"""
        if not hasattr(self, 'pending_orders') or not self.pending_orders:
            return
    
        completed_orders = []
        current_time = time.time()
        
        for order_id, order_info in list(self.pending_orders.items()):
            try:
                symbol = order_info['symbol']
                
                # 检查订单状态
                order_status = self.exchange.order_status(symbol, order_id)
            
                if order_status.get('status') == 'filled':
                    self.log_message(f"✅ 挂单成交: {symbol} {order_info['side']} {order_info['size']}", "info")
                    completed_orders.append(order_id)
                elif order_status.get('status') == 'cancelled':
                    self.log_message(f"❌ 挂单取消: {symbol}", "warning")
                    completed_orders.append(order_id)
                elif order_status.get('status') == 'pending':
                    # 检查是否超时（超过5分钟）
                    if current_time - order_info['timestamp'] > self.order_timeout:
                        self.log_message(f"挂单超时: {symbol}，尝试取消", "warning")
                        try:
                            self.exchange.cancel_order(symbol, order_id)
                            completed_orders.append(order_id)
                        except Exception as e:
                            self.log_message(f"❌ 取消挂单失败 {symbol}: {str(e)}", "error")
                else:
                    # 未知状态，保留记录但记录警告
                    self.log_message(f"挂单未知状态: {symbol} {order_status.get('status')}", "warning")
            
            except Exception as e:
                self.log_message(f"❌ 检查挂单状态失败 {order_info['symbol']}: {str(e)}", "error")
                # 如果检查失败超过10分钟，清理记录
                if current_time - order_info['timestamp'] > 600:
                    self.log_message(f"清理无法检查的挂单记录: {order_info['symbol']}", "warning")
                    completed_orders.append(order_id)
    
        # 移除已完成订单
        for order_id in completed_orders:
            if order_id in self.pending_orders:
                del self.pending_orders[order_id]

    def get_effective_margin_usage(self):
        """获取有效保证金使用率（包括挂单占用）"""
        try:
            # 获取当前已用保证金
            margin_state = self.get_current_margin_state()
            base_used = margin_state['total_margin_used']
            account_value = margin_state['account_value']
        
            # 计算挂单占用的保证金
            pending_margin = 0
            if hasattr(self, 'pending_orders') and self.pending_orders:
                for order_id, order_info in self.pending_orders.items():
                    # 估算挂单保证金占用
                    order_margin = (abs(order_info['size']) * order_info['price']) / float(self.leverage.get() or 3)
                    pending_margin += order_margin
        
            total_effective_used = base_used + pending_margin
            effective_ratio = (total_effective_used / account_value) * 100 if account_value > 0 else 0
        
            self.log_message(
                f"有效保证金: {base_used:.2f}(已用) + {pending_margin:.2f}(挂单) = {total_effective_used:.2f} "
                f"({effective_ratio:.1f}%)", 
                "debug"
            )
        
            return {
                'base_used': base_used,
                'pending_margin': pending_margin,
                'total_effective_used': total_effective_used,
                'effective_ratio': effective_ratio,
                'account_value': account_value
            }
        
        except Exception as e:
            self.log_message(f"计算有效保证金失败: {str(e)}", "error")
            return self.get_current_margin_state()

    def has_pending_orders_for_token(self, token):
        """检查指定币种是否有任何方向的挂单"""
        if not hasattr(self, 'pending_orders') or not self.pending_orders:
            return False
            
        for order_id, order_info in self.pending_orders.items():
            if order_info['symbol'] == token and order_info['status'] == 'pending':
                return True
        return False

    def execute_signal_trade(self, symbol, final_signal, position_info, current_price, signal_strength=None, available_margin=None):
        """信号驱动交易 - 修复版本"""
        size = position_info['size']
        has_position = size != 0
        is_long = position_info.get('is_long', False)
        is_short = position_info.get('is_short', False)

        # 检查是否已有相同方向的挂单
        if final_signal == "买入" and self.has_pending_order_for_symbol(symbol, "buy"):
            self.log_message(f"{symbol} 已有买入挂单，跳过执行", "warning")
            return
        elif final_signal == "卖出" and self.has_pending_order_for_symbol(symbol, "sell"):
            self.log_message(f" {symbol} 已有卖出挂单，跳过执行", "warning")
            return

        #  最终风险检查
        is_opening_new_position = (final_signal != "持有" and not has_position)
        
        margin_state = self.get_current_margin_state()
        current_used_margin = margin_state['total_margin_used']
        account_value = margin_state['account_value']
        
        risk_ok, risk_msg, risk_available_margin = self.enhanced_risk_check_dynamic(
            symbol, is_opening_new_position, current_used_margin, account_value
        )

        if available_margin is None:
            available_margin = risk_available_margin

        if not risk_ok:
            self.log_message(f" 最终风险检查未通过: {risk_msg}，取消交易", "warning")
            return

        if self.check_single_coin_position_limit(symbol, final_signal, position_info):
            self.log_message(f" {symbol} 单个币种仓位已达上限，跳过操作", "warning")
            return
    
        execution_mode = self.execution_mode_var.get()
        if execution_mode in ['weighted', 'strict'] and signal_strength:
            strength_threshold = float(self.signal_threshold.get())
            buy_strength = signal_strength.get('buy_strength', 0)
            sell_strength = signal_strength.get('sell_strength', 0)
    
            if final_signal == "买入" and buy_strength < strength_threshold:
                self.log_message(f" {symbol} 买入信号强度不足 ({buy_strength:.2f} < {strength_threshold:.2f})，跳过", "info")
                return
            elif final_signal == "卖出" and sell_strength < strength_threshold:
                self.log_message(f" {symbol} 卖出信号强度不足 ({sell_strength:.2f} < {strength_threshold:.2f})，跳过", "info")
                return

        #  交易执行逻辑
        if final_signal == "买入":
            if not has_position:
                new_size = self.calculate_position_size(symbol, is_long=True, available_margin=available_margin)
                if abs(new_size) > 0.01:
                    self.log_message(f"🟢 {symbol} 开多仓，数量: {new_size:.4f}", "info")
                    result = self.execute_trade(symbol, "buy", new_size, "market")
                    if result == "pending":
                        self.log_message(f"⏳ {symbol} 买入订单已挂单", "info")
                else:
                    self.log_message(f" {symbol} 计算仓位过小，跳过开多", "warning")
            elif is_short:
                self.log_message(f"🔄 {symbol} 调仓: 先平空仓再开多仓", "info")
                close_success = self.execute_close_position(symbol, size)
                if close_success:
                    time.sleep(2)
                    self.update_real_positions()
                    current_position = self.current_positions.get(symbol, {})
                    current_size = current_position.get('size', 0)
                    if abs(current_size) < 0.001:
                        new_size = self.calculate_position_size(symbol, is_long=True, available_margin=available_margin)
                        if abs(new_size) > 0.01:
                            self.log_message(f"🟢 {symbol} 开立多仓，数量: {new_size:.4f}", "info")
                            result = self.execute_trade(symbol, "buy", new_size, "market")
                            if result == "pending":
                                self.log_message(f"⏳ {symbol} 买入订单已挂单", "info")
            else:
                self.log_message(f"🟢 {symbol} 加多仓信号，当前多头持仓", "info")
                add_size = self.calculate_position_size(symbol, is_long=True, available_margin=available_margin)
                if abs(add_size) > 0.01:
                    self.log_message(f"🟢 {symbol} 加仓多头，数量: {add_size:.4f}", "info")
                    result = self.execute_trade(symbol, "buy", add_size, "market")
                    if result == "pending":
                        self.log_message(f"⏳ {symbol} 加仓订单已挂单", "info")
                else:
                    self.log_message(f"{symbol} 加仓计算数量过小，跳过", "warning")

        elif final_signal == "卖出":
            if not has_position:
                short_size = self.calculate_position_size(symbol, is_long=False, available_margin=available_margin)
                if abs(short_size) > 0.01:
                    self.log_message(f"🔴 {symbol} 开空仓，数量: {abs(short_size):.4f}", "info")
                    result = self.execute_trade(symbol, "sell", abs(short_size), "market")
                    if result == "pending":
                        self.log_message(f"⏳ {symbol} 卖出订单已挂单", "info")
                else:
                    self.log_message(f" {symbol} 计算空仓数量过小，跳过开空", "warning")
            elif is_long:
                self.log_message(f"🔄 {symbol} 调仓: 先平多仓再开空仓", "info")
                close_success = self.execute_close_position(symbol, size)
                if close_success:
                    time.sleep(2)
                    self.update_real_positions()
                    current_position = self.current_positions.get(symbol, {})
                    current_size = current_position.get('size', 0)
                    if abs(current_size) < 0.001:
                        new_size = self.calculate_position_size(symbol, is_long=False, available_margin=available_margin)
                        if abs(new_size) > 0.01:
                            self.log_message(f"🔴 {symbol} 开立空仓，数量: {abs(new_size):.4f}", "info")
                            result = self.execute_trade(symbol, "sell", abs(new_size), "market")
                            if result == "pending":
                                self.log_message(f"⏳ {symbol} 卖出订单已挂单", "info")
            else:
                self.log_message(f"🔴 {symbol} 加空仓信号，当前空头持仓", "info")
                add_size = self.calculate_position_size(symbol, is_long=False, available_margin=available_margin)
                if abs(add_size) > 0.01:
                    self.log_message(f"🔴 {symbol} 加仓空头，数量: {abs(add_size):.4f}", "info")
                    result = self.execute_trade(symbol, "sell", abs(add_size), "market")
                    if result == "pending":
                        self.log_message(f"⏳ {symbol} 加仓订单已挂单", "info")
                else:
                    self.log_message(f" {symbol} 加仓计算数量过小，跳过", "warning")

        else:
            self.log_message(f"🟡 {symbol} 持有信号，不执行操作", "info")

    def execute_trade(self, symbol, side, size, order_type="market", price=None, retry_count=None):
        """执行交易订单 - 加强挂单检查"""
        if not self.connection_status:
            self.log_message("❌ 请先连接交易所", "error")
            return False

        try:
            original_size = size
            if isinstance(size, str):
                size = float(size)
            else:
                size = float(size)
            
            if original_size != size:
                self.log_message(f" 数量类型转换: {original_size} -> {size}", "debug")
        except (ValueError, TypeError) as e:
            self.log_message(f" {symbol} 交易数量格式错误: {size}, 错误: {str(e)}", "error")
            return False

        #  确保price是浮点数
        if order_type == "limit" and price is not None:
            try:
                if isinstance(price, str):
                    price = float(price)
                else:
                    price = float(price)
            except (ValueError, TypeError) as e:
                self.log_message(f" {symbol} 价格格式错误: {price}, 错误: {str(e)}", "error")
                return False

        # 加强检查：检查是否已有相同方向的挂单
        if self.has_pending_order_for_symbol(symbol, side):
            self.log_message(f" {symbol} 已有{side}方向的挂单，禁止新订单", "warning")
            return "pending"

        # 新增检查：从交易所获取实际挂单状态
        try:
            wallet_address = self.wallet_address.get().strip()
            user_state = self.info.user_state(wallet_address)
            open_orders = user_state.get('openOrders', [])
            
            pending_orders_count = 0
            for order in open_orders:
                if (order.get('coin') == symbol and 
                    ((side == "buy" and order.get('side') == "B") or 
                     (side == "sell" and order.get('side') == "S"))):
                    pending_orders_count += 1
            
            if pending_orders_count > 0:
                self.log_message(f" {symbol} 交易所存在{side}方向挂单({pending_orders_count}个)，禁止新订单", "warning")
                return "pending"
                
        except Exception as e:
            self.log_message(f"检查交易所挂单状态失败: {str(e)}", "warning")

        # 新增：最终数量验证
        trading_config = self.coin_config.get("trading_config", {})
        symbol_config = trading_config.get(symbol.upper(), trading_config.get("DEFAULT", {}))
        
        size_precision = symbol_config.get("size_precision", 2)
        min_size = symbol_config.get("min_size", 0.01)
        
        # 确保数量精度
        original_size = size
        size = round(size, size_precision)
        
        # 关键修复：对于精度为0的代币，确保是整数
        if size_precision == 0:
            size = int(size)
            if size == 0:
                size = 1 if side.lower() == "buy" else -1
        
        # 检查最小交易量
        if abs(size) < min_size:
            self.log_message(f"{symbol} 交易数量过小: {original_size} -> {size} < 最小要求 {min_size}", "error")
            return False

        # 记录调整后的数量
        if original_size != size:
            self.log_message(f"🔧 {symbol} 数量精度调整: {original_size} -> {size} (精度: {size_precision})", "info")

        #  修复：减少重试次数，增加重试间隔
        if retry_count is None:
            retry_count = 1  # 只重试1次，总共2次尝试
        max_retries = retry_count + 1

        #  修复：记录交易前的持仓状态
        old_position = self.current_positions.get(symbol, {}).get('size', 0)
        self.log_message(f"📊 {symbol} 交易前持仓: {old_position}", "info")

        for attempt in range(max_retries):
            try:
                is_buy = (side.lower() == "buy")
                coin = f"{symbol.upper()}"

                #  再次检查挂单状态（防止在重试期间出现新挂单）
                if self.has_pending_order_for_symbol(symbol, side):
                    self.log_message(f" {symbol} 重试期间出现新挂单，取消重试", "warning")
                    return "pending"

                # 从 json 获取精度
                precision = symbol_config.get("price_precision", 4)
                tick_size = 10 ** (-precision)
                self.log_message(f"🔍 {symbol} tick_size: {tick_size} (precision: {precision})", "debug")

                if order_type == "market":
                    self.log_message(f"🔄 {symbol} Market {side} {size} (SDK market_open)", "info")
                    order_result = self.exchange.market_open(coin, is_buy, size)
                    trade_price = 0
                else:
                    if price is None:
                        price_data = self.get_stable_real_time_price(symbol)
                        price = price_data['price'] if price_data else 0
                    
                    if price == 0:
                        self.log_message(f"❌ 无法获取 {symbol} 的有效价格", "error")
                        return False

                    snapped_price = round(price / tick_size) * tick_size
                    snapped_price = round(snapped_price, precision)
                    trade_price = snapped_price
                    order_type_config = {"limit": {"tif": "Gtc"}}
                    order_result = self.exchange.order(coin, is_buy, size, trade_price, order_type_config)
                    self.log_message(f"🔧 {symbol} Limit snap价格: ${trade_price:.{precision}f} (原: ${price:.4f})", "info")

                self.log_message(f"🔧 交易参数: {symbol} 数量{size} 类型{order_type}", "debug")
                self.log_message(f"🔄 交易尝试 {attempt+1}/{max_retries}: {side} {size} {symbol} ({order_type})", "info")

                if order_result and order_result.get("status") == "ok":
                    statuses = order_result["response"]["data"]["statuses"]
                    if statuses:
                        status = statuses[0]
                    
                        if "resting" in status:
                            order_id = status['resting']['oid']
                            self.log_trade(symbol, side, size, trade_price, "挂单", f"订单号: {order_id}")
                            self.track_pending_order(symbol, order_id, side, size, trade_price)
                            return "pending"
                        
                        elif "filled" in status:
                            filled_size = status['filled']['totalSz']
                            self.log_trade(symbol, side, filled_size, trade_price, "完全成交")
                            #  立即更新持仓状态
                            time.sleep(3)
                            self.update_real_positions()
                            return True
                        
                        elif "error" in status:
                            error_msg = status["error"]
                            raise ValueError(f"订单错误: {error_msg}")
                        else:
                            self.log_message(f" {symbol} 订单未知状态: {status}", "warning")
                            time.sleep(5)
                            self.update_real_positions()
                            new_position = self.current_positions.get(symbol, {}).get('size', 0)
                            if new_position != old_position:
                                self.log_message(f"✅ {symbol} 实际持仓已变化: {old_position} -> {new_position}", "info")
                                return True
                            continue
                    
                    self.log_trade(symbol, side, size, trade_price, "处理中", f"尝试{attempt+1}")
                    
                    wait_time = 8 if attempt == 0 else 12
                    self.log_message(f"⏳ 等待 {wait_time} 秒确认订单状态...", "info")
                    time.sleep(wait_time)
                    
                    self.update_real_positions()
                    new_position = self.current_positions.get(symbol, {}).get('size', 0)
                    
                    if new_position != old_position:
                        actual_change = new_position - old_position
                        self.log_message(f"✅ {symbol} 持仓确认: {old_position} -> {new_position} (变化: {actual_change})", "info")
                        return True
                    else:
                        self.log_message(f" {symbol} 订单接受但持仓未变化，可能为挂单", "warning")
                        if attempt < max_retries - 1:
                            self.log_message(f"🔄 准备第{attempt+2}次尝试...", "info")
                        return "pending" if attempt < max_retries - 1 else False
                
                else:
                    error_msg = order_result.get('response', {}).get('error', 'Unknown error') if order_result else 'No response'
                    self.log_message(f" {symbol} API返回错误，检查实际成交: {error_msg}", "warning")
                    time.sleep(5)
                    self.update_real_positions()
                    new_position = self.current_positions.get(symbol, {}).get('size', 0)
                    if new_position != old_position:
                        self.log_message(f"✅ {symbol} 实际已成交，忽略API错误", "info")
                        return True
                    else:
                        raise ValueError(f"订单失败: {error_msg}")
            
            except Exception as e:
                self.log_message(f" 交易尝试{attempt+1}失败 {symbol}: {str(e)}", "error")
                time.sleep(5)
                self.update_real_positions()
                new_position = self.current_positions.get(symbol, {}).get('size', 0)
                if new_position != old_position:
                    self.log_message(f"✅ {symbol} 实际已成交，忽略异常", "info")
                    return True
                    
                if attempt < max_retries - 1:
                    retry_delay = 10
                    self.log_message(f" {retry_delay}秒后进行第{attempt+2}次尝试...", "info")
                    time.sleep(retry_delay)
                else:
                    self.log_trade(symbol, side, size, trade_price if 'trade_price' in locals() else price, "最终失败", f"错误: {str(e)}")
                    return False
        return False

    def execute_reduce_position(self, symbol):
        """执行减仓操作 - 修复版本"""
        try:
            # 检查交易锁，确保同一轮询只执行一次
            if hasattr(self, '_reduce_executed') and self._reduce_executed:
                return False
                        
            if not self.connection_status:
                return False
    
            # 获取持仓信息
            position = self.current_positions.get(symbol, {})
            position_size = position.get('size', 0)  # 初始化 position_size
            
            # 如果没有持仓，直接返回
            if abs(position_size) < 0.001:
                return False
                
            entry_price = position.get('entry_price', 0)
            
            # 获取当前保证金比例
            current_margin_ratio = self.get_position_margin_ratio(symbol)
            max_margin_pct = float(self.single_coin_max_pct.get() or 40)  # 使用40%限制
            
            #  关键修复：只有在超出40%限制时才减仓
            if current_margin_ratio <= max_margin_pct:
                self.log_message(
                    f"✅ {symbol} 保证金比例正常: {current_margin_ratio:.1f}% <= {max_margin_pct}%，无需减仓", 
                    "debug"
                )
                return False
                
            price_data = self.get_stable_real_time_price(symbol)
            if not price_data:
                return False
                
            current_price = price_data['price']
            
            #  计算超出比例和减仓数量
            excess_ratio = current_margin_ratio - max_margin_pct
            reduce_percentage = excess_ratio / current_margin_ratio
            reduce_percentage = max(0.2, min(0.8, reduce_percentage))  # 限制在20%-80%
            
            reduce_size = position_size * reduce_percentage
            
            #  确保减仓数量是浮点数
            if isinstance(reduce_size, str):
                reduce_size = float(reduce_size)
                
            #  判断方向
            is_long = position_size > 0
            direction = "多头" if is_long else "空头"
            
            #  计算美元价值（空头用开仓价）
            risk_price = entry_price if not is_long else current_price
            reduce_usd_value = abs(reduce_size) * risk_price
            
            #  检查最小交易额10 USDC
            min_trade_usd = 10
            if reduce_usd_value < min_trade_usd:
                self.log_message(
                    f"⏸️ {symbol} 减仓额度不足: ${reduce_usd_value:.2f} < ${min_trade_usd}，跳过",
                    "info"
                )
                return False
            
            self.log_message(
                f" {symbol}({direction}) 触发减仓: "
                f"保证金{current_margin_ratio:.1f}% > 限制{max_margin_pct}% | "
                f"减仓{reduce_percentage*100:.1f}% | 金额${reduce_usd_value:.2f}",
                "warning"
            )
            
            # 执行减仓
            if is_long:
                success = self.execute_trade(symbol, "sell", abs(reduce_size), "market")
            else:
                success = self.execute_trade(symbol, "buy", abs(reduce_size), "market")
                
            if success:
                #  设置交易锁，确保同一轮询只执行一次
                self._reduce_executed = True
                self.log_message(f"✅ {symbol} 减仓成功", "info")
                time.sleep(2)
                self.update_real_positions()
                return True
            else:
                self.log_message(f"❌ {symbol} 减仓失败", "error")
                return False
                
        except Exception as e:
            self.log_message(f"❌ 执行减仓时出错 {symbol}: {str(e)}", "error")
            return False
    
    def execute_profit_protection(self, symbol, position_info, trend_strength):
        """利润保护减仓 - 在未达到10%止盈时保存利润"""
        try:
            pnl_percent = position_info.get('pnl_percent', 0)
            
            # 只在盈利5%-9%时执行（未达到10%止盈）
            if pnl_percent < 5 or pnl_percent >= 10:
                return False
                
            position_size = position_info.get('size', 0)
            if abs(position_size) < 0.001:
                return False
            
            reduce_percentage = 0
            reduce_reason = ""
            
            # 情况1：趋势明显转弱
            if trend_strength < 0.3 and pnl_percent >= 5:
                reduce_percentage = 0.5  # 减仓50%
                reduce_reason = f"趋势转弱(强度{trend_strength:.2f})，锁定利润"
            
            # 情况2：接近关键技术位
            elif self.near_key_resistance(symbol) and pnl_percent >= 6:
                reduce_percentage = 0.4  # 减仓40%
                reduce_reason = f"接近阻力位，提前保护利润"
            
            # 情况3：横盘时间过长
            elif self.is_consolidating(symbol) and pnl_percent >= 8:
                reduce_percentage = 0.25  # 减仓25%
                reduce_reason = f"横盘时间过长，防范利润回吐"
            
            # 情况4：波动率突然放大
            elif self.volatility_spike(symbol) and pnl_percent >= 7:
                reduce_percentage = 0.3  # 减仓30%
                reduce_reason = f"波动加剧，降低风险暴露"
            
            if reduce_percentage > 0:
                # 计算减仓数量
                reduce_size = position_size * reduce_percentage
                if isinstance(reduce_size, str):
                    reduce_size = float(reduce_size)
                    
                # 判断方向
                is_long = position_size > 0
                
                # 最小交易额检查
                current_price = position_info.get('current_price', 0)
                reduce_usd_value = abs(reduce_size) * current_price
                if reduce_usd_value < 30:
                    return False
                
                self.log_message(
                    f" {symbol} 利润保护: 盈利{pnl_percent:.1f}% | {reduce_reason} | "
                    f"减仓{reduce_percentage*100:.0f}% | 金额${reduce_usd_value:.2f}",
                    "warning"
                )
                
                # 执行减仓
                if is_long:
                    success = self.execute_trade(symbol, "sell", abs(reduce_size), "market")
                else:
                    success = self.execute_trade(symbol, "buy", abs(reduce_size), "market")
                    
                return success
            else:
                return False
                
        except Exception as e:
            self.log_message(f"利润保护减仓出错 {symbol}: {str(e)}", "error")
            return False

    def auto_trading_loop(self):
        """自动交易循环 - 修复减仓逻辑"""
        loop_count = 0
        max_consecutive_errors = 5
        error_count = 0
        
        # 新增：交易锁，防止同一币种重复交易
        trading_locks = {}
    
        while self.trading_active:
            try:
                loop_count += 1
                self.log_message(f"🔄 第{loop_count}轮自动交易检查开始...", "info")
                #  重置减仓执行锁
                self._reduce_executed = False
    
                #  第一步：检查并清理挂单状态
                self.check_pending_orders()
    
                if not self.connection_status:
                    self.log_message("❌ 交易连接已断开，停止自动交易", "error")
                    self.stop_trading()
                    break
    
                # 更新持仓和保证金状态
                self.update_real_positions()
    
                tokens = [t.strip() for t in self.tokens_entry.get().split(",") if t.strip()]
                self.log_message(f" 监控代币: {tokens}", "debug")
    
                for item in self.signal_tree.get_children():
                    self.signal_tree.delete(item)
    
                # 初始获取保证金状态
                margin_state = self.get_current_margin_state()
                current_used_margin = margin_state['total_margin_used']
                account_value = margin_state['account_value']
                total_margin_limit = float(self.total_margin_pct.get() or 60)
            
                self.log_message(f"当前保证金: {margin_state['current_ratio']:.1f}% / {total_margin_limit}%", "info")
    
                #  获取止盈信号阈值
                try:
                    profit_signal_threshold = float(self.profit_signal_threshold.get() or 0.7)
                except ValueError:
                    profit_signal_threshold = 0.7
                    self.log_message(f" 止盈信号阈值格式错误，使用默认值: {profit_signal_threshold}", "warning")
    
                executed_tokens = []
                max_trades_per_cycle = 1
                trades_executed = 0
    
                #  修复：减仓检查
                reduce_executed = False  # 确保每轮只执行一次减仓
                for token, position in list(self.current_positions.items()):
                    if not self.trading_active or reduce_executed:
                        break
                    
                    # 检查交易锁
                    if token in trading_locks and trading_locks[token] > time.time() - 60:
                        self.log_message(f" {token} 处于交易锁定期，跳过减仓检查", "debug")
                        continue
                    
                    # 直接调用减仓方法，方法内部会检查40%限制和10USDC条件
                    success = self.execute_reduce_position(token)
                    if success:
                        executed_tokens.append(token)
                        trading_locks[token] = time.time()
                        trades_executed += 1
                        reduce_executed = True  # 标记已执行减仓
                        self.log_message(f"✅ {token} 减仓执行成功", "info")
                        time.sleep(3)
                        self.update_real_positions()
                        # 更新保证金状态
                        margin_state = self.get_current_margin_state()
                        current_used_margin = margin_state['total_margin_used']
                        account_value = margin_state['account_value']
                        break  # 执行一次减仓后就跳出
                    
                #  增强止盈策略：检查现有持仓的止盈止损
                for token, position in list(self.current_positions.items()):
                    if not self.trading_active:
                        break
                    
                    #  检查交易锁
                    if token in trading_locks and trading_locks[token] > time.time() - 60:
                        self.log_message(f" {token} 处于交易锁定期，跳过止盈止损检查", "debug")
                        continue
                    
                    price_data = self.get_stable_real_time_price(token)
                    if not price_data:
                        continue
                    
                    pos_info = self.get_position_info(token, price_data['price'])
                    action = self.check_take_profit_stop_loss(pos_info)

                    
                    if action:
                        # 增强止盈逻辑：如果是止盈操作，检查信号强度
                        if action == '止盈':
                            # 获取当前信号强度
                            token_signal_data = self.get_current_token_signal(token)
                            if token_signal_data:
                                current_strength = token_signal_data['signal_score']
                                # 如果信号强度高于阈值，跳过止盈
                                if current_strength >= profit_signal_threshold:
                                    self.log_message(
                                        f"{token} 达到止盈条件但信号强劲({current_strength:.2f}>={profit_signal_threshold})，跳过止盈", 
                                        "info"
                                    )
                                    continue
                                else:
                                    self.log_message(
                                        f"{token} 达到止盈条件且信号较弱({current_strength:.2f}<{profit_signal_threshold})，执行止盈", 
                                        "info"
                                    )
                            else:
                                self.log_message(f" {token} 无法获取信号数据，执行默认止盈", "warning")
                        
                        self.log_message(f"{token} {action}: pnl {pos_info['pnl_percent']:.2f}%，自动平仓", "warning")
                        success = self.execute_close_position(token, position['size'])
                        if success:
                            self.log_message(f"✅ {token} {action} 平仓成功", "info")
                            # 设置交易锁
                            trading_locks[token] = time.time()
                            time.sleep(3)
                            self.update_real_positions()
                        else:
                            self.log_message(f" {token} {action} 平仓失败", "error")
                        continue

                
                #  新增：利润保护减仓（在止盈止损之后，信号交易之前）
                for token, position in list(self.current_positions.items()):
                    if not self.trading_active:
                        break
        
                    # 检查交易锁
                    if token in trading_locks and trading_locks[token] > time.time() - 60:
                        continue
        
                    price_data = self.get_stable_real_time_price(token)
                    if not price_data:
                        continue
        
                    pos_info = self.get_position_info(token, price_data['price'])
                    trend_strength = self.assess_trend_strength(token)  # 需要获取趋势强度
    
                    # 执行利润保护减仓
                    protection_executed = self.execute_profit_protection(token, pos_info, trend_strength)
                    if protection_executed:
                        # 设置交易锁，避免重复操作
                        trading_locks[token] = time.time()
                        time.sleep(3)
                        self.update_real_positions()
                        continue  # 跳过本次循环的后续信号处理


                # 收集所有信号
                token_signals = []
            
                for token in tokens:
                    if not self.trading_active:
                        break
    
                    #  检查交易锁
                    if token in trading_locks and trading_locks[token] > time.time() - 60:
                        self.log_message(f" {token} 处于交易锁定期，跳过信号计算", "debug")
                        continue
    
                    price_data = self.get_stable_real_time_price(token)
                    if not price_data:
                        continue
                    
                    current_price = price_data['price']
                    position_info = self.get_position_info(token, current_price)
                    historical_prices = self.get_historical_prices(token, periods=100)
                    signals = self.calculate_strategy_signals(token, historical_prices, current_price)
    
                    final_signal, operation_advice, signal_strength = self.determine_final_signal_with_position(
                        signals, position_info, token
                    )
                
                    buy_str = signal_strength.get('buy_strength', 0)
                    sell_str = signal_strength.get('sell_strength', 0)
                    signal_score = max(buy_str, sell_str)
                    dominant_dir = "买入" if buy_str > sell_str else "卖出" if sell_str > buy_str else "持有"
                
                    token_signals.append({
                        'token': token,
                        'final_signal': final_signal,
                        'signal_strength': signal_strength,
                        'operation_advice': operation_advice,
                        'position_info': position_info,
                        'price_data': price_data,
                        'signals': signals,
                        'signal_score': signal_score,
                        'dominant_dir': dominant_dir
                    })
                
                    self.update_signal_display(
                        token, price_data, position_info, signals, final_signal, operation_advice
                    )
            
                # 加仓优先策略：分离处理信号
                new_position_signals = []
                increase_position_signals = []
                decrease_position_signals = []
            
                for token_data in token_signals:
                    token = token_data['token']
                    final_signal = token_data['final_signal']
                    position_info = token_data['position_info']
                    position_size = position_info['size']
                    is_long = position_info.get('is_long', False)
                    is_short = position_info.get('is_short', False)
                
                    has_position = position_info['status'] != '无持仓'
                    is_opening_new_position = (final_signal != "持有" and not has_position)
                    is_increasing_position = has_position and (
                        (final_signal == "买入" and is_long) or 
                        (final_signal == "卖出" and is_short)
                    )
                    is_decreasing_position = has_position and (
                        (final_signal == "卖出" and is_long) or 
                        (final_signal == "买入" and is_short)
                    )
                
                    self.log_message(
                        f"{token} 分类: {final_signal} | "
                        f"持仓: {position_info['status']} | "
                        f"新开: {is_opening_new_position} | 加仓: {is_increasing_position} | 减仓: {is_decreasing_position} | "
                        f"强度: {token_data['signal_score']:.2f}", 
                        "info"
                    )
                
                    if is_opening_new_position:
                        new_position_signals.append(token_data)
                        self.log_message(f"✅ {token} 符合新开仓条件，加入执行队列", "info")
                    elif is_increasing_position:
                        increase_position_signals.append(token_data)
                        self.log_message(f"✅ {token} 符合加仓条件，加入执行队列", "info")
                    elif is_decreasing_position:
                        decrease_position_signals.append(token_data)
                        self.log_message(f"✅ {token} 符合减仓条件，加入执行队列", "info")
            
                self.log_message(f" 信号分类: 新开{len(new_position_signals)} | 加仓{len(increase_position_signals)} | 减仓{len(decrease_position_signals)}", "info")
            
                # 加仓优先：按主导强度排序
                increase_position_signals.sort(key=lambda x: x['signal_score'], reverse=True)
                new_position_signals.sort(key=lambda x: x['signal_score'], reverse=True)
                decrease_position_signals.sort(key=lambda x: x['signal_score'], reverse=True)
            
                # 第一优先级：加仓（增强已有盈利仓位）
                for token_data in increase_position_signals:
                    if not self.trading_active or trades_executed >= max_trades_per_cycle:
                        break
                    
                    token = token_data['token']
                    
                    if token in trading_locks and trading_locks[token] > time.time() - 60:
                        continue
                    
                    final_signal = token_data['final_signal']
                    signal_strength = token_data['signal_strength']
                    operation_advice = token_data['operation_advice']
                    position_info = token_data['position_info']
                    current_price = token_data['price_data']['price']
                
                    self.log_message(f"开始处理加仓信号: {token} {final_signal}", "info")
                
                    risk_ok, risk_msg, available_margin = self.enhanced_risk_check_dynamic(
                        token, False, current_used_margin, account_value
                    )
                
                    if not risk_ok:
                        self.log_message(f"{token} 风险检查失败: {risk_msg}", "warning")
                        continue
                
                    #  执行加仓交易
                    success = self.execute_signal_trade(token, final_signal, position_info, current_price, signal_strength, available_margin)
                    if success:
                        executed_tokens.append(token)
                        trading_locks[token] = time.time()
                        trades_executed += 1
                        self.log_message(f" {token} 加仓执行成功: {final_signal}", "info")
                        
                        time.sleep(5)
                        self.update_real_positions()
                        margin_state = self.get_current_margin_state()
                        current_used_margin = margin_state['total_margin_used']
                        account_value = margin_state['account_value']
            
                #  第二优先级：新开仓
                if trades_executed < max_trades_per_cycle:
                    for token_data in new_position_signals:
                        if not self.trading_active or trades_executed >= max_trades_per_cycle:
                            break
                        
                        token = token_data['token']
                        
                        if token in trading_locks and trading_locks[token] > time.time() - 60:
                            continue
                        
                        final_signal = token_data['final_signal']
                        signal_strength = token_data['signal_strength']
                        operation_advice = token_data['operation_advice']
                        position_info = token_data['position_info']
                        current_price = token_data['price_data']['price']
                    
                        self.log_message(f"开始处理新开仓信号: {token} {final_signal}", "info")
                    
                        risk_ok, risk_msg, available_margin = self.enhanced_risk_check_dynamic(
                            token, True, current_used_margin, account_value
                        )
                    
                        if not risk_ok:
                            self.log_message(f" {token} 风险检查失败: {risk_msg}", "warning")
                            continue
                    
                        if final_signal == "买入":
                            new_size = self.calculate_position_size(token, is_long=True, available_margin=available_margin)
                        else:
                            new_size = self.calculate_position_size(token, is_long=False, available_margin=available_margin)
                    
                        self.log_message(f"🔧 {token} 计算仓位: {new_size}", "info")
                    
                        if abs(new_size) <= 0.00001:
                            self.log_message(f" {token} 计算仓位过小: {new_size}", "warning")
                            continue
                    
                        self.log_message(f"✅ {token} 准备执行: {final_signal} {new_size}", "info")
                    
                        success = False
                        if final_signal == "买入":
                            success = self.execute_trade(token, "buy", new_size, "market")
                        else:
                            success = self.execute_trade(token, "sell", abs(new_size), "market")
                    
                        if success:
                            executed_tokens.append(token)
                            trading_locks[token] = time.time()
                            trades_executed += 1
                            self.log_message(f"{token} 新开仓执行成功: {final_signal}", "info")
                            
                            time.sleep(5)
                            self.update_real_positions()
                            margin_state = self.get_current_margin_state()
                            current_used_margin = margin_state['total_margin_used']
                            account_value = margin_state['account_value']
                            break
                        else:
                            self.log_message(f" {token} 交易执行失败", "warning")
            
                #  第三优先级：减仓（风险控制）
                if trades_executed < max_trades_per_cycle:
                    for token_data in decrease_position_signals:
                        if not self.trading_active or trades_executed >= max_trades_per_cycle:
                            break
                        
                        token = token_data['token']
                        
                        if token in trading_locks and trading_locks[token] > time.time() - 60:
                            continue
                        
                        final_signal = token_data['final_signal']
                        signal_strength = token_data['signal_strength']
                        operation_advice = token_data['operation_advice']
                        position_info = token_data['position_info']
                        current_price = token_data['price_data']['price']
                    
                        self.log_message(f"开始处理减仓信号: {token} {final_signal}", "info")
                    
                        risk_ok, risk_msg, available_margin = self.enhanced_risk_check_dynamic(
                            token, False, current_used_margin, account_value
                        )
                    
                        if not risk_ok:
                            self.log_message(f" {token} 风险检查失败: {risk_msg}", "warning")
                            continue
                    
                        success = self.execute_signal_trade(token, final_signal, position_info, current_price, signal_strength, available_margin)
                        if success:
                            executed_tokens.append(token)
                            trading_locks[token] = time.time()
                            trades_executed += 1
                            self.log_message(f" {token} 减仓执行成功: {final_signal}", "info")
                            
                            time.sleep(5)
                            self.update_real_positions()
                            margin_state = self.get_current_margin_state()
                            current_used_margin = margin_state['total_margin_used']
                            account_value = margin_state['account_value']
                            break
            
                self.log_message(f"本轮执行交易: {len(executed_tokens)}个币种", "info")
            
                error_count = 0
                interval = int(self.check_interval.get() or 60)
                for i in range(interval):
                    if not self.trading_active:
                        break
                    time.sleep(1)
            
            except Exception as e:
                error_count += 1
                self.log_message(f"自动交易循环出错 (第{error_count}次): {str(e)}", "error")
                if error_count >= max_consecutive_errors:
                    self.log_message(" 连续错误过多，停止自动交易", "error")
                    self.stop_trading()
                    break
                time.sleep(min(30 * error_count, 300))

    def get_current_margin_state(self):
        """获取当前保证金状态"""
        try:
            if not self.connection_status:
                return {'total_margin_used': 0, 'account_value': 0, 'current_ratio': 0}
            
            wallet_address = self.wallet_address.get().strip()
            user_state = self.info.user_state(wallet_address)
            margin_summary = user_state.get('marginSummary', {})
            total_margin_used = float(margin_summary.get('totalMarginUsed', 0))
            account_value = float(margin_summary.get('accountValue', 0))
            current_ratio = (total_margin_used / account_value) * 100 if account_value > 0 else 0
        
            return {
                'total_margin_used': total_margin_used,
                'account_value': account_value,
                'current_ratio': current_ratio
            }
        except Exception as e:
            self.log_message(f" 获取保证金状态出错: {str(e)}", "error")
            return {'total_margin_used': 0, 'account_value': 0, 'current_ratio': 0}

    def get_position_margin_ratio(self, symbol):
        """计算仓位保证金比例"""
        try:
            margin_state = self.get_current_margin_state()
            account_value = margin_state['account_value']
            
            if account_value <= 0:
                return 0
                
            position = self.current_positions.get(symbol, {})
            position_size = position.get('size', 0)
            
            if abs(position_size) < 0.001:
                return 0
                
            # 获取当前价格
            price_data = self.get_stable_real_time_price(symbol)
            if not price_data:
                return 0
                
            current_price = price_data['price']
            entry_price = position.get('entry_price', current_price)
            
            # 计算风险价值（考虑做空方向）
            if position_size > 0:  # 多头仓位
                risk_value = abs(position_size) * current_price
            else:  # 空头仓位
                risk_value = abs(position_size) * entry_price
            
            #  修复：正确从 coins.json 获取杠杆配置
            trading_config = self.coin_config.get("trading_config", {})
            symbol_config = trading_config.get(symbol.upper(), trading_config.get("DEFAULT", {}))
            
            # 调试日志：显示实际配置
            self.log_message(
                f" {symbol} 杠杆配置: "
                f"配置杠杆: {self.leverage.get()} | "
                f"coins.json最大杠杆: {symbol_config.get('max_leverage', '未找到')} | "
                f"默认杠杆: {trading_config.get('DEFAULT', {}).get('max_leverage', '未找到')}",
                "debug"
            )
            
            # 获取配置的杠杆
            try:
                configured_leverage = float(self.leverage.get() or 3)
            except ValueError:
                configured_leverage = 3
                
            # 从 coins.json 获取最大允许杠杆
            max_allowed_leverage = symbol_config.get("max_leverage", 
                                  trading_config.get("DEFAULT", {}).get("max_leverage", 5))
            
            used_leverage = min(configured_leverage, max_allowed_leverage)
            
            # 保证金占用 = 风险价值 / 杠杆
            margin_used = risk_value / used_leverage
            margin_ratio = (margin_used / account_value) * 100 if account_value > 0 else 0
            
            # 详细日志
            self.log_message(
                f" {symbol} 保证金计算详情:\n"
                f"  风险价值: ${risk_value:.2f}\n"
                f"  配置杠杆: {configured_leverage}x\n"
                f"  允许杠杆: {max_allowed_leverage}x\n"
                f"  使用杠杆: {used_leverage}x\n"
                f"  保证金占用: ${margin_used:.2f}\n"
                f"  账户价值: ${account_value:.2f}\n"
                f"  保证金比率: {margin_ratio:.1f}%",
                "debug"
            )
            
            return margin_ratio
            
        except Exception as e:
            self.log_message(f" 计算保证金比例失败 {symbol}: {str(e)}", "error")
            return 0

    def check_single_coin_position_limit(self, symbol, final_signal, position_info):
        """检查单个币种仓位是否超过限制 - 基于保证金占用"""
        try:
            if not self.connection_status:
                return False
        
            # 获取账户价值
            margin_state = self.get_current_margin_state()
            account_value = margin_state['account_value']
            
            if account_value <= 0:
                return False
        
            # 获取当前持仓
            current_position = self.current_positions.get(symbol, {})
            position_size = current_position.get('size', 0)
            
            # 如果没有持仓，直接返回False
            if abs(position_size) < 0.001:
                return False
                
            # 获取当前价格
            current_price_data = self.get_stable_real_time_price(symbol)
            if not current_price_data:
                return False
        
            current_price = current_price_data['price']
            
            # 计算仓位价值
            position_value = abs(position_size) * current_price
            
            #  关键修复：计算保证金占用而不是仓位价值比例
            # 从配置获取实际使用的杠杆
            try:
                configured_leverage = float(self.leverage.get() or 3)
            except ValueError:
                configured_leverage = 3
                
            # 从 coins.json 获取最大允许杠杆
            trading_config = self.coin_config.get("trading_config", {})
            symbol_config = trading_config.get(symbol.upper(), trading_config.get("DEFAULT", {}))
            max_allowed_leverage = symbol_config.get("max_leverage", 5)
            used_leverage = min(configured_leverage, max_allowed_leverage)
            
            # 计算实际保证金占用
            margin_used = position_value / used_leverage
            margin_ratio = (margin_used / account_value) * 100 if account_value > 0 else 0

            # 获取单币保证金限制（使用max_margin_pct配置）
            try:
                single_margin_max_ratio = float(self.max_margin_pct.get() or 20)
            except ValueError:
                single_margin_max_ratio = 20.0

            # 记录详细的保证金信息
            self.log_message(
                f" {symbol} 保证金检查:\n"
                f"  持仓数量: {position_size}\n"
                f"  当前价格: ${current_price:.4f}\n"
                f"  仓位价值: ${position_value:.2f}\n"
                f"  使用杠杆: {used_leverage}x\n"
                f"  保证金占用: ${margin_used:.2f}\n"
                f"  账户价值: ${account_value:.2f}\n"
                f"  保证金比率: {margin_ratio:.1f}% / {single_margin_max_ratio}%",
                "info"
            )

            # 检查是否是加仓操作
            is_increasing_position = (
                (final_signal == "买入" and position_size >= 0) or
                (final_signal == "卖出" and position_size <= 0)
            )

            if is_increasing_position and margin_ratio >= single_margin_max_ratio:
                self.log_message(f" {symbol} 保证金使用已达{margin_ratio:.1f}%，超过单币限制{single_margin_max_ratio}%，阻止加仓", "warning")
                return True
            
            return False

        except Exception as e:
            self.log_message(f"检查单个币种仓位限制时出错: {str(e)}", "error")
            return False

    def enhanced_risk_check_dynamic(self, token, is_opening_new_position, current_used_margin, account_value):
        """动态风险检查"""
        try:
            if not self.connection_status:
                return False, "未连接交易所", 0

            if account_value <= 0:
                return False, "账户价值为0", 0

            #  使用有效保证金（包括挂单）
            effective_margin = self.get_effective_margin_usage()
            current_ratio = effective_margin['effective_ratio']
            total_effective_used = effective_margin['total_effective_used']
        
            total_margin_limit = float(self.total_margin_pct.get() or 60)

            # 减仓放宽检查
            if not is_opening_new_position and current_ratio >= total_margin_limit:
                self.log_message(f" {token} 当前有效使用率{current_ratio:.1f}%超限，但为减仓操作，允许执行以降低风险", "warning")
                # 计算可用
                max_total_margin = account_value * (total_margin_limit / 100)
                available_margin = max(0, max_total_margin - total_effective_used)
                return True, "超限但减仓允许", available_margin  # 放宽返回True
        
            #  严格检查：当前是否已经超过总限制（包括挂单）
            if current_ratio >= total_margin_limit:
                return False, f"有效保证金使用率{current_ratio:.1f}%已超过限制{total_margin_limit}%", 0

            #  关键修复：如果有挂单，拒绝新开仓
            if is_opening_new_position and self.has_pending_orders_for_token(token):
                return False, "存在挂单，拒绝新开仓", 0

            # 计算可用保证金（考虑挂单占用）
            max_total_margin = account_value * (total_margin_limit / 100)
            available_margin = max(0, max_total_margin - total_effective_used)
        
            #  保守策略：可用少于5%时直接拒绝
            available_ratio = (available_margin / account_value) * 100
            if is_opening_new_position and available_ratio < 5:
                return False, f"可用保证金过少({available_ratio:.1f}%)", available_margin

            # 单币保证金限制
            single_margin_pct = float(self.max_margin_pct.get() or 20)
            single_coin_max_margin = account_value * (single_margin_pct / 100)
        
            # 实际可用的保证金
            actual_available_margin = min(single_coin_max_margin, available_margin)
        
            if actual_available_margin <= 0:
                return False, "无可用保证金额度", 0

            # 持仓数量检查
            if is_opening_new_position:
                positions_count = len(self.current_positions)
                max_coins = int(self.max_coins.get() or 5)
                if positions_count >= max_coins:
                    return False, f"持仓数量{positions_count}已达上限{max_coins}", actual_available_margin

            # 对于新开仓，保守检查
            if is_opening_new_position and available_ratio < 10:
                return False, f"可用保证金较少({available_ratio:.1f}%)，保守拒绝", actual_available_margin
        
            return True, "通过", actual_available_margin

        except Exception as e:
            self.log_message(f" 动态风险检查出错: {str(e)}", "error")
            return False, "检查出错", 0

    def execute_close_position(self, symbol, size):
        """平仓执行"""
        if size > 0:
            return self.execute_trade(symbol, "sell", size, "market")
        elif size < 0:
            return self.execute_trade(symbol, "buy", abs(size), "market")
        else:
            self.log_message(f" {symbol} 无仓位可平", "warning")
            return True

    def initialize_state_recovery(self):
        """初始化状态恢复"""
        if self.connection_status:
            self.update_real_positions()
            self.log_message("✅ 状态恢复完成 - 已同步交易所持仓", "info")
        else:
            self.current_positions = {}
            self.update_position_display()
            self.log_message("✅ 状态恢复初始化完成 - 无持仓数据", "info")

    def get_position_info(self, symbol, current_price):
        """获取持仓信息"""
        position = self.current_positions.get(symbol)
        if position:
            entry_price = position.get('entry_price', current_price)
            position_size = position.get('size', 0)
            unrealized_pnl = position.get('unrealized_pnl', 0)
        
            is_long = position_size > 0
            is_short = position_size < 0
        
            if is_long:
                if entry_price > 0:
                    pnl_percent = ((current_price - entry_price) / entry_price) * 100
                else:
                    pnl_percent = 0
            elif is_short:
                if entry_price > 0:
                    pnl_percent = ((entry_price - current_price) / entry_price) * 100
                else:
                    pnl_percent = 0
            else:
                pnl_percent = 0
        
            return {
                'status': '持有多头' if position_size > 0 else '持有空头' if position_size < 0 else '无持仓',
                'size': position_size,
                'entry_price': entry_price,
                'current_price': current_price,
                'unrealized_pnl': unrealized_pnl,
                'pnl_percent': pnl_percent,
                'is_long': is_long,
                'is_short': is_short
            }
        else:
            return {
                'status': '无持仓',
                'size': 0,
                'entry_price': 0,
                'current_price': current_price,
                'unrealized_pnl': 0,
                'pnl_percent': 0,
                'is_long': False,
                'is_short': False
            }

    def get_current_token_signal(self, token):
        """获取指定币种的当前信号数据"""
        try:
            price_data = self.get_stable_real_time_price(token)
            if not price_data:
                return None
                
            current_price = price_data['price']
            position_info = self.get_position_info(token, current_price)
            historical_prices = self.get_historical_prices(token, periods=100)
            
            if not historical_prices or len(historical_prices) < 60:
                self.log_message(f" {token} 历史数据不足，无法计算信号", "warning")
                return None
                
            signals = self.calculate_strategy_signals(token, historical_prices, current_price)
            
            final_signal, operation_advice, signal_strength = self.determine_final_signal_with_position(
                signals, position_info, token
            )
            
            buy_strength = signal_strength.get('buy_strength', 0)
            sell_strength = signal_strength.get('sell_strength', 0)
            signal_score = max(buy_strength, sell_strength)
            
            return {
                'final_signal': final_signal,
                'signal_strength': signal_strength,
                'signal_score': signal_score,
                'operation_advice': operation_advice
            }
            
        except Exception as e:
            self.log_message(f" 获取 {token} 信号数据失败: {str(e)}", "error")
            return None

    def update_position_display(self):
        """更新持仓显示"""
        for item in self.position_tree.get_children():
            self.position_tree.delete(item)
    
        if not self.current_positions:
            self.position_tree.insert("", "end", values=(
                "无持仓", "-", "-", "-", "-", "-"
            ))
        else:
            for symbol, position in self.current_positions.items():
                current_price_data = self.get_stable_real_time_price(symbol)
                if current_price_data:
                    current_price = current_price_data['price']
                    position_info = self.get_position_info(symbol, current_price)
                
                    position_size = position_info['size']
                    entry_price = position_info['entry_price']
                    unrealized_pnl = position_info['unrealized_pnl']
                    pnl_percent = position_info['pnl_percent']
                
                    pnl_color = "🟢" if unrealized_pnl >= 0 else "🔴"
                    pnl_percent_color = "🟢" if pnl_percent >= 0 else "🔴"
                
                    direction = "多" if position_info['is_long'] else "空" if position_info['is_short'] else "-"
                
                    self.position_tree.insert("", "end", values=(
                        f"{symbol}({direction})",
                        f"{position_size:.4f}",
                        f"${entry_price:.4f}",
                        f"${current_price:.4f}",
                        f"{pnl_color}${unrealized_pnl:+.2f}",
                        f"{pnl_percent_color}{pnl_percent:+.2f}%"
                    ))

    def get_balance(self):
        """获取账户余额"""
        if not self.connection_status:
            self.log_message("请先连接交易所", "error")
            return
        
        try:
            wallet_address = self.wallet_address.get().strip()
            user_state = self.info.user_state(wallet_address)
            margin_summary = user_state.get('marginSummary', {})
            account_value = margin_summary.get('accountValue', 'N/A')
            total_margin_used = margin_summary.get('totalMarginUsed', '0')
            
            self.log_message(f" 账户总价值: {account_value} USDC", "info")
            self.log_message(f"已用保证金: {total_margin_used} USDC", "info")
            
        except Exception as e:
            self.log_message(f" 获取余额时出错: {str(e)}", "error")

    def start_trading(self):
        """开始交易"""
        if not self.connection_status:
            self.log_message("请先连接交易所", "error")
            return
            
        self.trading_active = True
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        
        self.log_message(" 开始自动交易", "info")
        
        self.trading_thread = threading.Thread(target=self.auto_trading_loop, daemon=True)
        self.trading_thread.start()

    def stop_trading(self):
        """停止交易"""
        self.trading_active = False
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.log_message("🛑 停止自动交易", "info")

    def load_config(self):
        """从文件加载配置"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                self.wallet_address.delete(0, tk.END)
                self.wallet_address.insert(0, config.get('wallet_address', ''))

                #止盈信号阈值
                self.profit_signal_threshold.delete(0, tk.END)
                self.profit_signal_threshold.insert(0, config.get('profit_signal_threshold', '0.7'))

                self.private_key.delete(0, tk.END)
                self.private_key.insert(0, config.get('private_key', ''))
                
                self.network_var.set(config.get('network', 'testnet'))

                self.kline_interval_var.set(config.get('kline_interval', '1d'))  # 默认1d
                
                self.tokens_entry.delete(0, tk.END)
                self.tokens_entry.insert(0, config.get('tokens', ''))
                
                
                self.execution_mode_var.set(config.get('execution_mode', 'weighted'))
                
                weight_preset = config.get('weight_preset', '平衡稳健型')
                self.weight_preset_var.set(weight_preset)
                
                self.strategy_weights.delete(0, tk.END)
                self.strategy_weights.insert(0, config.get('strategy_weights', '1.5,1.2,1.0,0.8'))
                
                self.signal_threshold.delete(0, tk.END)
                self.signal_threshold.insert(0, config.get('signal_threshold', '0.6'))
                
                self.max_margin_pct.delete(0, tk.END)
                self.max_margin_pct.insert(0, config.get('max_margin_pct', '20'))
                
                self.total_margin_pct.delete(0, tk.END)
                self.total_margin_pct.insert(0, config.get('total_margin_pct', '60'))
                
                self.max_coins.delete(0, tk.END)
                self.max_coins.insert(0, int(config.get('max_coins', 5)))
                
                self.take_profit_pct.delete(0, tk.END)
                self.take_profit_pct.insert(0, config.get('take_profit_pct', '15'))
                
                self.stop_loss_pct.delete(0, tk.END)
                self.stop_loss_pct.insert(0, config.get('stop_loss_pct', '8'))
                
                self.margin_stop_pct.delete(0, tk.END)
                self.margin_stop_pct.insert(0, config.get('margin_stop_pct', '30'))
                
                self.margin_size.delete(0, tk.END)
                self.margin_size.insert(0, config.get('margin_size', '100'))
                
                self.leverage.delete(0, tk.END)
                self.leverage.insert(0, config.get('leverage', '3'))
                
                self.check_interval.delete(0, tk.END)
                self.check_interval.insert(0, config.get('check_interval', '60'))
                
                self.auto_rebalance_var.set(config.get('auto_rebalance', True))
                
                weights_text = config.get('strategy_weights', '1.5,1.2,1.0,0.8')
                self.parse_strategy_weights(weights_text)
                
                self.log_message("✅ 配置已从文件加载", "info")
                
            else:
                self.set_default_values()
                self.log_message(" 配置文件不存在，已加载默认配置", "warning")
                
        except Exception as e:
            self.log_message(f" 加载配置时出错: {str(e)}", "error")
            self.set_default_values()

    def set_default_values(self):
        """设置默认配置值"""
        self.wallet_address.delete(0, tk.END)
        self.wallet_address.insert(0, "0xYourWalletAddressHere")
        
        self.private_key.delete(0, tk.END)
        self.private_key.insert(0, "")
        
        self.tokens_entry.delete(0, tk.END)
        self.tokens_entry.insert(0, "ETH, BTC, SOL")

        self.single_coin_max_pct.delete(0, tk.END)
        self.single_coin_max_pct.insert(0, "40")

        self.weight_preset_var.set("平衡稳健型")
        self.strategy_weights.delete(0, tk.END)
        self.strategy_weights.insert(0, "1.5,1.2,1.0,0.8")
        
        self.max_margin_pct.delete(0, tk.END)
        self.max_margin_pct.insert(0, "20")
        
        self.total_margin_pct.delete(0, tk.END)
        self.total_margin_pct.insert(0, "60")
        
        self.max_coins.delete(0, tk.END)
        self.max_coins.insert(0, "5")
        
        self.take_profit_pct.delete(0, tk.END)
        self.take_profit_pct.insert(0, "15")
        
        self.stop_loss_pct.delete(0, tk.END)
        self.stop_loss_pct.insert(0, "8")
        
        self.margin_stop_pct.delete(0, tk.END)
        self.margin_stop_pct.insert(0, "30")
        
        self.margin_size.delete(0, tk.END)
        self.margin_size.insert(0, "100")
        
        self.leverage.delete(0, tk.END)
        self.leverage.insert(0, "3")
        
        self.check_interval.delete(0, tk.END)
        self.check_interval.insert(0, "60")
        
        self.log_message("默认配置已加载", "info")

    def parse_strategy_weights(self, weights_text):
        """解析策略权重配置"""
        try:
            weight_values = [w.strip() for w in weights_text.split(',') if w.strip()]
            strategy_order = ['ma', 'rsi', 'macd', 'bollinger']
            weights = {}
        
            for i, weight_str in enumerate(weight_values):
                if i < len(strategy_order):
                    try:
                        weight_value = float(weight_str)
                        strategy = strategy_order[i]
                        weights[strategy] = weight_value
                    except ValueError:
                        weights[strategy_order[i]] = 1.0
                else:
                    break
        
            for i in range(len(weight_values), len(strategy_order)):
                weights[strategy_order[i]] = 1.0
        
            total = sum(weights.values())
            if total > 0:
                for key in weights:
                    weights[key] = round(weights[key] / total, 4)
        
            self.strategy_weights_config.update(weights)
            self.log_message(f"✅ 策略权重已更新: {self.strategy_weights_config}", "info")
        
        except Exception as e:
            self.log_message(f" 解析策略权重时出错: {str(e)}", "error")
            self.strategy_weights_config = {'ma': 0.3, 'rsi': 0.25, 'macd': 0.25, 'bollinger': 0.2}
            self.log_message(f"🔄 使用默认权重: {self.strategy_weights_config}", "info")

    def test_strategies(self):
        """测试策略功能"""
        try:
            if not self.connection_status:
                self.log_message("❌ 请先连接交易所", "error")
                return
                
            tokens = [t.strip() for t in self.tokens_entry.get().split(",") if t.strip()]
            if not tokens:
                self.log_message("❌ 请先填写交易代币", "error")
                return
            
            self.log_message(" 开始策略测试...", "info")
            
            for item in self.signal_tree.get_children():
                self.signal_tree.delete(item)
            
            for token in tokens:
                self.log_message(f"测试 {token} 的策略信号...", "info")
                
                price_data = self.get_stable_real_time_price(token)
                if not price_data:
                    continue
                    
                current_price = price_data['price']
                position_info = self.get_position_info(token, current_price)
                historical_prices = self.get_historical_prices(token, periods=100)
                signals = self.calculate_strategy_signals(token, historical_prices, current_price)
                
                final_signal, operation_advice, signal_strength = self.determine_final_signal_with_position(
                    signals, position_info, token
                )
                
                self.update_signal_display(
                    token, price_data, position_info, signals, final_signal, operation_advice
                )
                
                self.log_message(f"✅ {token}: 价格${current_price:.2f} | 信号:{final_signal} | 强度:买入{signal_strength.get('buy_strength', 0):.2f}", "info")
            
            self.log_message(" 策略测试完成！", "info")
            
        except Exception as e:
            self.log_message(f" 策略测试时出错: {str(e)}", "error")

    def run_backtest(self):
        """运行回测"""
        try:
            if not self.tokens_entry.get():
                self.log_message(" 请先填写交易代币", "error")
                return
            
            tokens = [t.strip() for t in self.tokens_entry.get().split(",") if t.strip()]
            start_date = "2025-01-01"
            end_date = "2025-10-30"
            
            self.log_message(f" 开始回测: {tokens}, 期间 {start_date} to {end_date}", "info")
            
            results = {}
            for token in tokens:
                historical_data = self.load_historical_data(token, start_date, end_date)
                if not historical_data.empty:
                    backtest_result = self.simulate_strategy(token, historical_data)
                    results[token] = backtest_result
                    self.log_message(f"✅ {token} 回测完成: 胜率 {backtest_result['win_rate']:.2%}, 总回报 {backtest_result['total_return']:.2%}", "info")
                else:
                    self.log_message(f" {token} 历史数据不足", "warning")
            
            self.display_backtest_results(results)
            
            self.log_message(" 回测完成！", "info")
            
        except Exception as e:
            self.log_message(f" 回测出错: {str(e)}", "error")
    
    def simulate_strategy(self, symbol, data):
        """模拟策略执行"""
        if data.empty:
            return {'win_rate': 0, 'total_return': 0, 'trades': 0}
        
        positions = 0
        entry_price = 0
        trades = []
        balance = 10000  # 初始资金
        
        for i in range(len(data)):
            row = data.iloc[i]
            current_price = row['close']
            
            # 模拟信号（用真实calculate_strategy_signals）
            historical = data['close'].iloc[max(0, i-100):i+1].tolist()  # 最近100点
            if len(historical) < 60:
                continue  # 跳过数据不足，避免警告
            
            signals = self.calculate_strategy_signals(symbol, historical, current_price)
            
            #  修复：用完整get_position_info模拟持仓
            position_info = self.get_position_info(symbol, current_price)
            position_info['size'] = positions  # 覆盖模拟持仓大小
            
            final_signal = self.determine_final_signal_with_position(signals, position_info, symbol)[0]
            
            # 模拟执行（简化，无杠杆/费用）
            if final_signal == "买入" and positions == 0:
                positions = balance / current_price * 0.1  # 10%仓位
                entry_price = current_price
                trades.append({'type': 'buy', 'price': current_price, 'time': row['open_time']})
            elif final_signal == "卖出" and positions > 0:
                pnl = (current_price - entry_price) / entry_price
                balance += positions * current_price * pnl
                trades.append({'type': 'sell', 'price': current_price, 'pnl': pnl, 'time': row['open_time']})
                positions = 0
            
        # 计算绩效
        wins = len([t for t in trades if t.get('pnl', 0) > 0])
        win_rate = wins / len(trades) if trades else 0
        total_return = (balance - 10000) / 10000
        
        return {'win_rate': win_rate, 'total_return': total_return, 'trades': len(trades), 'balance': balance}
    
    def load_historical_data(self, symbol, start_date, end_date):
        """加载历史数据（从CSV或API，支持分页拉取长历史）"""
        import time  # 用于分页延时
        
        # 优先从本地CSV加载（预下载Binance数据）
        csv_file = f"{symbol}_historical_{self.kline_interval_var.get()}.csv"  # 加间隔区分文件
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file, parse_dates=['open_time'])
            df = df[(df['open_time'] >= start_date) & (df['open_time'] <= end_date)]
            if not df.empty:
                self.log_message(f" 从本地CSV加载 {symbol} {len(df)}条数据", "info")
                return df
        
        # Fallback: 用API拉取（分页处理长历史）
        self.log_message(f" 从Binance拉取 {symbol} 历史数据 (间隔: {self.kline_interval_var.get()})", "info")
        binance_symbol = f"{symbol}USDT"
        url = "https://api.binance.com/api/v3/klines"
        
        # 时间戳
        start_ts = int(pd.to_datetime(start_date).timestamp() * 1000)
        end_ts = int(pd.to_datetime(end_date).timestamp() * 1000)
        
        all_data = []
        current_start = start_ts
        
        while current_start < end_ts:
            params = {
                'symbol': binance_symbol,
                'interval': self.kline_interval_var.get(),
                'startTime': current_start,
                'endTime': end_ts,
                'limit': 1000  # 最大1000条/次
            }
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                self.log_message(f" Binance API失败 {symbol}: HTTP {response.status_code}", "warning")
                break
            
            data_batch = response.json()
            if not data_batch:
                break
            
            all_data.extend(data_batch)
            
            # 分页推进：下一批从最后一条+1开始
            current_start = data_batch[-1][0] + 1  # open_time +1ms
            
            self.log_message(f" 已拉取 {len(all_data)} 条 {symbol} 数据批次", "debug")
            time.sleep(0.1)
        
        if not all_data:
            self.log_message(f" {symbol} 无历史数据可用", "warning")
            return pd.DataFrame()
        
        # 修复：正确12列定义
        columns = [
            'open_time', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'number_of_trades', 
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ]
        df = pd.DataFrame(all_data, columns=columns)
        
        # 类型转换
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df['close'] = df['close'].astype(float)  # 用于信号计算
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        # 过滤日期范围
        df = df[(df['open_time'] >= start_date) & (df['open_time'] <= end_date)]
        
        # 保存本地CSV
        df.to_csv(csv_file, index=False)
        self.log_message(f"✅ {symbol} 拉取完成: {len(df)} 条数据 (间隔: {self.kline_interval_var.get()})", "info")
        
        return df
    
    def load_historical_data(self, symbol, start_date, end_date):
        """加载历史数据"""
        import time  # 用于分页延时
        
        # 优先从本地CSV加载
        csv_file = f"{symbol}_historical_{self.kline_interval_var.get()}.csv"  # 加间隔区分文件
        if os.path.exists(csv_file):
            df = pd.read_csv(csv_file, parse_dates=['open_time'])
            df = df[(df['open_time'] >= start_date) & (df['open_time'] <= end_date)]
            if not df.empty:
                self.log_message(f"从本地CSV加载 {symbol} {len(df)}条数据", "info")
                return df
        
        # Fallback: 用API拉取（分页处理长历史）
        self.log_message(f" 从Binance拉取 {symbol} 历史数据 (间隔: {self.kline_interval_var.get()})", "info")
        binance_symbol = f"{symbol}USDT"
        url = "https://api.binance.com/api/v3/klines"
        
        # 时间戳
        start_ts = int(pd.to_datetime(start_date).timestamp() * 1000)
        end_ts = int(pd.to_datetime(end_date).timestamp() * 1000)
        
        all_data = []
        current_start = start_ts
        
        while current_start < end_ts:
            params = {
                'symbol': binance_symbol,
                'interval': self.kline_interval_var.get(),
                'startTime': current_start,
                'endTime': end_ts,
                'limit': 1000  # 最大1000条/次
            }
            response = requests.get(url, params=params, timeout=10)
            
            if response.status_code != 200:
                self.log_message(f" Binance API失败 {symbol}: HTTP {response.status_code}", "warning")
                break
            
            data_batch = response.json()
            if not data_batch:
                break
            
            all_data.extend(data_batch)
            
            # 分页推进：下一批从最后一条+1开始
            current_start = data_batch[-1][0] + 1  # open_time +1ms
            
            self.log_message(f" 已拉取 {len(all_data)} 条 {symbol} 数据批次", "debug")
            time.sleep(0.1)
        
        if not all_data:
            self.log_message(f" {symbol} 无历史数据可用", "warning")
            return pd.DataFrame()
        
        # 修复：正确12列定义
        columns = [
            'open_time', 'open', 'high', 'low', 'close', 'volume', 
            'close_time', 'quote_asset_volume', 'number_of_trades', 
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ]
        df = pd.DataFrame(all_data, columns=columns)
        
        # 类型转换
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df['close'] = df['close'].astype(float)  # 用于信号计算
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        # 过滤日期范围
        df = df[(df['open_time'] >= start_date) & (df['open_time'] <= end_date)]
        
        # 保存本地CSV
        df.to_csv(csv_file, index=False)
        self.log_message(f"✅ {symbol} 拉取完成: {len(df)} 条数据 (间隔: {self.kline_interval_var.get()})", "info")
        
        return df
    
    def simulate_strategy(self, symbol, data):
        """模拟策略执行"""
        if data.empty:
            return {'win_rate': 0, 'total_return': 0, 'trades': 0}
        
        positions = 0
        entry_price = 0
        trades = []
        balance = 10000  # 初始资金
        
        for i in range(len(data)):
            row = data.iloc[i]
            current_price = row['close']
            
            # 模拟信号（用真实calculate_strategy_signals）
            historical = data['close'].iloc[max(0, i-100):i+1].tolist()  # 最近100点
            if len(historical) < 60:
                continue  # 跳过数据不足，避免警告
            
            signals = self.calculate_strategy_signals(symbol, historical, current_price)
            
            #  修复：模拟 position_info 字典
            simulated_position = {
                'size': positions,
                'entry_price': entry_price if positions != 0 else 0,
                'unrealized_pnl': 0,  # 模拟0
            }
            position_info = self.get_position_info(symbol, current_price)  # 基值
            position_info.update(simulated_position)  # 覆盖模拟大小
            position_info['status'] = '持有多头' if positions > 0 else '持有空头' if positions < 0 else '无持仓'  # 手动设置 'status'
            position_info['is_long'] = positions > 0
            position_info['is_short'] = positions < 0
            position_info['pnl_percent'] = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 and positions != 0 else 0
            
            final_signal = self.determine_final_signal_with_position(signals, position_info, symbol)[0]
            
            # 模拟执行（简化，无杠杆/费用）
            if final_signal == "买入" and positions == 0:
                positions = balance / current_price * 0.1  # 10%仓位
                entry_price = current_price
                trades.append({'type': 'buy', 'price': current_price, 'time': row['open_time']})
            elif final_signal == "卖出" and positions > 0:
                pnl = (current_price - entry_price) / entry_price
                balance += positions * current_price * pnl
                trades.append({'type': 'sell', 'price': current_price, 'pnl': pnl, 'time': row['open_time']})
                positions = 0
            
        # 计算绩效
        wins = len([t for t in trades if t.get('pnl', 0) > 0])
        win_rate = wins / len(trades) if trades else 0
        total_return = (balance - 10000) / 10000
        
        return {'win_rate': win_rate, 'total_return': total_return, 'trades': len(trades), 'balance': balance}


    
    def display_backtest_results(self, results):
        """显示回测结果（日志或新窗口）"""
        self.log_message("回测报告:", "info")
        for token, res in results.items():
            self.log_message(f"  {token}: 胜率 {res['win_rate']:.2%} | 总回报 {res['total_return']:.2%} | 交易数 {res['trades']}", "info")
    
        # 可选：新tkinter窗口显示表格
        result_window = tk.Toplevel(self.root)
        result_window.title("回测结果")
    
        #  修复
        columns = ('Token', 'Win Rate', 'Total Return', 'Trades')
        tree = ttk.Treeview(result_window, columns=columns, show="headings")
    
        # 设置表头
        tree.heading('Token', text='币种')
        tree.heading('Win Rate', text='胜率')
        tree.heading('Total Return', text='总回报')
        tree.heading('Trades', text='交易数')
    
        # 设置列宽（可选）
        tree.column('Token', width=80)
        tree.column('Win Rate', width=100)
        tree.column('Total Return', width=100)
        tree.column('Trades', width=80)
    
        # 插入数据
        for token, res in results.items():
            tree.insert('', 'end', values=(
                token,
                f"{res['win_rate']:.2%}",
                f"{res['total_return']:.2%}",
                res['trades']
            ))
    
        tree.pack(fill=tk.BOTH, expand=True)


    def determine_final_signal_with_position(self, signals, position_info, symbol):
        """根据执行模式和仓位状态确定最终交易信号"""
        execution_mode = self.execution_mode_var.get()
        has_position = position_info['status'] != '无持仓'
        
        active_signals = []
        strategy_details = []
        
        for strategy in ['ma', 'rsi_signal', 'macd_signal', 'bollinger']:
            signal = signals.get(strategy, "持有")
            if "未启用" not in signal and signal != "数据不足":
                active_signals.append(signal)
                strategy_details.append((strategy, signal))
    
        if not active_signals:
            return "持有", "无活跃策略", {'buy_strength': 0, 'sell_strength': 0, 'hold_strength': 1}
    
        signal_strength = self.calculate_signal_strength(strategy_details)
        final_signal = "持有"
        operation_advice = "保持现状"
    
        if execution_mode == "weighted":
            result = self.weighted_decision(
                strategy_details, signal_strength, has_position, position_info, symbol
            )
            if result is not None:
                final_signal, operation_advice = result
            
        elif execution_mode == "strict":
            result = self.strict_decision(
                active_signals, has_position, position_info
            )
            if result is not None:
                final_signal, operation_advice = result
            
        elif execution_mode == "majority":
            result = self.majority_decision(
                active_signals, has_position, position_info
            )
            if result is not None:
                final_signal, operation_advice = result

        return final_signal, operation_advice, signal_strength

    def calculate_signal_strength(self, strategy_details):
        """计算信号强度"""
        # 修复：映射策略键，确保匹配权重
        key_mapping = {
            'rsi_signal': 'rsi',
            'macd_signal': 'macd',
            'ma': 'ma',
            'bollinger': 'bollinger'
        }
        
        buy_score = 0
        sell_score = 0
        hold_score = 0
        
        for strategy, signal in strategy_details:
            mapped_key = key_mapping.get(strategy, strategy)  # 映射
            weight = self.strategy_weights_config.get(mapped_key, 0.25)
            
            if signal == "买入":
                buy_score += weight
            elif signal == "卖出":
                sell_score += weight
            elif signal == "持有":
                hold_score += weight
        
        total = buy_score + sell_score + hold_score
        if total > 0:
            return {
                'buy_strength': buy_score / total,
                'sell_strength': sell_score / total,
                'hold_strength': hold_score / total,
                'buy_score': buy_score,
                'sell_score': sell_score,
                'hold_score': hold_score
            }
        else:
            return {
                'buy_strength': 0,
                'sell_strength': 0,
                'hold_strength': 1,
                'buy_score': 0,
                'sell_score': 0,
                'hold_score': 1
            }

    def weighted_decision(self, strategy_details, signal_strength, has_position, position_info, symbol):
        """权重决策模式"""
        try:
            threshold = float(self.signal_threshold.get())
        except:
            threshold = 0.5
    
        buy_strength = signal_strength['buy_strength']
        sell_strength = signal_strength['sell_strength']
        hold_strength = signal_strength['hold_strength']

        position_size = position_info.get('size', 0)
        is_long = position_size > 0
        is_short = position_size < 0
    
        if has_position:
            if is_long:
                if sell_strength > threshold and buy_strength < 0.2:
                    return "卖出", "强烈建议平多仓"
                elif sell_strength > 0.4 and buy_strength < 0.3:
                    return "持有", "考虑减仓"
                elif buy_strength > threshold:
                    if self.check_single_coin_position_limit(symbol, "买入", position_info):
                        return "持有", "多头仓位已达上限，保持持仓"
                    else:
                        return "买入", "考虑加仓"
                else:
                    return "持有", "保持多头持仓"

            elif is_short:
                if buy_strength > threshold and sell_strength < 0.2:
                    return "买入", "强烈建议平空仓"
                elif buy_strength > 0.4 and sell_strength < 0.3:
                    return "持有", "考虑减空仓"
                elif sell_strength > threshold:
                    if self.check_single_coin_position_limit(symbol, "卖出", position_info):
                        return "持有", "空头仓位已达上限，保持持仓"
                    else:
                        return "卖出", "考虑加空仓"
                else:
                    return "持有", "保持空头持仓"
            else:
                return "持有", "持仓状态异常"
        else:
            #  修复：优先主导方向 >阈值触发 (买 >卖 and 买>阈值 → 买; 卖 >买 and 卖>阈值 → 卖)
            if buy_strength > sell_strength and buy_strength > threshold:
                return "买入", "建议开多仓"
            elif sell_strength > buy_strength and sell_strength > threshold:
                return "卖出", "建议开空仓"
            elif buy_strength > 0.5 and sell_strength < 0.3:
                return "持有", "观望等待更好时机"
            else:
                return "持有", "保持空仓"

    def strict_decision(self, active_signals, has_position, position_info):
        """严格决策模式"""
        unique_signals = set(active_signals)
        
        if len(unique_signals) == 1:
            signal = list(unique_signals)[0]
            if signal == "买入":
                advice = "建议开仓" if not has_position else "建议加仓"
            elif signal == "卖出":
                advice = "建议平仓" if has_position else "保持空仓"
            else:
                advice = "保持现状"
            return signal, advice
        else:
            if has_position:
                return "持有", "策略分歧，保持持仓"
            else:
                return "持有", "策略分歧，保持空仓"

    def majority_decision(self, active_signals, has_position, position_info):
        """多数决策模式"""
        buy_count = active_signals.count("买入")
        sell_count = active_signals.count("卖出")
        hold_count = active_signals.count("持有")
        total = len(active_signals)
        
        if buy_count > total / 2:
            if has_position:
                return "持有", "多数看多，保持持仓"
            else:
                return "买入", "多数看多，建议开仓"
        elif sell_count > total / 2:
            if has_position:
                return "卖出", "多数看空，建议平仓"
            else:
                return "持有", "多数看空，保持空仓"
        else:
            if has_position:
                return "持有", "信号分歧，保持持仓"
            else:
                return "持有", "信号分歧，保持空仓"

    def update_signal_display(self, token, price_data, position_info, signals, final_signal, operation_advice):
        """更新信号显示表格"""
        execution_mode = self.execution_mode_var.get()
        
        signal_colors = {
            "买入": "🟢",
            "卖出": "🔴", 
            "持有": "🟡",
            "未启用": "⚫",
            "数据不足": "⚪"
        }
        
        position_colors = {
            "持有多头": "🟢",
            "持有空头": "🔴",
            "无持仓": "⚪"
        }

        display_price = f"${price_data['price']:.4f}"

        self.signal_tree.insert("", "end", values=(
            token,
            display_price,
            f"{position_colors.get(position_info['status'], '')}{position_info['status']}",
            f"{signal_colors.get(signals.get('ma', '未启用'), '')}{signals.get('ma', '未启用')}",
            f"{signal_colors.get(signals.get('rsi_signal', '未启用'), '')}{signals.get('rsi_signal', '未启用')}",
            f"{signal_colors.get(signals.get('macd_signal', '未启用'), '')}{signals.get('macd_signal', '未启用')}",
            f"{signal_colors.get(signals.get('bollinger', '未启用'), '')}{signals.get('bollinger', '未启用')}",
            execution_mode,
            f"{signal_colors.get(final_signal, '')}{final_signal}",
            operation_advice
        ))

    def check_take_profit_stop_loss(self, position_info):
        """检查单个仓位止盈止损"""
        pnl = position_info['pnl_percent']
        take_profit_pct = float(self.take_profit_pct.get() or 15)
        stop_loss_pct = float(self.stop_loss_pct.get() or 8)
        
        if pnl > take_profit_pct:
            return '止盈'
        elif pnl < -stop_loss_pct:
            return '止损'
        return None

    def get_stable_real_time_price(self, symbol):
        """获取稳定的实时价格"""
        if symbol in self.price_cache:
            cached_data = self.price_cache[symbol]
            if time.time() - cached_data['timestamp'] < 20:
                return cached_data
        
        price_data = self.get_real_time_price(symbol)
        if price_data:
            self.price_cache[symbol] = price_data
        return price_data

    def calculate_strategy_signals(self, symbol, historical_prices, current_price):
        """计算各种策略信号"""
        #  新增：检查历史数据是否充足
        if not historical_prices or len(historical_prices) < 60:
            self.log_message(f" {symbol}: 历史数据不足，无法计算策略信号", "warning")
            return {
                'ma': "数据不足",
                'rsi': 0,
                'rsi_signal': "数据不足",
                'macd': 0,
                'macd_signal': "数据不足",
                'bollinger': "数据不足"
            }

        signals = {}
        
        prices = np.array(historical_prices)
        
        if self.ma_strategy_var.get():
            signals['ma'] = self.ma_strategy_enhanced(prices, current_price)
        else:
            signals['ma'] = "未启用"
        
        if self.rsi_strategy_var.get():
            signals['rsi'] = self.calculate_rsi(prices)
            signals['rsi_signal'] = self.rsi_strategy_enhanced(signals['rsi'])
        else:
            signals['rsi'] = 0
            signals['rsi_signal'] = "未启用"
        
        if self.macd_strategy_var.get():
            macd, signal_line = self.calculate_macd(prices)
            signals['macd'] = macd
            signals['macd_signal'] = self.macd_strategy_enhanced(macd, signal_line)
        else:
            signals['macd'] = 0
            signals['macd_signal'] = "未启用"
        
        if self.bollinger_strategy_var.get():
            bb_upper, bb_lower, bb_middle = self.calculate_bollinger_bands_enhanced(prices)
            signals['bollinger'] = self.bollinger_strategy_enhanced(current_price, bb_upper, bb_lower, bb_middle)
        else:
            signals['bollinger'] = "未启用"
        
        return signals

    def ma_strategy_enhanced(self, prices, current_price):
        """均线策略"""
        if len(prices) < 20:
            return "数据不足"
        
        ma_short = np.mean(prices[-10:])
        ma_long = np.mean(prices[-20:])
        price_vs_short = (current_price - ma_short) / ma_short * 100
        
        if ma_short > ma_long and current_price > ma_short and price_vs_short > 1:
            return "买入"
        elif ma_short < ma_long and current_price < ma_short and price_vs_short < -1:
            return "卖出"
        elif abs(price_vs_short) < 0.5:
            return "持有"
        else:
            return "持有"

    def calculate_rsi(self, prices, period=14):
        """计算RSI"""
        if len(prices) < period + 1:
            return 50
        
        deltas = np.diff(prices)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gains = np.mean(gains[-period:])
        avg_losses = np.mean(losses[-period:])
        
        if avg_losses == 0:
            return 100
        
        rs = avg_gains / avg_losses
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def rsi_strategy_enhanced(self, rsi):
        """RSI策略"""
        if rsi > 75:
            return "卖出"
        elif rsi > 70:
            return "持有"
        elif rsi < 25:
            return "买入"
        elif rsi < 30:
            return "持有"
        elif 45 <= rsi <= 55:
            return "持有"
        else:
            return "持有"

    def compute_ema_series(self, series, period):
        """计算EMA完整序列"""
        series = np.array(series, dtype=float)
        if len(series) < period:
            return np.full_like(series, np.nan)
    
        ema = np.full_like(series, np.nan)
        multiplier = 2 / (period + 1.0)
    
        ema[period-1] = np.mean(series[:period])
    
        for i in range(period, len(series)):
            ema[i] = (series[i] * multiplier) + (ema[i-1] * (1 - multiplier))
    
        return ema

    def calculate_macd(self, prices, fast=12, slow=26, signal=9):
        """计算MACD"""
        if len(prices) < slow + signal:
            return np.nan, np.nan
    
        prices = np.array(prices, dtype=float)
        if np.any(~np.isfinite(prices)):
            return np.nan, np.nan
    
        ema_fast = self.compute_ema_series(prices, fast)
        ema_slow = self.compute_ema_series(prices, slow)
    
        valid_mask = ~np.isnan(ema_fast) & ~np.isnan(ema_slow)
        if not np.any(valid_mask):
            return np.nan, np.nan
    
        macd_series = ema_fast - ema_slow
        signal_series = self.compute_ema_series(macd_series[~np.isnan(macd_series)], signal)
    
        if len(signal_series) > 0 and not np.isnan(signal_series[-1]):
            return macd_series[-1], signal_series[-1]
        else:
            return np.nan, np.nan

    def macd_strategy_enhanced(self, macd, signal):
        """MACD策略"""
        if np.isnan(macd) or np.isnan(signal):
            return "数据不足"
    
        if signal == 0:
            return "持有"
    
        macd_diff = macd - signal
        macd_strength = abs(macd_diff) / (abs(signal) + 1e-6)
    
        if macd > signal and macd_diff > 0 and macd_strength > 0.1:
            return "买入"
        elif macd < signal and macd_diff < 0 and macd_strength > 0.1:
            return "卖出"
        elif abs(macd_diff) < abs(signal) * 0.05:
            return "持有"
        else:
            return "持有"

    def calculate_bollinger_bands_enhanced(self, prices, period=20, std_dev=2):
        """计算布林带"""
        if len(prices) < period:
            return np.mean(prices), np.mean(prices), np.mean(prices)
        
        sma = np.mean(prices[-period:])
        std = np.std(prices[-period:])
        
        upper_band = sma + (std * std_dev)
        lower_band = sma - (std * std_dev)
        
        return upper_band, lower_band, sma

    def bollinger_strategy_enhanced(self, current_price, upper_band, lower_band, middle_band):
        """布林带策略"""
        if current_price > upper_band:
            return "卖出"
        elif current_price < lower_band:
            return "买入"
        elif abs(current_price - middle_band) / middle_band < 0.02:
            return "持有"
        else:
            return "持有"

    def assess_trend_strength(self, symbol):
        """评估趋势强度"""
        try:
            historical_prices = self.get_historical_prices(symbol, periods=50)
            if not historical_prices or len(historical_prices) < 20:
                return 0.5  # 默认中等强度
            
            prices = np.array(historical_prices)
            
            # 计算短期和长期均线
            if len(prices) >= 10:
                ma_short = np.mean(prices[-10:])
            else:
                ma_short = np.mean(prices)
                
            if len(prices) >= 20:
                ma_long = np.mean(prices[-20:])
            else:
                ma_long = np.mean(prices)
            
            # 计算均线角度
            price_trend = (prices[-1] - prices[-5]) / prices[-5] * 100
            
            # 计算RSI趋势
            rsi = self.calculate_rsi(prices)
            rsi_trend = abs(rsi - 50) / 50  # 偏离50的程度
            
            # 综合趋势强度 (0-1)
            ma_strength = 1.0 if (ma_short > ma_long and price_trend > 0) or (ma_short < ma_long and price_trend < 0) else 0.3
            trend_strength = (ma_strength + rsi_trend) / 2
            
            return min(max(trend_strength, 0.1), 1.0)  # 限制在0.1-1.0之间
            
        except Exception as e:
            self.log_message(f" 评估趋势强度出错 {symbol}: {str(e)}", "error")
            return 0.5

    def get_real_time_price(self, symbol):
        """从Hyperliquid获取实时价格"""
        if not self.connection_status:
            return self.get_fallback_price(symbol)  # 直接使用get_fallback_price
        
        try:
            all_mids = self.info.all_mids()
            coin = f"{symbol.upper()}"
            
            if coin in all_mids:
                mark_price = float(all_mids[coin])
                return {
                    'symbol': symbol,
                    'price': mark_price,
                    'timestamp': time.time(),
                    'source': 'Hyperliquid Mark Price'
                }
            
            meta = self.info.meta()
            if 'universe' in meta:
                for asset in meta['universe']:
                    if asset.get('name') == coin:
                        mark_price = float(asset.get('markPx', 0))
                        if mark_price > 0:
                            return {
                                'symbol': symbol,
                                'price': mark_price,
                                'timestamp': time.time(),
                                'source': 'Hyperliquid Universe'
                            }
            
            self.log_message(f"Hyperliquid价格查询失败 {symbol}，使用fallback", "warning")
            return self.get_fallback_price(symbol)  # 直接使用get_fallback_price
            
        except Exception as e:
            self.log_message(f" Hyperliquid价格查询失败 {symbol}: {str(e)}，fallback", "warning")
            return self.get_fallback_price(symbol)  # 直接使用get_fallback_price

    def get_fallback_price(self, symbol):
        """Fallback价格获取 - 完全使用币安API"""
        try:
            time.sleep(0.5)
            
            # 使用币安API获取实时价格
            binance_symbol = f"{symbol.upper()}USDT"
            url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={binance_symbol}"
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                return {
                    'symbol': symbol,
                    'price': float(data['lastPrice']),
                    'change_24h': float(data['priceChangePercent']),
                    'high_24h': float(data['highPrice']),
                    'low_24h': float(data['lowPrice']),
                    'volume': float(data['volume']),
                    'timestamp': time.time(),
                    'source': 'Binance'
                }
            else:
                self.log_message(f" 币安API请求失败 {symbol}: HTTP {response.status_code}", "warning")
                
        except Exception as e:
            self.log_message(f"获取实时价格失败 {symbol}: {str(e)}", "error")
        
        # 最终fallback：使用缓存或基础价格
        if symbol in self.price_cache:
            return self.price_cache[symbol]
        
        # 绝对fallback：基础价格
        base_prices = {
            'ETH': 3500, 'BTC': 110000, 'SOL': 160
        }
        base_price = base_prices.get(symbol.upper(), 100)
        
        price_data = {
            'symbol': symbol,
            'price': base_price,
            'change_24h': 0,
            'timestamp': time.time(),
            'source': 'Base Price'
        }
        
        self.price_cache[symbol] = price_data
        return price_data


    def get_historical_prices(self, symbol, periods=100):
        """从币安API获取历史K线数据"""
        try:
            # 币安API限制，最大1000根K线
            limit = min(periods, 1000)
            binance_symbol = f"{symbol.upper()}USDT"
            url = "https://api.binance.com/api/v3/klines"
    

            interval = self.kline_interval_var.get()       
            params = {
                'symbol': binance_symbol,
                'interval': interval,
                'limit': limit
            }
            
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                kline_data = response.json()
                # 提取收盘价（索引4）
                prices = [float(kline[4]) for kline in kline_data]
                self.log_message(f" {symbol}: 从币安获取{len(prices)}根K线数据", "debug")
                return prices
            else:
                self.log_message(f" 币安API请求失败 {symbol}: HTTP {response.status_code}", "warning")
                return []  # 直接返回空列表
                
        except Exception as e:
            self.log_message(f"获取历史价格失败 {symbol}: {str(e)}", "error")
            return []  # 直接返回空列表


    def reload_coin_config(self):
        """重新加载币种配置"""
        self.coin_config = self.load_coin_config()
        self.log_message("✅ 币种配置已重新加载", "info")
        #  添加：确认 BTC 配置
        trading_config = self.coin_config.get("trading_config", {})
        btc_config = trading_config.get("BTC", {})
        self.log_message(f"重载后 BTC 配置: {btc_config}", "info")

    def near_key_resistance(self, symbol):
        """判断是否接近关键技术位 - 简化实现"""
        try:
            historical_prices = self.get_historical_prices(symbol, periods=50)
            if len(historical_prices) < 20:
                return False
                
            current_price = historical_prices[-1]
            resistance_level = max(historical_prices[-20:])
            
            # 如果当前价格在阻力位的5%范围内
            return current_price >= resistance_level * 0.95
            
        except Exception as e:
            self.log_message(f" 判断阻力位失败 {symbol}: {str(e)}", "error")
            return False

    def is_consolidating(self, symbol):
        """判断是否处于横盘状态"""
        try:
            historical_prices = self.get_historical_prices(symbol, periods=30)
            if len(historical_prices) < 20:
                return False
                
            # 计算波动率
            volatility = np.std(historical_prices[-20:]) / np.mean(historical_prices[-20:])
            
            # 低波动率视为横盘
            return volatility < 0.02
            
        except Exception as e:
            self.log_message(f" 判断横盘状态失败 {symbol}: {str(e)}", "error")
            return False

    def volatility_spike(self, symbol):
        """判断波动率是否突然放大"""
        try:
            historical_prices = self.get_historical_prices(symbol, periods=40)
            if len(historical_prices) < 40:
                return False
                
            # 计算近期和前期波动率
            recent_volatility = np.std(historical_prices[-10:]) / np.mean(historical_prices[-10:])
            previous_volatility = np.std(historical_prices[-20:-10]) / np.mean(historical_prices[-20:-10])
            
            # 如果近期波动率是前期的2倍以上
            return recent_volatility > previous_volatility * 2
            
        except Exception as e:
            self.log_message(f" 判断波动率放大失败 {symbol}: {str(e)}", "error")
            return False

def main():
    root = tk.Tk()
    app = HyperliquidTradingBot(root)
    root.mainloop()

if __name__ == "__main__":
    main()
