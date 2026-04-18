"""
币安 U 本位合约短线撸短策略 - 完整版
继承 Nautilus Trader Strategy 基类，支持回测和实盘

策略核心：
1. 最高可分 5 次投入
2. 每次赚到 1% 就止盈
3. 95% 把握度：下跌企稳后做反弹，不接飞刀不追涨
"""

from decimal import Decimal
from typing import Optional

import numpy as np
import talib

from nautilus_trader.core.datetime import dt_to_unix_nanos
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide
from nautilus_trader.model.events import OrderFilled
from nautilus_trader.model.identifiers import InstrumentId, OrderId, PositionId, StrategyId, TraderId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.model.orders import MarketOrder, LimitOrder
from nautilus_trader.model.position import Position
from nautilus_trader.live.config import TradingStrategyConfig
from nautilus_trader.backtest.config import BacktestStrategyConfig

from nautilus_trader.strategy import Strategy


class BinanceScalpingStrategyConfig(BacktestStrategyConfig):
    """策略配置"""
    instrument_id: str
    symbol: str
    base_position_size: Decimal = Decimal("1000")  # 总仓位 (USDT)
    max_positions: int = 5  # 最多 5 次投入
    take_profit_pct: Decimal = Decimal("0.01")  # 1% 止盈
    stop_loss_pct: Decimal = Decimal("0.02")  # 2% 止损
    confidence_threshold: float = 0.95  # 95% 把握度
    bar_type: str = "1-MINUTE"  # K 线周期


