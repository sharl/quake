# -*- coding: utf-8 -*-
#
# これは外部サービスと連携するためのダミーモジュールです
#
# テキストのみの場合:
# {
#     'text': '2026/04/20 16:53:23 [INFO] 2026/04/20 16:53:21 第12報 三陸沖 M7.0 深さ 20km 最大予測震度 4'
# }
#
# 画像の場合:
# {
#     'text': '三陸沖',
#     'image_url': 'https://weather-pctr.c.yimg.jp/t/weather-img/earthquake/20260420165303/f802614a_1776671880_point.png'
# }
#
# のような固定フォーマット(text, image_url は変化します)で呼ばれるので
# 連携する API に合わせて data を加工して、ファイル名を post.py として配置してください
#
def post(data):
    pass
