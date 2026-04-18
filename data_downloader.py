"""
币安历史数据下载器
下载 U 本位合约 K 线数据用于回测
"""

import asyncio
import aiohttp
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import json


class BinanceDataDownloader:
    """币安数据下载器"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.base_url = "https://fapi.binance.com/fapi/v1/klines"
    
    async def download_klines(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "1m",
        start_date: str = None,
        end_date: str = None,
        limit_per_request: int = 1000,
        timeout_seconds: int = 60,
        use_proxy: bool = True,
    ):
        """
        下载 K 线数据
        
        Args:
            symbol: 交易对 (如 BTCUSDT)
            interval: K 线周期 (1m, 3m, 5m, 15m, 30m, 1h, 4h, 1d)
            start_date: 开始日期 (YYYY-MM-DD)
            end_date: 结束日期 (YYYY-MM-DD)
            limit_per_request: 每次请求最大条数 (最大 1000)
        
        Returns:
            DataFrame with columns: timestamp, open, high, low, close, volume
        """
        
        if end_date is None:
            end_dt = datetime.now()
        else:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        if start_date is None:
            start_dt = end_dt - timedelta(days=30)
        else:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        
        print(f"下载 {symbol} {interval} 数据：{start_dt.date()} 至 {end_dt.date()}")
        
        all_klines = []
        current_start = start_dt
        
        # 配置代理 (macOS 系统代理)
        proxy = None
        if use_proxy:
            proxy = "http://127.0.0.1:7890"
            print(f"使用代理：{proxy}")
        
        connector = aiohttp.TCPConnector(ssl=False)
        
        async with aiohttp.ClientSession(
            connector=connector,
            headers={"User-Agent": "Mozilla/5.0"},
        ) as session:
            while current_start < end_dt:
                start_ts = int(current_start.timestamp() * 1000)
                
                params = {
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": start_ts,
                    "limit": limit_per_request,
                }
                
                try:
                    async with session.get(self.base_url, params=params, timeout=aiohttp.ClientTimeout(total=timeout_seconds), proxy=proxy) as resp:
                        if resp.status != 200:
                            print(f"请求失败：{resp.status}")
                            break
                        
                        klines = await resp.json()
                        
                        if not klines:
                            break
                        
                        all_klines.extend(klines)
                        
                        # 更新起始时间
                        last_kline_time = datetime.fromtimestamp(klines[-1][0] / 1000)
                        current_start = last_kline_time + timedelta(minutes=1)
                        
                        print(f"已下载至：{last_kline_time} (累计 {len(all_klines)} 条)")
                        
                except Exception as e:
                    print(f"下载出错：{e}")
                    break
        
        # 转换为 DataFrame
        if not all_klines:
            print("未下载任何数据")
            return pd.DataFrame()
        
        df = pd.DataFrame(all_klines, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "taker_buy_base",
            "taker_buy_quote", "ignore"
        ])
        
        # 数据类型转换
        df["timestamp"] = pd.to_datetime(df["timestamp"].astype(int), unit="ms")
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        df["volume"] = df["volume"].astype(float)
        
        # 保留需要的列
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        
        print(f"下载完成！共 {len(df)} 条 K 线数据")
        return df
    
    def save_to_csv(self, df: pd.DataFrame, symbol: str, interval: str):
        """保存数据到 CSV"""
        filename = self.data_dir / f"{symbol}_{interval}_{datetime.now().strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False)
        print(f"数据已保存至：{filename}")
        return filename
    
    def save_to_parquet(self, df: pd.DataFrame, symbol: str, interval: str):
        """保存数据到 Parquet (推荐)"""
        filename = self.data_dir / f"{symbol}_{interval}_{datetime.now().strftime('%Y%m%d')}.parquet"
        df.to_parquet(filename, index=False)
        print(f"数据已保存至：{filename}")
        return filename


async def main():
    """主函数 - 下载近 1 个月数据"""
    downloader = BinanceDataDownloader()
    
    # 计算日期范围
    end = datetime.now()
    start = end - timedelta(days=30)
    
    # 下载 BTCUSDT 1 分钟 K 线
    df = await downloader.download_klines(
        symbol="BTCUSDT",
        interval="1m",
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
    )
    
    if len(df) > 0:
        # 保存数据
        downloader.save_to_parquet(df, "BTCUSDT", "1m")
        downloader.save_to_csv(df, "BTCUSDT", "1m")
        
        # 显示统计信息
        print("\n数据统计:")
        print(f"  开始时间：{df['timestamp'].min()}")
        print(f"  结束时间：{df['timestamp'].max()}")
        print(f"  最高价：{df['high'].max()}")
        print(f"  最低价：{df['low'].min()}")
        print(f"  平均成交量：{df['volume'].mean():.2f}")


if __name__ == "__main__":
    asyncio.run(main())
