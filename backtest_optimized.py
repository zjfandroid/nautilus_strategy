"""
币安 U 本位合约短线策略 - 真实数据回测（优化版）
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
import numpy as np
import talib
import json


class RealDataBacktest:
    """真实数据回测 - 优化版"""
    
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
        self.initial_capital = 0
        self.position_size = 0
    
    def calculate_confidence(self) -> float:
        """计算把握度"""
        if len(self.close_prices) < 30:
            return 0.0
        
        closes = np.array(self.close_prices[-50:])
        lows = np.array(self.low_prices[-50:])
        volumes = np.array(self.volume[-50:])
        
        scores = []
        weights = []
        
        # RSI (30%)
        rsi_14 = talib.RSI(closes, timeperiod=14)[-1]
        rsi_score = 1.0 if rsi_14 < 30 else (0.7 if rsi_14 < 35 else (0.3 if rsi_14 < 40 else 0.0))
        scores.append(rsi_score)
        weights.append(0.30)
        
        # 企稳 (25%)
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
        
        # 成交量 (20%)
        avg_vol = np.mean(volumes[-20:])
        recent_vol = np.mean(volumes[-5:])
        vol_score = 1.0 if recent_vol > avg_vol * 1.2 else (0.5 if recent_vol > avg_vol * 0.8 else 0.0)
        scores.append(vol_score)
        weights.append(0.20)
        
        # 均线 (15%)
        ma20 = talib.SMA(closes, timeperiod=20)[-1]
        ma5 = talib.SMA(closes, timeperiod=5)[-1]
        ma10 = talib.SMA(closes, timeperiod=10)[-1]
        
        ma_score = 1.0 if closes[-1] >= ma20 else (0.6 if closes[-1] >= ma20 * 0.99 else (0.3 if closes[-1] >= ma20 * 0.98 else 0.0))
        scores.append(ma_score)
        weights.append(0.15)
        
        # 趋势 (10%)
        trend_score = 1.0 if ma5 >= ma10 >= ma20 else (0.5 if ma5 >= ma10 else (0.3 if ma5 > ma20 * 0.98 else 0.0))
        scores.append(trend_score)
        weights.append(0.10)
        
        return sum(s * w for s, w in zip(scores, weights))
    
    def run(self, df, initial_capital=10000, position_size=200):
        """运行回测"""
        self.initial_capital = initial_capital
        self.position_size = position_size
        
        capital = initial_capital
        signals = 0
        trades = 0
        
        print(f"开始回测 {self.symbol}...")
        print(f"数据条数：{len(df)}")
        print(f"日期范围：{df['timestamp'].min()} 至 {df['timestamp'].max()}")
        print(f"初始资金：{initial_capital} USDT")
        print(f"每次仓位：{position_size} USDT")
        print(f"最大仓位：{self.max_positions} 次")
        print(f"止盈：{self.take_profit_pct*100}% | 止损：{self.stop_loss_pct*100}%")
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
            
            # 检查持仓止盈止损
            positions_to_close = []
            for j, pos in enumerate(self.positions):
                pnl_pct = (current_price - pos['entry_price']) / pos['entry_price']
                if pnl_pct >= self.take_profit_pct:
                    positions_to_close.append((j, pos, pnl_pct, 'TP'))
                elif pnl_pct <= -self.stop_loss_pct:
                    positions_to_close.append((j, pos, pnl_pct, 'SL'))
            
            if positions_to_close:
                # 倒序平仓避免索引问题
                for idx, pos, pnl_pct, action in sorted(positions_to_close, key=lambda x: x[0], reverse=True):
                    pnl = pos['size'] * pnl_pct
                    capital += pnl + pos['size']
                    self.trades.append({
                        'entry': pos['entry_price'],
                        'exit': current_price,
                        'pnl': pnl,
                        'type': action,
                        'pnl_pct': pnl_pct,
                    })
                    self.positions.pop(idx)
                    trades += 1
                    
                    if trades <= 30 or i > len(df) - 100:
                        print(f"[{i:6d}] {action} @ {current_price:.2f} | 盈亏：{pnl:+.2f} USDT ({pnl_pct*100:+.2f}%) | 现金：{capital:.0f}")
                continue
            
            # 开仓
            if len(self.positions) < self.max_positions and confidence >= self.confidence_threshold:
                if capital >= position_size:
                    self.positions.append({'entry_price': current_price, 'size': position_size})
                    capital -= position_size
                    signals += 1
                    
                    if signals <= 15:
                        print(f"[{i:6d}] OPEN @ {current_price:.2f} | 把握度：{confidence*100:.1f}% | 现金：{capital:.0f}")
        
        # 计算未平仓盈亏
        unrealized_pnl = 0
        if self.positions and len(self.close_prices) > 0:
            final_price = self.close_prices[-1]
            for pos in self.positions:
                unrealized_pnl += pos['size'] * (final_price - pos['entry_price']) / pos['entry_price']
        
        # 统计
        total_pnl = sum(t['pnl'] for t in self.trades)
        win_trades = [t for t in self.trades if t['pnl'] > 0]
        loss_trades = [t for t in self.trades if t['pnl'] <= 0]
        
        # 计算最终资金（现金 + 未实现盈亏 + 仓位本金）
        positions_capital = sum(p['size'] for p in self.positions)
        final_capital = capital + positions_capital + unrealized_pnl
        
        print("\n" + "=" * 70)
        print("回测结果")
        print("=" * 70)
        print(f"总交易次数：{len(self.trades)}")
        print(f"盈利次数：{len(win_trades)}")
        print(f"亏损次数：{len(loss_trades)}")
        if len(self.trades) > 0:
            print(f"胜率：{len(win_trades)/len(self.trades)*100:.2f}%")
            avg_win = np.mean([t['pnl'] for t in win_trades]) if win_trades else 0
            avg_loss = np.mean([t['pnl'] for t in loss_trades]) if loss_trades else 0
            print(f"平均盈利：{avg_win:+.2f} USDT")
            print(f"平均亏损：{avg_loss:+.2f} USDT")
            print(f"盈亏比：{abs(avg_win/avg_loss):.2f}" if avg_loss != 0 else "N/A")
        
        print(f"\n已实现盈亏：{total_pnl:+.2f} USDT")
        print(f"未实现盈亏：{unrealized_pnl:+.2f} USDT ({len(self.positions)} 个未平仓)")
        print(f"总盈亏：{total_pnl + unrealized_pnl:+.2f} USDT")
        print(f"最终资金：{final_capital:.2f} USDT")
        print(f"收益率：{(final_capital - initial_capital) / initial_capital * 100:.2f}%")
        print(f"发现信号：{signals} 次")
        print("=" * 70)
        
        return {
            'total_trades': len(self.trades),
            'win_trades': len(win_trades),
            'loss_trades': len(loss_trades),
            'win_rate': len(win_trades)/len(self.trades)*100 if self.trades else 0,
            'total_pnl': total_pnl,
            'unrealized_pnl': unrealized_pnl,
            'final_capital': final_capital,
            'return_pct': (final_capital - initial_capital) / initial_capital * 100,
            'signals': signals,
        }


async def main():
    """主函数"""
    from data_downloader import BinanceDataDownloader
    
    print("=" * 70)
    print("币安 U 本位合约短线策略 - 真实数据回测（优化版）")
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
    
    # 保存数据
    data_file = downloader.save_to_parquet(df, "BTCUSDT", "1m")
    
    # 运行回测 - 测试不同参数组合
    print("\n" + "=" * 70)
    print("测试 1: 原始参数 (止盈 1%, 止损 2%, 阈值 60%)")
    print("=" * 70)
    backtest1 = RealDataBacktest(symbol="BTCUSDT")
    backtest1.confidence_threshold = 0.60
    backtest1.take_profit_pct = 0.01
    backtest1.stop_loss_pct = 0.02
    result1 = backtest1.run(df, initial_capital=10000, position_size=200)
    
    print("\n" + "=" * 70)
    print("测试 2: 平衡参数 (止盈 1.5%, 止损 1.5%, 阈值 65%)")
    print("=" * 70)
    backtest2 = RealDataBacktest(symbol="BTCUSDT")
    backtest2.confidence_threshold = 0.65
    backtest2.take_profit_pct = 0.015
    backtest2.stop_loss_pct = 0.015
    result2 = backtest2.run(df, initial_capital=10000, position_size=200)
    
    print("\n" + "=" * 70)
    print("测试 3: 高阈值参数 (止盈 1.5%, 止损 1%, 阈值 70%)")
    print("=" * 70)
    backtest3 = RealDataBacktest(symbol="BTCUSDT")
    backtest3.confidence_threshold = 0.70
    backtest3.take_profit_pct = 0.015
    backtest3.stop_loss_pct = 0.01
    result3 = backtest3.run(df, initial_capital=10000, position_size=200)
    
    # 对比结果
    print("\n" + "=" * 70)
    print("参数对比")
    print("=" * 70)
    print(f"{'参数':<30} {'测试 1':<15} {'测试 2':<15} {'测试 3':<15}")
    print(f"{'止盈/止损':<30} {'1%/2%':<15} {'1.5%/1.5%':<15} {'1.5%/1%':<15}")
    print(f"{'把握度阈值':<30} {'60%':<15} {'65%':<15} {'70%':<15}")
    print(f"{'交易次数':<30} {result1['total_trades']:<15} {result2['total_trades']:<15} {result3['total_trades']:<15}")
    print(f"{'胜率':<30} {result1['win_rate']:.2f}%{'':<10} {result2['win_rate']:.2f}%{'':<10} {result3['win_rate']:.2f}%")
    print(f"{'收益率':<30} {result1['return_pct']:.2f}%{'':<11} {result2['return_pct']:.2f}%{'':<11} {result3['return_pct']:.2f}%")
    print("=" * 70)
    
    # 保存结果
    results = {
        'test1_original': result1,
        'test2_balanced': result2,
        'test3_conservative': result3,
        'timestamp': datetime.now().isoformat(),
    }
    
    results_file = "results/backtest_comparison.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n结果已保存至：{results_file}")


if __name__ == "__main__":
    asyncio.run(main())
