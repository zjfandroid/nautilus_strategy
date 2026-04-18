# 币安 U 本位合约短线撸短策略

基于 Nautilus Trader 框架实现的币安 U 本位永续合约短线策略。

## 策略核心逻辑

1. **分批建仓**: 最高可分 5 次投入，降低单次入场风险
2. **快速止盈**: 每次赚到 1% 就止盈离场
3. **高把握度入场**: 95% 把握度判断，只在下跌企稳后做反弹
4. **风险控制**: 
   - 不接下跌飞刀（下跌趋势中不买入）
   - 不追涨（大幅上涨后不买入）
   - 2% 止损保护

## 技术指标

策略综合以下 5 个维度计算入场信号把握度：

| 指标 | 权重 | 说明 |
|------|------|------|
| RSI 超卖 | 30% | RSI<30 为超卖，得分最高 |
| 价格企稳 | 25% | 最近 5 根 K 线不再创新低 |
| 成交量 | 20% | 企稳时缩量，反弹时放量 |
| 均线支撑 | 15% | 价格在 MA20 附近或上方 |
| 趋势判断 | 10% | 均线多头排列 (MA5>MA10>MA20) |

## 安装

```bash
cd /Users/silent/workspace/nautilus_binance_strategy

# 创建虚拟环境 (Python 3.11+)
python3.12 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

## 使用方法

### 1. 下载历史数据

```bash
# 下载 BTCUSDT 近 30 天 1 分钟 K 线数据
python data_downloader.py
```

数据将保存到 `data/` 目录，支持 CSV 和 Parquet 格式。

### 2. 运行回测

```bash
# 配置回测（需要先下载数据）
python backtest_runner.py

# 一键模式：下载数据 + 运行回测
python backtest_runner.py --full
```

### 3. 自定义参数

编辑 `backtest_runner.py` 修改以下参数：

```python
symbol = "BTCUSDT"           # 交易对
days = 30                    # 回测天数
initial_capital = 10000      # 初始资金 (USDT)
base_position_size = 1000    # 总仓位 (USDT)
```

## 策略配置

在 `strategies/binance_scalping_strategy.py` 中可调整：

```python
max_positions = 5            # 最多分几次投入
take_profit_pct = 0.01       # 止盈比例 (1%)
stop_loss_pct = 0.02         # 止损比例 (2%)
confidence_threshold = 0.95  # 入场把握度阈值 (95%)
bar_type = "1-MINUTE"        # K 线周期
```

## 支持的交易对

任何币安 U 本位永续合约：
- BTCUSDT
- ETHUSDT
- BNBUSDT
- SOLUSDT
- 等等...

修改 `symbol` 参数即可切换交易对。

## 回测输出

回测完成后将输出：
- 总交易次数
- 盈利/亏损次数
- 胜率
- 总盈亏 (USDT)
- 每次交易的详细信息

## 注意事项

1. **数据质量**: 回测结果依赖于历史数据质量
2. **滑点**: 实际交易可能存在滑点，回测未完全模拟
3. **手续费**: 已配置币安标准手续费 (Maker 0.02%, Taker 0.04%)
4. **风险**: 加密货币交易风险高，请谨慎使用

## 项目结构

```
nautilus_binance_strategy/
├── strategies/
│   └── binance_scalping_strategy.py   # 策略核心
├── data/                               # 历史数据目录
├── configs/                            # 配置文件目录
├── results/                            # 回测结果目录
├── data_downloader.py                  # 数据下载器
├── backtest_runner.py                  # 回测脚本
├── requirements.txt                    # 依赖列表
└── README.md                           # 说明文档
```

## 扩展开发

### 添加新的交易对

```python
# 在 backtest_runner.py 中
symbols = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
for symbol in symbols:
    await run_backtest(symbol=symbol)
```

### 调整策略参数

修改 `BinanceScalpingStrategyConfig` 类中的默认值。

### 添加更多技术指标

在 `calculate_confidence()` 方法中添加新的评分维度。

## License

MIT License
