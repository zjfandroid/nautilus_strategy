"""
策略逻辑测试 - 验证把握度计算和信号生成
不依赖完整回测引擎，快速验证策略核心逻辑
"""

import numpy as np
import talib
from datetime import datetime, timedelta
from decimal import Decimal


class StrategyLogicTest:
    """策略逻辑测试类"""
    
    def __init__(self):
        self.close_prices = []
        self.high_prices = []
        self.low_prices = []
        self.volume = []
        
        self.max_positions = 5
        self.take_profit_pct = 0.01
        self.stop_loss_pct = 0.02
        self.confidence_threshold = 0.60  # 测试时降低阈值
        
        self.positions = []
        self.trades = []
    
    def add_bar(self, open_, high, low, close, volume):
        """添加 K 线数据"""
        self.close_prices.append(close)
        self.high_prices.append(high)
        self.low_prices.append(low)
        self.volume.append(volume)
        
        # 保持数据长度
        if len(self.close_prices) > 100:
            self.close_prices = self.close_prices[-100:]
            self.high_prices = self.high_prices[-100:]
            self.low_prices = self.low_prices[-100:]
            self.volume = self.volume[-100:]
    
    def calculate_confidence(self) -> float:
        """计算入场信号把握度"""
        if len(self.close_prices) < 30:
            return 0.0
        
        closes = np.array(self.close_prices[-50:])
        highs = np.array(self.high_prices[-50:])
        lows = np.array(self.low_prices[-50:])
        volumes = np.array(self.volume[-50:])
        
        scores = []
        weights = []
        
        # 1. RSI 超卖 (30%)
        rsi_14 = talib.RSI(closes, timeperiod=14)[-1]
        rsi_score = 0.0
        if rsi_14 < 30:
            rsi_score = 1.0
        elif rsi_14 < 35:
            rsi_score = 0.7
        elif rsi_14 < 40:
            rsi_score = 0.3
        scores.append(rsi_score)
        weights.append(0.30)
        
        # 2. 价格企稳 (25%)
        recent_lows = lows[-5:]
        prev_lows = lows[-10:-5]
        stabilization_score = 0.0
        if len(recent_lows) == 5 and len(prev_lows) == 5:
            if min(recent_lows) >= min(prev_lows):
                stabilization_score = 1.0
            elif min(recent_lows) >= min(prev_lows) * 0.995:
                stabilization_score = 0.5
        scores.append(stabilization_score)
        weights.append(0.25)
        
        # 3. 成交量 (20%)
        avg_vol_20 = np.mean(volumes[-20:])
        recent_vol = np.mean(volumes[-5:])
        vol_score = 0.0
        if recent_vol > avg_vol_20 * 1.2:
            vol_score = 1.0
        elif recent_vol > avg_vol_20 * 0.8:
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
        
        # 5. 趋势判断 (10%)
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
        
        confidence = sum(s * w for s, w in zip(scores, weights))
        return confidence
    
    def check_signals(self, current_price):
        """检查信号"""
        if len(self.close_prices) < 30:
            return None
        
        confidence = self.calculate_confidence()
        
        # 检查持仓止盈止损
        for i, pos in enumerate(self.positions):
            pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
            
            if pnl_pct >= self.take_profit_pct:
                return {
                    'type': 'TAKE_PROFIT',
                    'position_idx': i,
                    'pnl_pct': pnl_pct,
                    'confidence': confidence,
                }
            
            if pnl_pct <= -self.stop_loss_pct:
                return {
                    'type': 'STOP_LOSS',
                    'position_idx': i,
                    'pnl_pct': pnl_pct,
                    'confidence': confidence,
                }
        
        # 检查开仓信号
        if len(self.positions) < self.max_positions and confidence >= self.confidence_threshold:
            return {
                'type': 'OPEN',
                'confidence': confidence,
            }
        
        return None
    
    def open_position(self, price, size):
        """开仓"""
        self.positions.append({
            'entry_price': price,
            'size': size,
        })
    
    def close_position(self, idx, price):
        """平仓"""
        pos = self.positions.pop(idx)
        pnl = (price - pos['entry_price']) / pos['entry_price'] * pos['size']
        self.trades.append({
            'entry_price': pos['entry_price'],
            'exit_price': price,
            'pnl': pnl,
        })
        return pnl


