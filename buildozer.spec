[app]
title = 股票状态栏
package.name = stockbar
package.domain = org.cyh

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt

version = 1.0.0

requirements = python3,kivy==2.3.0,requests,urllib3,chardet,idna,certifi,pyjnius,android

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,WAKE_LOCK
android.api = 34
android.minapi = 24
android.ndk = 25b
android.ndk_api = 24

# 后台服务：类型 foreground 保证 Android 12+ 不被杀
services = StockService:service.py:foreground

android.archs = arm64-v8a

[buildozer]
log_level = 2
warn_on_root = 1