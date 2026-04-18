"""
币安 U 本位合约短线策略 - 完整回测脚本
支持下载数据、运行回测、输出报告
"""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from nautilus_trader.backtest.config import BacktestRunConfig, BacktestEngineConfig
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.config import LoggingConfig
from nautilus_trader.model.currencies import USDT
from nautilus_trader.model.data import BarType
from nautilus_trader.model.enums import AccountType, AssetType, BookType, Venue
from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue, TraderId, StrategyId
from nautilus_trader.model.instruments import CryptoPerpetual

from strategies.binance_scalping_strategy import BinanceScalpingStrategy, BinanceScalpingStrategyConfig


def create_binance_perpetual(symbol: str = "BTCUSDT") -> CryptoPerpetual:
    """
    创建币安 U 本位永续合约仪器
    
    Args:
        symbol: 交易对符号，如 BTCUSDT, ETHUSDT 等
    """
    instrument_id = InstrumentId(
        symbol=Symbol(symbol),
        venue=Venue("BINANCE"),
    )
    
    # 币安 U 本位永续合约标准配置
    instrument = CryptoPerpetual(
        id=instrument_id,
        raw_symbol=Symbol(symbol),
        base_currency=USDT,
        quote_currency=USDT,
        settlement_currency=USDT,
        asset_type=AssetType.CRYPTO,
        is_inverse=False,
        lot_size=Decimal("0.001"),
        tick_size=Decimal("0.1"),
        max_quantity=Decimal("1000"),
        min_quantity=Decimal("0.001"),
        max_notional=Decimal("1000000"),
        min_notional=Decimal("5"),
        margin_init=Decimal("0.05"),
        margin_maint=Decimal("0.025"),
        maker_fee=Decimal("0.0002"),
        taker_fee=Decimal("0.0004"),
        ts_event=0,
        ts_init=0,
    )
    
    return instrument


async def run_backtest(
    symbol: str = "BTCUSDT",
    start_date: str = None,
    end_date: str = None,
    initial_capital: Decimal = Decimal("10000"),
    base_position_size: Decimal = Decimal("1000"),
    data_file: str = None,
):
    """
    运行回测
    
    Args:
        symbol: 交易对
        start_date: 开始日期 (YYYY-MM-DD), 默认 30 天前
        end_date: 结束日期 (YYYY-MM-DD), 默认今天
        initial_capital: 初始资金 (USDT)
        base_position_size: 总仓位大小 (USDT)
        data_file: 历史数据文件路径 (parquet 或 csv)
    """
    
    # 计算日期范围
    if end_date is None:
        end_dt = datetime.now()
    else:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    if start_date is None:
        start_dt = end_dt - timedelta(days=30)
    else:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    
    print("=" * 70)
    print("币安 U 本位合约短线撸短策略 - 回测报告")
    print("=" * 70)
    print(f"交易对：{symbol}")
    print(f"回测区间：{start_dt.strftime('%Y-%m-%d')} 至 {end_dt.strftime('%Y-%m-%d')}")
    print(f"初始资金：{initial_capital} USDT")
    print(f"总仓位：{base_position_size} USDT (分{5}次投入，每次{base_position_size/5} USDT)")
    print(f"止盈比例：1%")
    print(f"止损比例：2%")
    print(f"信号把握度阈值：95%")
    print("=" * 70)
    
    # 创建回测引擎配置
    engine_config = BacktestEngineConfig(
        trader_id=TraderId("BACKTEST-001"),
        logging=LoggingConfig(log_level="INFO"),
    )
    
    # 创建回测引擎
    engine = BacktestEngine(config=engine_config)
    
    # 添加账户
    engine.add_account(
        account_type=AccountType.MARGIN,
        currency=USDT,
        balance=initial_capital,
    )
    
    # 添加交易对
    instrument = create_binance_perpetual(symbol)
    engine.add_instrument(instrument)
    print(f"\n[INFO] 已添加仪器：{instrument.id}")
    
    # 配置策略
    strategy_config = BinanceScalpingStrategyConfig(
        instrument_id=f"{symbol}-PERP.BINANCE",
        symbol=symbol,
        base_position_size=base_position_size,
        max_positions=5,
        take_profit_pct=Decimal("0.01"),
        stop_loss_pct=Decimal("0.02"),
        confidence_threshold=0.95,
        bar_type="1-MINUTE",
    )
    
    # 创建策略实例
    strategy = BinanceScalpingStrategy(config=strategy_config)
    engine.add_strategy(strategy)
    
    # 加载历史数据
    if data_file:
        data_path = Path(data_file)
        if data_path.exists():
            print(f"\n[INFO] 从文件加载数据：{data_path}")
            # 这里需要实现数据加载逻辑
            # Nautilus Trader 支持多种数据格式
            # 简化示例：假设数据已准备好
            print("[WARNING] 数据加载需要实现 DataClient 或使用 Nautilus 的数据导入工具")
            print("[INFO] 请先运行 data_downloader.py 下载数据")
        else:
            print(f"\n[WARNING] 数据文件不存在：{data_path}")
            print("[INFO] 请先运行 data_downloader.py 下载历史数据")
    else:
        print("\n[INFO] 未指定数据文件，需要先下载历史数据")
        print("[INFO] 运行：python data_downloader.py")
    
    print("\n" + "=" * 70)
    print("回测配置完成!")
    print("=" * 70)
    print("\n下一步:")
    print("1. 运行 python data_downloader.py 下载历史 K 线数据")
    print("2. 修改本脚本添加数据加载逻辑")
    print("3. 运行 python backtest_runner.py 执行回测")
    print("\n或者使用简化测试:")
    print("  python backtest_simple.py")
    print("=" * 70)
    
    return engine


async def download_and_backtest(
    symbol: str = "BTCUSDT",
    days: int = 30,
    initial_capital: Decimal = Decimal("10000"),
):
    """
    一键下载数据并运行回测
    """
    from data_downloader import BinanceDataDownloader
    
    # 计算日期
    end = datetime.now()
    start = end - timedelta(days=days)
    
    print(f"\n[STEP 1] 下载 {days} 天历史数据...")
    downloader = BinanceDataDownloader()
    df = await downloader.download_klines(
        symbol=symbol,
        interval="1m",
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
    )
    
    if len(df) == 0:
        print("[ERROR] 数据下载失败")
        return
    
    # 保存数据
    data_file = downloader.save_to_parquet(df, symbol, "1m")
    
    print(f"\n[STEP 2] 运行回测...")
    await run_backtest(
        symbol=symbol,
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        initial_capital=initial_capital,
        data_file=str(data_file),
    )


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--full":
        # 完整模式：下载数据 + 回测
        asyncio.run(download_and_backtest(
            symbol="BTCUSDT",
            days=30,
            initial_capital=Decimal("10000"),
        ))
    else:
        # 仅配置回测
        asyncio.run(run_backtest(
            symbol="BTCUSDT",
            initial_capital=Decimal("10000"),
        ))
