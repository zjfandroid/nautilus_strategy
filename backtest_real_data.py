"""
真实数据回测脚本
下载币安真实数据并运行策略回测
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import numpy as np
import talib


class RealDataBacktest:
    """真实数据回测"""
    
    def __init__(self, symbol="BTCUSDT"):
        self.symbol = symbol
        self.close_prices = []
        self.high_prices = []
        self.low_prices = []
        self.volume = []
        
        self.max_positions = 5
        self.take_profit_pct = 0.01
        self.stop_loss_pct = 0.02
        self.confidence_threshold = 0.95
        
        self.positions = []
        self.trades = []
    
    def calculate_confidence(self) -> float:
        """计算把握度"""
        if len(self.close_prices) < 30:
            return 0.0
        
        closes = np.array(self.close_prices[-50:])
        lows = np.array(self.low_prices[-50:])
        volumes = np.array(self.volume[-50:])
        
        scores = []
        weights = []
        
        # RSI
        rsi_14 = talib.RSI(closes, timeperiod=14)[-1]
        rsi_score = 1.0 if rsi_14 < 30 else (0.7 if rsi_14 < 35 else (0.3 if rsi_14 < 40 else 0.0))
        scores.append(rsi_score)
        weights.append(0.30)
        
        # 企稳
        recent_lows = lows[-5:]
        prev_lows = lows[-10:-5]
        stab_score = 0.0
        if len(recent_lows) == 5 and len(prev_lows) == 5:
            if min(recent_lows) >= min(prev_lows):
                stab_score = 1.0
            elif min(recent_lows) >= min(prev_lows) * 0.995:
                stab_score = 0.5
        scores.append(stab_score)
        weights.append(0.25)
        
        # 成交量
        avg_vol = np.mean(volumes[-20:])
        recent_vol = np.mean(volumes[-5:])
        vol_score = 1.0 if recent_vol > avg_vol * 1.2 else (0.5 if recent_vol > avg_vol * 0.8 else 0.0)
        scores.append(vol_score)
        weights.append(0.20)
        
        # 均线
        ma20 = talib.SMA(closes, timeperiod=20)[-1]
        ma5 = talib.SMA(closes, timeperiod=5)[-1]
        ma10 = talib.SMA(closes, timeperiod=10)[-1]
        
        ma_score = 1.0 if closes[-1] >= ma20 else (0.6 if closes[-1] >= ma20 * 0.99 else (0.3 if closes[-1] >= ma20 * 0.98 else 0.0))
        scores.append(ma_score)
        weights.append(0.15)
        
        trend_score = 1.0 if ma5 >= ma10 >= ma20 else (0.5 if ma5 >= ma10 else (0.3 if ma5 > ma20 * 0.98 else 0.0))
        scores.append(trend_score)
        weights.append(0.10)
        
        return sum(s * w for s, w in zip(scores, weights))
    
    def run(self, df, initial_capital=10000, position_size=200):
        """运行回测"""
        capital = initial_capital
        signals = 0
        trades = 0
        
        print(f"开始回测 {self.symbol}...")
        print(f"数据条数：{len(df)}")
        print(f"日期范围：{df['timestamp'].min()} 至 {df['timestamp'].max()}")
        print(f"初始资金：{initial_capital} USDT")
        print(f"每次仓位：{position_size} USDT")
        print(f"把握度阈值：{self.confidence_threshold*100}%")
        print()
        
        for i, row in df.iterrows():
            self.close_prices.append(row['close'])
            self.high_prices.append(row['high'])
            self.low_prices.append(row['low'])
            self.volume.append(row['volume'])
            
            if len(self.close_prices) < 30:
                continue
            
            confidence = self.calculate_confidence()
            current_price = row['close']
            
            # 检查持仓
            positions_to_close = []
            for j, pos in enumerate(self.positions):
                pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
                if pnl_pct >= self.take_profit_pct:
                    positions_to_close.append((j, pos, pnl_pct, 'TP'))
                elif pnl_pct <= -self.stop_loss_pct:
                    positions_to_close.append((j, pos, pnl_pct, 'SL'))
            
            if positions_to_close:
                # 按索引倒序平仓，避免索引变化问题
                for idx, pos, pnl_pct, action in sorted(positions_to_close, key=lambda x: x[0], reverse=True):
                    pnl = pos['size'] * pnl_pct
                    capital += pnl + pos['size']
                    self.trades.append({'entry': pos['entry_price'], 'exit': current_price, 'pnl': pnl, 'type': action})
                    self.positions.pop(idx)
                    trades += 1
                    
                    if trades <= 20 or trades > len(df) - 10:
                        print(f"[{i:6d}] {action} @ {current_price:.2f} | 盈亏：{pnl:+.2f} USDT | 现金：{capital:.0f}")
                continue
            
            # 开仓
            if len(self.positions) < self.max_positions and confidence >= self.confidence_threshold:
                if capital >= position_size:
                    self.positions.append({'entry_price': current_price, 'size': position_size})
                    capital -= position_size
                    signals += 1
                    
                    if signals <= 10:
                        print(f"[{i:6d}] OPEN @ {current_price:.2f} | 把握度：{confidence*100:.1f}% | 现金：{capital:.0f}")
        
        # 统计
        total_pnl = sum(t['pnl'] for t in self.trades)
        win_trades = len([t for t in self.trades if t['pnl'] > 0])
        loss_trades = len([t for t in self.trades if t['pnl'] <= 0])
        
        print("\n" + "=" * 70)
        print("回测结果")
        print("=" * 70)
        print(f"总交易次数：{len(self.trades)}")
        print(f"盈利次数：{win_trades}")
        print(f"亏损次数：{loss_trades}")
        if len(self.trades) > 0:
            print(f"胜率：{win_trades/len(self.trades)*100:.2f}%")
        print(f"总盈亏：{total_pnl:+.2f} USDT")
        print(f"最终资金：{capital + total_pnl:.2f} USDT")
        print(f"收益率：{(capital + total_pnl - initial_capital) / initial_capital * 100:.2f}%")
        print(f"发现信号：{signals} 次")
        print("=" * 70)
        
        return {
            'total_trades': len(self.trades),
            'win_rate': win_trades/len(self.trades)*100 if self.trades else 0,
            'total_pnl': total_pnl,
            'return_pct': (capital + total_pnl - initial_capital) / initial_capital * 100,
        }


async def main():
    """主函数"""
    from data_downloader import BinanceDataDownloader
    
    print("=" * 70)
    print("币安 U 本位合约短线策略 - 真实数据回测")
    print("=" * 70)
    
    # 下载数据
    downloader = BinanceDataDownloader()
    end = datetime.now()
    start = end - timedelta(days=30)
    
    print(f"\n下载 {start.date()} 至 {end.date()} 数据...")
    df = await downloader.download_klines(
        symbol="BTCUSDT",
        interval="1m",
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
    )
    
    if len(df) == 0:
        print("数据下载失败")
        return
    
    # 运行回测
    backtest = RealDataBacktest(symbol="BTCUSDT")
    backtest.confidence_threshold = 0.60  # 测试阈值
    backtest.take_profit_pct = 0.015      # 提高止盈到 1.5%
    backtest.stop_loss_pct = 0.015        # 降低止损到 1.5%
    results = backtest.run(df, initial_capital=10000, position_size=200)
    
    # 保存结果
    import json
    results_file = "results/backtest_results.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\n结果已保存至：{results_file}")


if __name__ == "__main__":
    asyncio.run(main())
