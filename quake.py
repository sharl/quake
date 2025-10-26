# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import binascii
import ctypes
import io
import logging
import logging.handlers
import threading
import time
import webbrowser

from PIL import Image
from pystray import Icon, Menu, MenuItem
import darkdetect as dd
import requests
import schedule

TITLE = 'quake'
INTERVAL = 1
KMONI = 'http://www.kmoni.bosai.go.jp'
# https://www.jma.go.jp/jma/kishou/know/shindo/index.html
QUAKE_CLASS = '0 1 2 3 4 5弱 5強 6弱 6強 7'.split()
PreferredAppMode = {
    'Light': 0,
    'Dark': 1,
}
# https://github.com/moses-palmer/pystray/issues/130
ctypes.windll['uxtheme.dll'][135](PreferredAppMode[dd.theme()])


# logger settings
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.handlers.RotatingFileHandler("log.log", maxBytes=1000000, backupCount=0),
        logging.StreamHandler(),
    ],
    datefmt='%x %X'
)
logger = logging.getLogger(TITLE)
logger.setLevel(logging.DEBUG)


class taskTray:
    def __init__(self):
        self.running = False
        # quake status
        self.status = {}
        # hamu report
        self.report_id = str()
        # quake class check: 0, 1 is False
        self.quake_check = {i: (i not in ['0', '1']) for i in QUAKE_CLASS}

        image = Image.open(io.BytesIO(binascii.unhexlify(ICON.replace('\n', '').strip())))
        item = [
            MenuItem(TITLE, self.doOpen, default=True),
            Menu.SEPARATOR,
            MenuItem('Set All', self.setAll),
            MenuItem('Unset All', self.unsetAll),
            Menu.SEPARATOR,
        ]
        for i in self.quake_check:
            item.append(MenuItem(i, self.toggle, checked=lambda x: self.quake_check[str(x)]))
        item.append(Menu.SEPARATOR)
        item.append(MenuItem('Exit', self.stopApp))
        menu = Menu(*item)
        self.app = Icon(name=f'PYTHON.win32.{TITLE}', title=TITLE, icon=image, menu=menu)

    def doOpen(self):
        webbrowser.open(KMONI)

    def setAll(self):
        for i in self.quake_check:
            self.quake_check[i] = True
        self.app.update_menu()

    def unsetAll(self):
        for i in self.quake_check:
            self.quake_check[i] = False
        self.app.update_menu()

    def toggle(self, _, _item):
        item = str(_item)
        self.quake_check[item] = not self.quake_check[item]
        self.app.update_menu()

    def doTask(self):
        # {
        #   "result": {
        #     "status": "success",
        #     "message": "",
        #     "is_auth": true
        #   },
        #   "report_time": "2025/10/24 09:27:52",
        #   "region_code": "",
        #   "request_time": "202510240927%s",
        #   "region_name": "宮城県沖",
        #   "longitude": "141.7",
        #   "is_cancel": false,
        #   "depth": "60km",
        #   "calcintensity": "2",
        #   "is_final": false,
        #   "is_training": false,
        #   "latitude": "38.2",
        #   "origin_time": "20251024092714",
        #   "security": {
        #     "realm": "/kyoshin_monitor/static/jsondata/eew_est/",
        #     "hash": "b61e4d95a8c42e004665825c098a6de4"
        #   },
        #   "magunitude": "3.5",
        #   "report_num": "2",
        #   "request_hypo_type": "eew",
        #   "report_id": "20251024092722",
        #   "alertflg": "予報"
        # }
        for t in range(2, 10):
            now = datetime.now() - timedelta(seconds=t)
            url = f'{KMONI}/webservice/hypo/eew/{now.strftime("%Y%m%d%H%M%S")}.json'
            try:
                with requests.get(url, timeout=1) as r:
                    data = r.json()
                    # print(url, t)
                    if data.get('report_time'):
                        if self.status != data:
                            logger.info(data)
                            calcintensity = data.get('calcintensity')
                            lines = [
                                '【訓練】' if data.get('is_training') else '',
                                data.get('report_time') + (' 最終報' if data.get('is_final') else f' 第{data.get("report_num")}報'),
                                data.get('region_name'),
                                f'M{data.get("magunitude")} 深さ {data.get("depth")}',
                                f'最大予測震度 {calcintensity}',
                            ]
                            self.app.title = '\n'.join(lines).strip()
                            self.app.update_menu()

                            # result in one line
                            result = ' '.join(lines).strip()
                            logger.info(result)

                            # hamu
                            # 指定された震度の場合のみ送信
                            report_id = data.get('report_id')
                            if self.quake_check[calcintensity] and self.report_id != report_id:
                                requests.post(
                                    'http://localhost:16543/chat_postMessage',
                                    json={
                                        # 'channel': 'dev',
                                        'text': result,
                                    }
                                )
                                self.report_id = report_id

                            self.status = data
                    break
            except Exception as e:
                print('Exception', e, url, t)

    def runSchedule(self):
        schedule.every(INTERVAL).seconds.do(self.doTask)

        while self.running:
            schedule.run_pending()
            time.sleep(1)

    def stopApp(self):
        self.running = False
        self.app.stop()

    def runApp(self):
        self.running = True

        task_thread = threading.Thread(target=self.runSchedule)
        task_thread.start()

        self.app.run()


ICON = """
47494638396110001000f700006b6b3f6c6c3e6e6e3e7676367d7d337979367979377171387373397676394242424c4c4746464a47474a4848494949
494a4a4849494a4a4a4a4b4b4b4f4f494d4d4b4f4f4a4e4e4b48484c4b4b4c4a4a4d4b4b4d4c4c4c4d4d4d4f4f4f5555435151455252455353475151
485353485353495454484f4f535050505151515252515252525353535757575555585858585959595d5d5d5e5e5e65654066665b7f7f5570705d6464
6364646465656567676569696762626a6464686a6a697f7f797e7e7ab9b91bbfbf19baba1cbbbb1c96962995952b99992899992a9d9d28818134a0a0
25a1a126a9a92aacac28adad34a0a03dc7c717cece14cfcf14d2d211d3d311d4d410dcdc15d4d41bd4d41cd5d51ce1e10ce8e809f0f006f0f007f5f5
04f6f604f8f803f9f903fcfc01ffff00ffff01fefe02f9f904fafa04f4f408fdfd08e8e810e9e910c5c52bc5c52cd6d626d4d4298080488c8c4a9292
46efef4ff0f04dd6d670d6d672e6e69ae6e69cd7d7c6d8d8c5d6d6cfd8d8d1d9d9d1dadad2e3e3c0e2e2c1e1e1ce0000000000000000000000000000
000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000
0021f904000000000021ff0b496d6167654d616769636b0e67616d6d613d302e343534353435002c00000000100010000008d5009fd48853e0c38310
03848421c3b0a18d1e34042c78f0a0410824601a3294c3038a17020d285264a291cc953958c8041149f103959267185a09c1b28191920da984c8c0a1
6706041919869112858b129e3d396498b1258a9430494c9040502169d20a0848986052812752ab3e959248d055850ab01ccc66a860c0cb1000697b9a
95cb41c0102f0c8d9c78d1428502052a5ebc38814463131738649c4d2b03870b271ae100f17103c78e1d386ef888f3a6611a3777f4f0f143da0f9f3d
77dca42173260b1b3574f204122428109e3a6ad864391310003b
"""

if __name__ == '__main__':
    taskTray().runApp()
