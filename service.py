# -*- coding: utf-8 -*-
"""后台服务：即使 App 退到后台/锁屏，也继续刷新状态栏。
   非交易时段自动取消通知。"""
import time
import traceback

from stock_core import (
    load_config, in_trading_hours, fetch_stocks,
    build_status_text, android_notify, android_cancel,
)

NID = 1001


def main():
    last_state = None
    while True:
        try:
            cfg = load_config()
            stocks = cfg.get('stocks', [])
            interval = max(2, int(cfg.get('interval', 10)))
            all_day = bool(cfg.get('all_day', False))

            if not stocks:
                time.sleep(interval)
                continue

            # 非交易时段 → 不显示
            if not all_day and not in_trading_hours():
                if last_state != 'off':
                    android_cancel(NID)
                    last_state = 'off'
                time.sleep(30)
                continue

            try:
                data = fetch_stocks(stocks)
                text = build_status_text(stocks, data, True)
                last_state = 'on'
            except Exception as e:
                print('[service] fetch failed:', e)
                text = build_status_text(stocks, {}, False)
                last_state = 'err'

            android_notify(text, NID)
            time.sleep(interval)
        except Exception:
            traceback.print_exc()
            time.sleep(10)


if __name__ == '__main__':
    main()