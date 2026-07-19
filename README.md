# quake

緊急地震速報を音などでお知らせ

VOICEVOX Engine が起動していれば "警告: n秒後に到達します" とお知らせしてくれます

通知機能をカスタマイズすることで様々なサービスに対応可能
- Discord
- Email
- Slack
- X (formerly known as Twitter)

etc..

## Run

```powershell
git clone https://github.com/sharl/quake.git
cd quake
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
cp post_template.py post.py
python quake.py
```

## config, log

```
~\.config\quake\config.json
~\.local\state\quake\log.log
```

XDG_CONFIG_HOME, XDG_STATE_HOME に準拠しています

一度実行すると ~\.config\quake\config.json が生成されます

```powershell
PS> Get-Content ~/.config/quake/config.json | python -m json.tool
{
    "check": {
        "1": false,
        "2": false,
        "3": true,
        "4": true,
        "5\u8811\uff71": true,
        "5\u8811\uff77": true,
        "6\u8811\uff71": true,
        "6\u8811\uff77": true,
        "7": true
    },
    "sound": true,
    "epicenter": false,
    "delay": 3,
    "mapboxes": {}
}
```

### 震央情報に MAPBOX を使用可能

maxboxes を設定することで震央に対応した画像URLを生成可能です

```
    "mapboxes": {
        "MAPBOX_ACCESS_TOKEN": "YOUR MAPBOX ACCESS TOKEN",
        "MAPBOX_USERNAME": "YOUR MAPBOX USER NAME",
        "MAPBOX_STYLE_ID": "YOUR MAPBOX USER STYLE ID"
    }
```

## sound

ニュース速報のアラーム - ニコニ・コモンズ  
https://commons.nicovideo.jp/works/nc124106  
をトリミングしたものを利用しています