class BinanceScalpingStrategy(Strategy):
    """
    币安 U 本位合约短线撸短策略
    
    核心逻辑：
    1. 使用多个技术指标综合判断市场状态
    2. 只在下跌企稳后做反弹（RSI 超卖 + 价格企稳信号）
    3. 不接下跌飞刀（下跌趋势中不买入）
    4. 不追涨（大幅上涨后不买入）
    5. 分 5 次建仓，每次 1% 止盈
    """
    
    def __init__(self, config: BinanceScalpingStrategyConfig):
        super().__init__(config)
        
        self.config = config
        self.instrument_id = InstrumentId.from_str(config.instrument_id)
        self.instrument: Optional[Instrument] = None
        
        # 仓位管理
        self.positions_open = 0
        self.total_invested = Decimal("0")
        self.position_entries = []  # 记录每次建仓的价格和数量
        
        # 技术指标数据
        self.close_prices = []
        self.high_prices = []
        self.low_prices = []
        self.volume = []
        
        # 策略状态
        self.last_signal_confidence = 0.0
        self.trade_count = 0
        self.win_count = 0
        self.loss_count = 0
        self.total_pnl = Decimal("0")
    
    def on_start(self):
        """策略启动"""
        self.log.info(f"策略启动：{self.config.symbol}")
        self.log.info(f"最大仓位数：{self.config.max_positions}")
        self.log.info(f"止盈比例：{self.config.take_profit_pct * 100}%")
        self.log.info(f"止损比例：{self.config.stop_loss_pct * 100}%")
        self.log.info(f"把握度阈值：{self.config.confidence_threshold * 100}%")
        
        # 订阅 K 线数据
        bar_type = BarType.from_str(f"{self.config.symbol}-PERP.BINANCE.{self.config.bar_type}")
        self.subscribe_bars(bar_type)
        
        self.log.info(f"已订阅 K 线：{bar_type}")
    
    def on_stop(self):
        """策略停止"""
        self.log.info(f"策略停止")
        self.log.info(f"总交易次数：{self.trade_count}")
        self.log.info(f"盈利次数：{self.win_count}")
        self.log.info(f"亏损次数：{self.loss_count}")
        self.log.info(f"总盈亏：{self.total_pnl} USDT")
        
        if self.trade_count > 0:
            win_rate = self.win_count / self.trade_count * 100
            self.log.info(f"胜率：{win_rate:.2f}%")
    
    def on_instrument(self, instrument: Instrument):
        """获取仪器信息"""
        self.instrument = instrument
        self.log.info(f"仪器信息：{instrument}")
    
    def on_bar(self, bar: Bar):
        """处理 K 线数据 - 核心策略逻辑"""
        # 更新价格数据
        self.close_prices.append(float(bar.close.as_double()))
        self.high_prices.append(float(bar.high.as_double()))
        self.low_prices.append(float(bar.low.as_double()))
        self.volume.append(float(bar.volume.as_double()))
        
        # 保持数据长度在合理范围
        max_history = 100
        if len(self.close_prices) > max_history:
            self.close_prices = self.close_prices[-max_history:]
            self.high_prices = self.high_prices[-max_history:]
            self.low_prices = self.low_prices[-max_history:]
            self.volume = self.volume[-max_history:]
        
        # 至少需要 30 根 K 线才能计算指标
        if len(self.close_prices) < 30:
            return
        
        # 计算把握度
        confidence = self.calculate_confidence()
        self.last_signal_confidence = confidence
        
        # 如果有持仓，检查止盈止损
        if self.positions_open > 0:
            self.check_exit_conditions(bar)
            return
        
        # 开仓逻辑：只在高把握度时入场
        if confidence >= self.config.confidence_threshold:
            self.log.info(f"[SIGNAL] 把握度 {confidence*100:.1f}% >= {self.config.confidence_threshold*100}%，准备开仓")
            self.open_position(bar)
    
    def calculate_confidence(self) -> float:
        """
        计算入场信号把握度 (0-1)
        
        综合多个指标：
        1. RSI 超卖 (权重 30%) - 确保在低位
        2. 价格企稳信号 (权重 25%) - 不再创新低
        3. 成交量确认 (权重 20%) - 放量反弹
        4. 均线支撑 (权重 15%) - 价格在均线附近
        5. 不处于下跌趋势 (权重 10%) - 均线多头排列
        """
        closes = np.array(self.close_prices[-50:])
        highs = np.array(self.high_prices[-50:])
        lows = np.array(self.low_prices[-50:])
        volumes = np.array(self.volume[-50:])
        
        if len(closes) < 30:
            return 0.0
        
        scores = []
        weights = []
        
        # 1. RSI 超卖信号 (30%)
        rsi_14 = talib.RSI(closes, timeperiod=14)[-1]
        rsi_score = 0.0
        if rsi_14 < 30:  # 超卖
            rsi_score = 1.0
        elif rsi_14 < 35:
            rsi_score = 0.7
        elif rsi_14 < 40:
            rsi_score = 0.3
        scores.append(rsi_score)
        weights.append(0.30)
        
        # 2. 价格企稳信号 (25%)
        recent_lows = lows[-5:]
        prev_lows = lows[-10:-5]
        stabilization_score = 0.0
        if len(recent_lows) == 5 and len(prev_lows) == 5:
            if min(recent_lows) >= min(prev_lows):  # 不再创新低
                stabilization_score = 1.0
            elif min(recent_lows) >= min(prev_lows) * 0.995:  # 接近企稳
                stabilization_score = 0.5
        scores.append(stabilization_score)
        weights.append(0.25)
        
        # 3. 成交量确认 (20%)
        avg_vol_20 = np.mean(volumes[-20:])
        recent_vol = np.mean(volumes[-5:])
        vol_score = 0.0
        if recent_vol > avg_vol_20 * 1.2:  # 放量
            vol_score = 1.0
        elif recent_vol > avg_vol_20 * 0.8:  # 正常
            vol_score = 0.5
        scores.append(vol_score)
        weights.append(0.20)
        
        # 4. 均线支撑 (15%)
        ma20 = talib.SMA(closes, timeperiod=20)[-1]
        ma_score = 0.0
        current_price = closes[-1]
        if current_price >= ma20:
            ma_score = 1.0
        elif current_price >= ma20 * 0.99:
            ma_score = 0.6
        elif current_price >= ma20 * 0.98:
            ma_score = 0.3
        scores.append(ma_score)
        weights.append(0.15)
        
        # 5. 不处于明显下跌趋势 (10%)
        ma5 = talib.SMA(closes, timeperiod=5)[-1]
        ma10 = talib.SMA(closes, timeperiod=10)[-1]
        trend_score = 0.0
        if ma5 >= ma10 >= ma20:
            trend_score = 1.0
        elif ma5 >= ma10:
            trend_score = 0.5
        elif ma5 > ma20 * 0.98:
            trend_score = 0.3
        scores.append(trend_score)
        weights.append(0.10)
        
        # 加权计算总分
        confidence = sum(s * w for s, w in zip(scores, weights))
        return confidence
    
    def open_position(self, bar: Bar):
        """开仓逻辑"""
        if self.positions_open >= self.config.max_positions:
            self.log.warning(f"已达到最大仓位数 {self.config.max_positions}，无法开仓")
            return
        
        if self.instrument is None:
            self.log.error("仪器信息未加载，无法开仓")
            return
        
        # 计算仓位大小（等分 5 次）
        position_size_usdt = self.config.base_position_size / self.config.max_positions
        
        # 计算合约数量
        price = float(bar.close.as_double())
        quantity = Decimal(str(position_size_usdt / price))
        
        # 调整为合约规定的精度
        quantity = self.instrument.make_qty(quantity)
        
        if quantity <= 0:
            self.log.error(f"计算出的仓位数量为 0 或负数")
            return
        
        # 提交买单
        order = MarketOrder(
            trader_id=TraderId("TRADER-001"),
            strategy_id=self.strategy_id,
            instrument_id=self.instrument_id,
            side=OrderSide.BUY,
            quantity=quantity,
            ts_event=bar.ts_event,
        )
        
        self.submit_order(order)
        
        # 记录建仓
        self.position_entries.append({
            'price': price,
            'size': position_size_usdt,
            'quantity': float(quantity),
            'time': bar.ts_event,
            'order_id': order.id,
        })
        self.positions_open += 1
        self.total_invested += position_size_usdt
        
        self.log.info(
            f"[OPEN] 第{self.positions_open}次建仓 @ {price}, "
            f"数量：{quantity}, 仓位：{position_size_usdt} USDT"
        )
    
    def check_exit_conditions(self, bar: Bar):
        """检查止盈止损条件"""
        current_price = float(bar.close.as_double())
        
        # 检查每个仓位的止盈止损
        positions_to_close = []
        
        for i, entry in enumerate(self.position_entries):
            entry_price = entry['price']
            
            # 计算盈亏比例
            pnl_pct = (current_price - entry_price) / entry_price
            
            # 止盈检查 (1%)
            if pnl_pct >= float(self.config.take_profit_pct):
                self.log.info(
                    f"[TAKE PROFIT] 第{i+1}仓位止盈 @ {current_price}, "
                    f"盈利：{pnl_pct*100:.2f}%"
                )
                positions_to_close.append((i, entry, pnl_pct))
                continue
            
            # 止损检查 (2%)
            if pnl_pct <= -float(self.config.stop_loss_pct):
                self.log.info(
                    f"[STOP LOSS] 第{i+1}仓位止损 @ {current_price}, "
                    f"亏损：{pnl_pct*100:.2f}%"
                )
                positions_to_close.append((i, entry, pnl_pct))
        
        # 执行平仓
        for idx, entry, pnl_pct in positions_to_close:
            self.close_position(idx, entry, bar, pnl_pct)
    
    def close_position(self, position_index: int, entry: dict, bar: Bar, pnl_pct: float):
        """平仓"""
        if self.instrument is None:
            return
        
        quantity = Decimal(str(entry['quantity']))
        quantity = self.instrument.make_qty(quantity)
        
        # 提交卖单
        order = MarketOrder(
            trader_id=TraderId("TRADER-001"),
            strategy_id=self.strategy_id,
            instrument_id=self.instrument_id,
            side=OrderSide.SELL,
            quantity=quantity,
            ts_event=bar.ts_event,
        )
        
        self.submit_order(order)
        
        # 计算盈亏
        pnl_usdt = entry['size'] * Decimal(str(pnl_pct))
        self.total_pnl += pnl_usdt
        
        # 更新统计
        self.trade_count += 1
        if pnl_pct > 0:
            self.win_count += 1
        else:
            self.loss_count += 1
        
        # 移除仓位记录
        self.position_entries.pop(position_index)
        self.positions_open -= 1
        
        self.log.info(
            f"[CLOSE] 平仓第{position_index+1}仓位 @ {bar.close}, "
            f"盈亏：{pnl_usdt:.2f} USDT ({pnl_pct*100:.2f}%)"
        )
    
    def on_order_filled(self, filled: OrderFilled):
        """订单成交回调"""
        self.log.info(f"订单成交：{filled}")
