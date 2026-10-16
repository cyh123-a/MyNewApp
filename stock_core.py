# -*- coding: utf-8 -*-
"""共享核心：配置 / 行情获取 / Android 状态栏通知"""
import json
import os
import re
from datetime import datetime, time as dtime

import requests

# Android 打包后 ANDROID_PRIVATE 是 App 私有目录，主程序与服务共享
_BASE = os.environ.get('ANDROID_PRIVATE') or os.path.expanduser('~')
CONFIG_FILE = os.path.join(_BASE, 'stockbar_config.json')

DEFAULT_CONFIG = {
    'stocks': ['sh600519', 'sz000001'],   # 默认贵州茅台 / 平安银行
    'interval': 10,                       # 秒
    'all_day': False,                     # 全天显示
}


# ---------- 配置读写 ----------
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
    except Exception as e:
        print('[config] load error:', e)
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(cfg, f, ensure_ascii=False)
    except Exception as e:
        print('[config] save error:', e)


# ---------- 交易时间 ----------
def in_trading_hours(now=None):
    now = now or datetime.now()
    if now.weekday() >= 5:                     # 周六周日
        return False
    t = now.time()
    return (dtime(9, 15) <= t <= dtime(11, 35)) or \
           (dtime(12, 55) <= t <= dtime(15, 30))


# ---------- 代码规整 ----------
def normalize_code(raw):
    code = (raw or '').strip().lower().replace(' ', '')
    if not code:
        return ''
    if code[:2] in ('sh', 'sz', 'bj') and len(code) == 8:
        return code
    if code.isdigit() and len(code) == 6:
        if code[0] == '6':
            return 'sh' + code
        if code[0] in ('0', '3'):
            return 'sz' + code
        if code[0] in ('4', '8'):
            return 'bj' + code
    return code


# ---------- 行情：腾讯（首选） ----------
def _fetch_tencent(codes):
    url = 'https://qt.gtimg.cn/q=' + ','.join(codes)
    r = requests.get(url, timeout=6, headers={'User-Agent': 'Mozilla/5.0'})
    r.encoding = 'gbk'
    out = {}
    for line in r.text.split(';'):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'v_([A-Za-z0-9]+)="(.*)"$', line)
        if not m:
            continue
        code = m.group(1)
        parts = m.group(2).split('~')
        if len(parts) < 5:
            continue
        name = parts[1]
        try:
            cur = float(parts[3])
            prev = float(parts[4])
        except (ValueError, IndexError):
            continue
        if prev == 0:
            continue
        out[code] = (name, (cur - prev) / prev * 100.0)
    if not out:
        raise RuntimeError('腾讯接口返回为空')
    return out


# ---------- 行情：新浪（备选） ----------
def _fetch_sina(codes):
    url = 'https://hq.sinajs.cn/list=' + ','.join(codes)
    headers = {'Referer': 'https://finance.sina.com.cn',
               'User-Agent': 'Mozilla/5.0'}
    r = requests.get(url, headers=headers, timeout=6)
    r.encoding = 'gbk'
    out = {}
    for line in r.text.split('\n'):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'var hq_str_([A-Za-z0-9]+)="(.*)";?', line)
        if not m:
            continue
        code = m.group(1)
        parts = m.group(2).split(',')
        if len(parts) < 4:
            continue
        name = parts[0]
        try:
            prev = float(parts[2])
            cur = float(parts[3])
        except (ValueError, IndexError):
            continue
        if prev == 0:
            continue
        out[code] = (name, (cur - prev) / prev * 100.0)
    if not out:
        raise RuntimeError('新浪接口返回为空')
    return out


def fetch_stocks(codes):
    """先腾讯，失败自动切新浪"""
    codes = [c for c in codes if c]
    if not codes:
        raise RuntimeError('没有股票代码')
    try:
        return _fetch_tencent(codes)
    except Exception as e:
        print('[data] 腾讯失败，切新浪:', e)
        return _fetch_sina(codes)


# ---------- 状态栏文本 ----------
def build_status_text(codes, result, ok):
    """🟢 表示该股票获取成功，🔴 表示失败/无数据"""
    items = []
    for code in codes:
        if ok and result and code in result:
            _, pct = result[code]
            items.append('🟢%+.2f%%' % pct)
        else:
            items.append('🔴--')
    return '  '.join(items)   # 用两个空格分隔（比 - 更清晰）


# ---------- Android 通知 ----------
def _get_context():
    """优先用 Service Context，回退到 Activity"""
    try:
        from jnius import autoclass
        ctx = autoclass('org.kivy.android.PythonService').mService
        if ctx:
            return ctx
    except Exception:
        pass
    try:
        from jnius import autoclass
        return autoclass('org.kivy.android.PythonActivity').mActivity
    except Exception:
        return None


def android_notify(text, nid=1001, title='股票行情'):
    ctx = _get_context()
    if ctx is None:
        print('[notify] no context:', text)
        return
    try:
        from jnius import autoclass
        NM = autoclass('android.app.NotificationManager')
        Channel = autoclass('android.app.NotificationChannel')
        Builder = autoclass('android.app.Notification$Builder')
        BuildV = autoclass('android.os.Build$VERSION')
        Context = autoclass('android.content.Context')
        Rdraw = autoclass('android.R$drawable')

        nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE)
        ch_id = 'stockbar'
        if BuildV.SDK_INT >= 26:
            ch = Channel(ch_id, '股票行情', NM.IMPORTANCE_LOW)
            ch.setShowBadge(False)
            ch.enableLights(False)
            ch.enableVibration(False)
            nm.createNotificationChannel(ch)

        b = Builder(ctx)
        if BuildV.SDK_INT >= 26:
            b.setChannelId(ch_id)
        b.setContentTitle(title)
        b.setContentText(text)
        b.setSmallIcon(Rdraw.stat_notify_sync)
        b.setOngoing(True)
        b.setOnlyAlertOnce(True)
        b.setShowWhen(False)
        b.setAutoCancel(False)
        nm.notify(nid, b.build())
    except Exception as e:
        print('[notify] error:', e)


def android_cancel(nid=1001):
    ctx = _get_context()
    if ctx is None:
        return
    try:
        from jnius import autoclass
        NM = autoclass('android.app.NotificationManager')
        Context = autoclass('android.content.Context')
        nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE)
        nm.cancel(nid)
    except Exception as e:
        print('[cancel] error:', e)