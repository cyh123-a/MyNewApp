# -*- coding: utf-8 -*-
"""股票状态栏 - 主程序"""
import threading

from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.utils import platform

from stock_core import (
    load_config, save_config, in_trading_hours, normalize_code,
    fetch_stocks, build_status_text, android_notify, android_cancel,
)

IS_ANDROID = (platform == 'android')
NID = 1001


# ---------------- 单行股票 ----------------
class StockRow(BoxLayout):
    def __init__(self, code, on_delete, **kw):
        super().__init__(orientation='horizontal', size_hint_y=None,
                         height=dp(46), spacing=dp(4), **kw)
        self.code = code
        self.name_label = Label(text='--', size_hint_x=0.35, font_size=dp(14))
        self.add_widget(self.name_label)

        self.code_label = Label(text=code, size_hint_x=0.25,
                                font_size=dp(11), color=(0.6, 0.6, 0.6, 1))
        self.add_widget(self.code_label)

        self.pct_label = Label(text='--', size_hint_x=0.28,
                               font_size=dp(15), bold=True)
        self.add_widget(self.pct_label)

        self.add_widget(Button(text='✕', size_hint_x=0.12, font_size=dp(14),
                               background_color=(0.75, 0.2, 0.2, 1),
                               on_release=lambda *a: on_delete(self)))

    def update(self, name, pct):
        if name:
            self.name_label.text = name
        if pct is None:
            self.pct_label.text = '--'
            self.pct_label.color = (0.6, 0.6, 0.6, 1)
        elif pct > 0:                              # 红涨
            self.pct_label.text = '%+.2f%%' % pct
            self.pct_label.color = (1.0, 0.28, 0.28, 1)
        elif pct < 0:                              # 绿跌
            self.pct_label.text = '%.2f%%' % pct
            self.pct_label.color = (0.25, 0.9, 0.35, 1)
        else:
            self.pct_label.text = '0.00%'
            self.pct_label.color = (1, 1, 1, 1)