def generate_test_data(days=30, base_price=50000, volatility=0.02):
    """生成模拟 K 线数据"""
    import random
    
    bars = []
    price = base_price
    minutes = days * 24 * 60
    
    print(f"生成 {minutes} 条模拟 K 线数据...")
    
    for i in range(minutes):
        # 随机游走 + 趋势
        trend = np.sin(i / 1000) * 0.001  # 长期趋势
        noise = random.gauss(0, volatility)
        
        change = 1 + trend + noise
        open_ = price
        close = price * change
        high = max(open_, close) * (1 + abs(random.gauss(0, 0.005)))
        low = min(open_, close) * (1 - abs(random.gauss(0, 0.005)))
        volume = random.uniform(100, 1000)
        
        bars.append((open_, high, low, close, volume))
        price = close
        
        if (i + 1) % 10000 == 0:
            print(f"  已生成 {i+1}/{minutes} 条")
    
    return bars


def run_test():
    """运行策略测试"""
    print("=" * 70)
    print("策略逻辑测试 - 模拟回测")
    print("=" * 70)
    
    # 生成测试数据
    bars = generate_test_data(days=30, base_price=50000, volatility=0.015)
    
    # 初始化策略
    strategy = StrategyLogicTest()
    
    # 运行回测
    initial_capital = 10000
    position_size = 200  # 每次 200 USDT
    capital = initial_capital
    
    print(f"\n初始资金：{initial_capital} USDT")
    print(f"每次仓位：{position_size} USDT")
    print(f"最大仓位数：{strategy.max_positions}")
    print(f"\n开始回测...\n")
    
    signals_found = 0
    trades_executed = 0
    
    for i, (open_, high, low, close, volume) in enumerate(bars):
        strategy.add_bar(open_, high, low, close, volume)
        
        signal = strategy.check_signals(close)
        
        if signal:
            signals_found += 1
            
            if signal['type'] == 'OPEN':
                if capital >= position_size:
                    strategy.open_position(close, position_size)
                    capital -= position_size
                    print(f"[{i:6d}] OPEN  @ {close:.2f} | 把握度：{signal['confidence']*100:.1f}% | 现金：{capital:.0f}")
            
            elif signal['type'] in ['TAKE_PROFIT', 'STOP_LOSS']:
                pnl = strategy.close_position(signal['position_idx'], close)
                capital += pnl + position_size
                trades_executed += 1
                action = "TP" if signal['type'] == 'TAKE_PROFIT' else "SL"
                print(f"[{i:6d}] {action}   @ {close:.2f} | 盈亏：{pnl:+.2f} USDT | 现金：{capital:.0f}")
        
        # 显示前几个高把握度信号
        if i < 1000 and signal and signal['type'] == 'OPEN' and signal['confidence'] > 0.5:
            print(f"  -> 调试：把握度={signal['confidence']*100:.1f}%")
        
        # 进度显示
        if (i + 1) % 50000 == 0:
            print(f"  处理进度：{i+1}/{len(bars)} ({(i+1)/len(bars)*100:.1f}%)")
    
    # 统计结果
    print("\n" + "=" * 70)
    print("回测结果")
    print("=" * 70)
    
    total_pnl = sum(t['pnl'] for t in strategy.trades)
    win_trades = [t for t in strategy.trades if t['pnl'] > 0]
    loss_trades = [t for t in strategy.trades if t['pnl'] <= 0]
    
    print(f"总交易次数：{len(strategy.trades)}")
    print(f"盈利次数：{len(win_trades)}")
    print(f"亏损次数：{len(loss_trades)}")
    
    if len(strategy.trades) > 0:
        win_rate = len(win_trades) / len(strategy.trades) * 100
        print(f"胜率：{win_rate:.2f}%")
    
    print(f"\n总盈亏：{total_pnl:+.2f} USDT")
    print(f"最终资金：{capital + total_pnl:.2f} USDT")
    print(f"收益率：{(capital + total_pnl - initial_capital) / initial_capital * 100:.2f}%")
    
    print("\n" + "=" * 70)
    print(f"发现信号：{signals_found} 次")
    print(f"执行交易：{trades_executed} 次")
    print("=" * 70)
    
    return {
        'total_trades': len(strategy.trades),
        'win_trades': len(win_trades),
        'loss_trades': len(loss_trades),
        'total_pnl': total_pnl,
        'final_capital': capital + total_pnl,
        'return_pct': (capital + total_pnl - initial_capital) / initial_capital * 100,
    }


if __name__ == "__main__":
    run_test()