# ---------------- App ----------------
class StockBarApp(App):
    def build(self):
        if IS_ANDROID:
            try:
                from android.permissions import request_permissions, Permission
                request_permissions([Permission.POST_NOTIFICATIONS,
                                     Permission.INTERNET])
            except Exception as e:
                print('[perm]', e)

        self.cfg = load_config()
        self.rows = []
        self.fetching = False
        self.timer = None
        self.service = None

        root = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(8))

        # 顶部预览：模拟状态栏文本
        self.preview = Label(text='等待数据…', size_hint_y=None, height=dp(44),
                             font_size=dp(15), bold=True, color=(1, 1, 1, 1))
        root.add_widget(self.preview)

        # 股票列表
        scroll = ScrollView(size_hint_y=None, height=dp(150))
        self.list_box = BoxLayout(orientation='vertical',
                                  size_hint_y=None, spacing=dp(2))
        self.list_box.bind(minimum_height=self.list_box.setter('height'))
        scroll.add_widget(self.list_box)
        root.add_widget(scroll)

        # 按钮行
        row1 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        row1.add_widget(Button(text='＋ 添加股票', on_release=self.open_add))
        row1.add_widget(Button(text='⟳ 立即刷新',
                               on_release=lambda *a: self.refresh()))
        root.add_widget(row1)

        # 间隔设置
        row2 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        row2.add_widget(Label(text='刷新间隔(秒)', size_hint_x=0.35,
                              font_size=dp(14)))
        self.interval_input = TextInput(text=str(self.cfg['interval']),
                                        input_filter='int', multiline=False,
                                        size_hint_x=0.3, font_size=dp(14))
        row2.add_widget(self.interval_input)
        row2.add_widget(Button(text='保存', size_hint_x=0.35,
                               on_release=self.save_interval))
        root.add_widget(row2)

        # 全天显示
        row3 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        row3.add_widget(Label(text='全天显示（不限制交易时段）',
                              font_size=dp(14)))
        self.all_day_cb = CheckBox(active=bool(self.cfg['all_day']),
                                   size_hint_x=0.2)
        self.all_day_cb.bind(active=self.toggle_all_day)
        row3.add_widget(self.all_day_cb)
        root.add_widget(row3)

        tip = Label(text='交易时段：工作日 9:15-11:35 / 12:55-15:30\n'
                         '非交易时段不显示（勾选"全天显示"除外）',
                    size_hint_y=None, height=dp(46),
                    font_size=dp(11), color=(0.65, 0.65, 0.65, 1))
        root.add_widget(tip)

        self.rebuild_rows()
        Clock.schedule_once(lambda *a: self.start_timer(), 0.3)
        Clock.schedule_once(lambda *a: self.start_service(), 0.5)
        return root

    # ---- 启动 Android 后台服务 ----
    def start_service(self):
        if not IS_ANDROID:
            return
        try:
            from android import AndroidService
            self.service = AndroidService('股票状态栏', '正在后台更新行情')
            self.service.start('')
        except Exception as e:
            print('[service] start failed:', e)

    # ---- 股票行管理 ----
    def rebuild_rows(self):
        self.list_box.clear_widgets()
        self.rows = []
        for code in self.cfg['stocks']:
            row = StockRow(code, self.remove_stock)
            self.rows.append(row)
            self.list_box.add_widget(row)

    def open_add(self, *a):
        if len(self.cfg['stocks']) >= 3:
            self.popup_msg('提示', '最多只能添加 3 个股票')
            return
        content = BoxLayout(orientation='vertical', spacing=dp(10),
                            padding=dp(10))
        content.add_widget(Label(
            text='输入股票代码\n例：sh600519 / 600519 / 000001',
            font_size=dp(13), halign='center'))
        ti = TextInput(multiline=False, font_size=dp(16))
        content.add_widget(ti)
        btns = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        popup = Popup(title='添加股票', content=content,
                      size_hint=(0.85, 0.5))

        def do_add(*a):
            code = normalize_code(ti.text)
            if code and code not in self.cfg['stocks']:
                self.cfg['stocks'].append(code)
                save_config(self.cfg)
                self.rebuild_rows()
                self.refresh()
            popup.dismiss()

        btns.add_widget(Button(text='取消', on_release=popup.dismiss))
        btns.add_widget(Button(text='确定', on_release=do_add))
        content.add_widget(btns)
        popup.open()

    def remove_stock(self, row):
        if row.code in self.cfg['stocks']:
            self.cfg['stocks'].remove(row.code)
            save_config(self.cfg)
            self.rebuild_rows()
            self.refresh()

    def popup_msg(self, title, msg):
        content = BoxLayout(orientation='vertical', padding=dp(10),
                            spacing=dp(10))
        content.add_widget(Label(text=msg))
        popup = Popup(title=title, content=content, size_hint=(0.8, 0.35))
        content.add_widget(Button(text='好', size_hint_y=None, height=dp(44),
                                  on_release=popup.dismiss))
        popup.open()

    # ---- 设置 ----
    def save_interval(self, *a):
        try:
            v = int(self.interval_input.text or '10')
        except ValueError:
            v = 10
        v = max(2, min(v, 3600))
        self.cfg['interval'] = v
        self.interval_input.text = str(v)
        save_config(self.cfg)
        self.start_timer()
        self.popup_msg('提示', '已设置为每 %d 秒刷新' % v)

    def toggle_all_day(self, cb, value):
        self.cfg['all_day'] = bool(value)
        save_config(self.cfg)
        self.refresh()

    # ---- 定时刷新 ----
    def start_timer(self):
        if self.timer:
            self.timer.cancel()
        self.timer = Clock.schedule_interval(
            self.tick, max(2, int(self.cfg['interval'])))
        self.tick(0)

    def tick(self, dt):
        if self.cfg.get('all_day') or in_trading_hours():
            self.refresh()
        else:
            self.preview.text = '非交易时段，已停止刷新'
            for r in self.rows:
                r.update(None, None)
            if IS_ANDROID:
                android_cancel(NID)

    def refresh(self):
        if self.fetching:
            return
        self.fetching = True
        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        codes = list(self.cfg['stocks'])
        try:
            data = fetch_stocks(codes)
            Clock.schedule_once(
                lambda dt: self._apply(codes, data, True), 0)
        except Exception as e:
            print('[app] fetch error:', e)
            Clock.schedule_once(
                lambda dt: self._apply(codes, {}, False), 0)

    def _apply(self, codes, data, ok):
        self.fetching = False
        for row in self.rows:
            if ok and row.code in data:
                name, pct = data[row.code]
                row.update(name, pct)
            else:
                row.update(None, None)
        text = build_status_text(codes, data, ok)
        self.preview.text = text
        if IS_ANDROID:
            android_notify(text, NID)

    # ---- 生命周期 ----
    def on_pause(self):
        return True

    def on_resume(self):
        self.start_timer()


if __name__ == '__main__':
    StockBarApp().run()