"""Japanese and Korean, as overlays on the base table in ``i18n``.

The original three languages live in ``i18n.STRINGS`` as a tuple per key. Two
more would have meant editing 278 tuples, and every future string would have
to be written five times before the app would start. These are dictionaries
instead: a key that is missing here falls back to English, so an untranslated
string is a small blemish rather than a crash or a bare key on screen.

Placeholders in braces are part of the contract with the code that formats
them - ``{total}``, ``{version}`` and the rest must survive translation.
"""

from __future__ import annotations

JA: dict = {
    "app.title": "LagScope",
    "app.short": "B站 遅延",
    "app.short_generic": "遅延",

    "menu.show_overlay": "オーバーレイを表示",
    "menu.lock": "位置を固定",
    "menu.click_through": "クリックを透過",
    "menu.pause": "計測を一時停止",
    "menu.resume": "計測を再開",
    "menu.reset_position": "オーバーレイの位置をリセット",
    "menu.settings": "設定…",
    "menu.copy_diag": "診断情報をコピー",
    "menu.open_config": "設定フォルダーを開く",
    "menu.about": "このアプリについて",
    "menu.quit": "終了",

    "label.total": "合計",
    "label.network": "ネットワーク",
    "label.stream": "配信",
    "label.display": "表示",
    "label.avg": "平均",
    "label.p95": "P95",
    "label.jitter": "ジッター",
    "label.range": "範囲",
    "label.room": "配信",
    "label.video": "動画",
    "label.startup": "再生開始",
    "label.speed": "帯域",
    "label.latency": "遅延",
    "label.connections": "接続数",
    "label.app": "アプリ",
    "label.target": "対象",
    "label.down": "下り",
    "label.up": "上り",
    "label.measured": "実測",
    "label.estimated": "推定",
    "label.auto": "自動",

    "status.no_room": "配信が未設定です",
    "status.offline": "配信していません",
    "status.connecting": "接続中…",
    "status.paused": "一時停止中",
    "status.error": "計測に失敗しました",
    "status.network_only": "ネットワークのみ",
    "status.no_video": "動画が未設定です",
    "status.no_app": "アプリが未選択です",
    "status.no_connections": "そのアプリは現在ネットワークに接続していません",
    "status.unreachable": "対象に到達できません",
    "status.no_reply": "そのアプリのサーバーは応答しません（ping が遮断されている可能性）",
    "status.detecting": "視聴中のページを判別しています…",

    "menu.diagnose": "ネットワーク診断…",
    "diag.title": "ネットワーク診断",
    "diag.running": "各区間を計測しています…（約 10 秒）",
    "diag.you_router": "あなた → ルーター",
    "diag.router_isp": "ルーター → プロバイダー",
    "diag.to_target": "→ 対象サーバー",
    "diag.wifi": "Wi-Fi",
    "diag.loss": "損失",
    "diag.dns": "名前解決",
    "diag.no_gateway": "デフォルトゲートウェイが見つかりません",
    "diag.gateway_silent": "ルーターが ping に応答しません（よくある設定で、故障ではありません）",

    "verdict.ok": "ネットワークは正常に見えます",
    "verdict.wifi": "遅延の大半はあなたとルーターの間にあり、Wi-Fi の電波も弱めです"
                    "——ルーターに近づくか有線に変えると大きく改善します。",
    "verdict.home": "遅延の大半は宅内（あなた↔ルーター）です。Wi-Fi やルーターの負荷を確認するか、"
                    "有線に変えてください。",
    "verdict.isp": "宅内は正常で、遅延はプロバイダー側の区間から増えています。"
                   "ここは自分では直せないので、このレポートをサポートに見せてください。",
    "verdict.server": "回線は正常です。遅延はサーバーまでの距離や経路によるもので、"
                      "近いサーバー／ノードに変えるのが一番効きます。",
    "verdict.loss": "パケットロスがあります——ゲームや通話には遅延より響くので、こちらを先に。",
    "verdict.target_down": "対象が応答しません（ping を遮断しているか停止中）が、"
                           "あなたのネットワーク自体は正常です。",
    "verdict.no_ping": "この PC で使える ping コマンドが見つからないため、区間ごとの診断はできません"
                       "（他の機能は問題なく動きます）。",
    "verdict.dns": "回線自体は正常ですが、名前解決が遅いです——これが返るまで何も始まりません。"
                   "DNS を 8.8.8.8 や 1.1.1.1 に変えるとたいてい即座に直ります。",
    "verdict.unknown": "データが足りず判断できません",

    "settings.title": "設定",
    "settings.tab.general": "一般",
    "settings.tab.overlay": "表示",
    "settings.tab.advanced": "詳細",
    "settings.tab.about": "情報",

    "general.target": "計測する対象",
    "general.target.auto": "見ているページに自動で追従",
    "general.target.live": "配信を手動で指定",
    "general.target.video": "動画を手動で指定",
    "general.target.app": "任意のアプリ（ゲーム／通話／ブラウザー…）",
    "general.target.custom": "サーバーアドレスを指定",
    "general.app_name": "アプリ",
    "general.app_follow": "今使っているアプリに自動で追従",
    "general.app_hint": "ネットワークを使っているプログラムを選ぶと、"
                        "接続先サーバーを見つけて遅延を計り続けます。UDP のゲームは ping に切り替わります。",
    "general.app_refresh": "更新",
    "general.target_host": "サーバーアドレス",
    "general.target_port": "ポート",
    "general.target_hint": "ゲームサーバー、社内 VPN、8.8.8.8 など。まず TCP、駄目なら ping。",
    "general.netspeed": "PC 全体の上り／下り速度を表示",
    "general.video": "動画 ID または URL",
    "general.video_hint": "BV 番号、av 番号、または https://www.bilibili.com/video/BV… "
                          "（パート指定は ?p=2）。",
    "general.room": "配信 ID または URL",
    "general.room_hint": "https://live.bilibili.com/123456 を貼るか 123456 だけでも可。"
                         "空ならネットワークのみを計測します。",
    "general.interval": "計測間隔（ミリ秒）",
    "general.sample_window": "統計の窓（サンプル数）",
    "general.language": "表示言語",
    "general.language_auto": "システムに従う",
    "general.autostart": "PC 起動時に自動で開始",
    "general.autostart_unsupported": "この環境では自動起動を設定できません。README を参照してください。",
    "general.notify": "カクつき・遅延スパイクを通知する",

    "detect.group": "自動検出",
    "detect.history": "ブラウザーの履歴を読む（読み取りのみ）",
    "detect.titles": "ウィンドウタイトルで判別（Windows）",
    "detect.bridge": "ユーザースクリプトの報告を受け取る（最も正確）",
    "detect.client": "公式 PC クライアントの再生中の内容を読む",
    "detect.clipboard": "コピーしたリンクを検出（クライアント用）",
    "detect.remember_titles": "ウィンドウタイトルと配信の対応を覚える",
    "detect.client_hint": "公式 PC クライアントではクライアント自身の記録を読むので、操作は不要です。"
                          "バージョン差で読めない場合も「共有 → リンクをコピー」ですぐ切り替わります。"
                          "コマンドラインに --detect-report を付けると何が読めているか確認できます。",
    "detect.bridge_port": "スクリプトの受信ポート",
    "detect.window": "履歴をさかのぼる時間（分）",
    "detect.follow_videos": "通常の動画にも追従する",
    "detect.interval": "検出間隔（秒）",
    "detect.privacy": "検出はこの PC 内だけで行われます。履歴ファイルは一時コピーを読み取り専用で開き、"
                      "bilibili.com の URL だけを抽出します。書き戻しも送信もせず、ログインも不要です。"
                      "不要ならこの項目をオフにできます。",
    "detect.source.manual": "手動",
    "detect.source.clipboard": "コピーしたリンク",
    "detect.source.title": "ウィンドウタイトル",
    "detect.source.history": "履歴",
    "detect.source.history+title": "現在のタブ",
    "detect.source.bridge": "スクリプト",
    "menu.auto_detect": "見ているページに追従",
    "menu.read_clipboard": "クリップボードのリンクを読む",
    "notice.clipboard_read": "クリップボードを読みました。B站のリンクならすぐ切り替わります。",

    "menu.phone": "スマホ用アドレス…",
    "extras.group": "同時に監視（追加）",
    "extras.hint": "主対象のほかにいくつか監視して、「これだけ遅い」のか「回線全体が遅い」のかを"
                   "見分けます。最大 4 つ、順番に計測するので主計測は遅くなりません。",
    "extras.add": "追加…",
    "extras.remove": "削除",
    "extras.add_router": "＋ルーター",
    "extras.add_dns": "＋DNS",
    "extras.router": "ルーター",
    "extras.dns": "DNS",
    "extras.dialog": "監視対象を追加",
    "extras.kind": "種類",
    "extras.kind.target": "サーバーアドレス",
    "extras.kind.app": "アプリ",
    "extras.ident": "アドレス／プロセス名",
    "extras.label": "表示名",
    "extras.full": "追加できるのは 4 つまでです",
    "extras.no_router": "ルーターのアドレスが見つかりません",

    "web.group": "スマホ用ダッシュボード",
    "web.enabled": "同じネットワークのスマホからも見られるようにする",
    "web.port": "ポート",
    "web.code": "アクセスコード（空＝不要）",
    "web.hint": "下のアドレスをスマホのブラウザーで開くと同じ数値がリアルタイムで見られます。"
                "アプリのインストールは不要で iPhone でも Android でも同じです。"
                "読み取り専用でスマホからは何も変更できず、アドレスは自宅のネットワーク内でのみ有効です。",
    "web.url_label": "スマホで開く：",
    "web.off": "無効です（設定でオンにしてください）",
    "web.copied": "アドレスをクリップボードにコピーしました",

    "overlay.enabled": "オーバーレイを表示する",
    "overlay.anchor": "位置モード",
    "overlay.anchor.free": "自由に配置（ドラッグ）",
    "overlay.anchor.screen": "画面の隅に固定",
    "overlay.anchor.window": "B站のウィンドウに追従",
    "overlay.corner": "隅",
    "overlay.corner.top-left": "左上",
    "overlay.corner.top-right": "右上",
    "overlay.corner.bottom-left": "左下",
    "overlay.corner.bottom-right": "右下",
    "overlay.screen": "画面",
    "overlay.screen_primary": "メイン画面",
    "overlay.offset_x": "水平オフセット",
    "overlay.offset_y": "垂直オフセット",
    "overlay.opacity": "不透明度",
    "overlay.scale": "拡大率",
    "overlay.on_top": "常に最前面",
    "overlay.click_through": "クリックを透過（操作の邪魔をしない）",
    "overlay.lock": "位置を固定",
    "overlay.theme": "テーマ",
    "overlay.theme.dark": "ダーク",
    "overlay.theme.light": "ライト",
    "overlay.theme.pink": "ピンク",
    "overlay.compact": "コンパクト表示（合計のみ）",
    "overlay.show_breakdown": "内訳を表示",
    "overlay.show_sparkline": "折れ線を表示",
    "overlay.show_stats": "統計行を表示",
    "overlay.follow_keyword": "ウィンドウタイトルのキーワード",
    "overlay.window_unsupported": "ウィンドウ追従は Windows のみ対応です。"
                                  "他の OS では画面の隅に固定されます。",
    "tray.enabled": "ステータスバー（トレイ）アイコンを表示",
    "tray.show_value": "アイコンに数値を描画する",

    "advanced.timeout": "リクエストのタイムアウト（ミリ秒）",
    "advanced.playurl_refresh": "再生アドレスの更新（秒）",
    "advanced.rtt_host": "RTT 計測用ホスト",
    "advanced.prefer_hls": "HLS を優先（より正確）",
    "advanced.auto_cdn": "最速の CDN ノードを自動で選ぶ",
    "advanced.auto_cdn_hint": "B站の同じ配信は複数の CDN ノードから配信されますが、プレイヤーは"
                              "最初の 1 つを使うだけで、最速より数十ミリ秒遅いこともよくあります。"
                              "有効にすると定期的に全ノードを比較し、明らかに速いもの（25ms 以上かつ"
                              "20% 以上速い）が見つかれば切り替えます。切り替えは最短 3 分間隔なので、"
                              "似た速度のノード同士で行ったり来たりはしません。"
                              "変わるのはこのアプリが計測するノードだけで、"
                              "あなたのプレイヤーが使うノードは変わりません。",
    "advanced.buffer_segments": "プレイヤーのバッファ分割数",
    "advanced.frames_in_flight": "コンポジターの先行フレーム数",
    "advanced.manual_offset": "モニターの入力遅延の補正（ミリ秒）",
    "advanced.include_display": "合計に表示遅延を含める",
    "advanced.csv": "サンプルを CSV に記録",
    "advanced.csv_hint": "設定フォルダー内の logs に保存され、自動でローテーションします。",
    "advanced.good": "緑のしきい値（ミリ秒）",
    "advanced.warn": "黄のしきい値（ミリ秒）",

    "about.body": "無料・オープンソース・ログイン不要。"
                  "B站の配信について、サーバーから PC、そして画面までの遅延を計測します。",
    "about.repo": "プロジェクトのページ",
    "about.version": "バージョン",

    "button.ok": "OK",
    "button.cancel": "キャンセル",
    "button.apply": "適用",
    "button.defaults": "既定に戻す",

    "notice.tray_missing": "システムトレイが使えないため、オーバーレイのみ表示します。",
    "notice.copied": "診断情報をクリップボードにコピーしました。",
    "notice.stall": "サーバーを見失いました——再試行しています…",
    "notice.spike": "遅延が急増：{value}（通常は約 {baseline}）",
    "notice.hidden_hint": "オーバーレイを隠しました。トレイアイコンから再表示できます。",

    "tray.tooltip": "{title}\n合計 {total}\n"
                    "ネットワーク {network} / 配信 {stream} / 表示 {display}\n{status}",
    "tray.tooltip_video": "{title}\n動画の合計 {total}\n"
                          "ネットワーク {network} / 再生開始 {stream} / 表示 {display}\n"
                          "帯域 {speed}\n{status}",
    "tray.tooltip_app": "{title}\n遅延 {total}\nサーバー {host}\n"
                        "接続 {conns}   ↓{down} ↑{up}\n{status}",

    "menu.history": "遅延の履歴…",
    "menu.report": "診断レポートを書き出す…",
    "history.title": "遅延の履歴",
    "history.range.1h": "1 時間",
    "history.range.6h": "6 時間",
    "history.range.24h": "24 時間",
    "history.range.all": "すべて",
    "history.export": "レポートを書き出す",
    "history.copy": "要約をコピー",
    "history.empty": "まだ履歴がありません。数分動かすとここに推移が出ます。",
    "history.group": "履歴",
    "history.enabled": "遅延の履歴を保存する（グラフとレポートに使用）",
    "history.keep": "保存する期間（時間）",
    "history.clear": "履歴を消去",
    "history.hint": "1 分あたり 1 行の要約（平均／最良／最悪／損失）だけを保存するので、"
                    "1 日で約 130 KB、終了しても失われません。"
                    "ファイルは設定フォルダーにあり、いつでも削除できます。",
    "history.auto_check": "カクついたら原因を自動で調べる",
    "history.auto_check_hint": "計測に失敗したり遅延が急増したときに、簡易版の区間診断"
                               "（ping 3 回、約 2 秒）をバックグラウンドで実行し、"
                               "その結論をその 1 分に記録します。"
                               "後から「昨夜 9 時は Wi-Fi が原因だった」と分かります。",

    "report.title": "ネットワーク診断レポート",
    "report.generated": "作成日時",
    "report.window": "集計範囲",
    "report.watching": "計測対象",
    "report.chart": "遅延の推移",
    "report.worst": "最も不安定だった時間帯",
    "report.segments": "区間ごとの診断",
    "report.extras": "その他の監視対象",
    "report.uptime": "応答率",
    "report.samples": "サンプル数",
    "report.stalls": "カクつき",
    "report.spikes": "遅延スパイク",
    "report.hours": "直近 {n} 時間",
    "report.all": "記録のすべて",
    "report.no_data": "まだ履歴が足りません",
    "report.legend_avg": "平均遅延",
    "report.legend_range": "1 分ごとの最良～最悪",
    "report.legend_marks": "カクつき／スパイク",
    "report.worst_line": "{time}　平均 {avg}、最大 {max}、カクつき・スパイク {stalls} 回",
    "report.no_trouble": "この期間はカクつきも遅延スパイクもありませんでした。",
    "report.privacy": "このレポートに含まれるのは遅延の数値、宅内ネットワークのアドレス、"
                      "計測したサーバーだけです。グローバル IP、アカウント、閲覧履歴、"
                      "Cookie は含まれません。",
    "report.saved": "レポートの保存先：",
    "report.copied": "要約をクリップボードにコピーしました",
    "report.failed": "レポートファイルを書き込めませんでした",
    "report.findings": "カクついたとき何が起きていたか",
    "report.switches": "自動で切り替えたノード",
    "report.switches_hint": "同じ配信は複数の CDN ノードから配信されますが、プレイヤーは最初の 1 つを"
                            "使うだけです。明らかに速いノードがあれば自動で切り替えます。",
    "report.auto_check": "自動チェック",

    "wizard.title": "初期設定",
    "wizard.welcome": "{app} へようこそ",
    "wizard.blurb": "3 つの質問に答えれば始められます。"
                    "ほかは妥当な既定値で、あとから設定でいつでも変更できます。",
    "wizard.watch": "① 何を計測しますか？",
    "wizard.watch.auto": "見ている B站の配信／動画（自動で追従）",
    "wizard.watch.app": "アプリ（ゲーム、通話、ブラウザーなど）",
    "wizard.watch.target": "サーバーアドレス",
    "wizard.watch.network": "まずはネットワーク全体だけ",
    "wizard.detail.app": "アプリ名",
    "wizard.detail.target": "アドレス",
    "wizard.hint.auto": "ブラウザーでも公式 PC クライアントでも動き、配信を変えれば自動で切り替わります。",
    "wizard.hint.app": "空欄なら今使っているアプリに追従します。あとから設定で一覧から選べます。",
    "wizard.hint.target": "例：8.8.8.8、ゲームサーバー、社内 VPN。",
    "wizard.place": "② オーバーレイをどこに置きますか？",
    "wizard.place.free": "自由に配置（自分で動かす）",
    "wizard.updates": "③ 更新を確認しますか？",
    "wizard.footer": "バージョン {version}　·　ログイン不要、利用データの収集もありません。",
    "wizard.start": "開始",

    "update.enabled": "新しいバージョンが出たら知らせる",
    "update.hint": "1 日 1 回まで GitHub に「最新のバージョン番号」を問い合わせます。"
                   "公開ページを 1 つ読むだけで、識別子も送らず、何も送信せず、"
                   "自動でダウンロードやインストールもしません。オフにしても他に影響はありません。",
    "update.available": "新しいバージョン {version} があります（現在 {current}）",
    "update.open": "ダウンロードページを開く",
    "update.skip": "このバージョンをスキップ",
    "update.later": "あとで",
    "update.none": "すでに最新バージョンです",
    "update.failed": "バージョン情報を取得できませんでした（オフライン？）",
    "menu.check_update": "更新を確認…",
    "update.group": "更新",

    # ----------------------------------------------------- before and after
    "menu.mark": "この瞬間を記録（設定を変えた）…",
    "compare.title": "変更は効きましたか",
    "compare.hint": "前後で同じ長さの期間を使い、両側にデータがある短いほうに合わせます。"
                    "一晩分の「前」と 5 分の「後」を比べてしまわないためです。",
    "compare.better": "改善しました（{value} 速くなりました）",
    "compare.worse": "むしろ悪化しました（{value} 遅くなりました）",
    "compare.same": "はっきりした差はありません",
    "compare.unclear": "データが足りず判断できません",
    "compare.span_min": "前後それぞれ {n} 分",
    "compare.span_hour": "前後それぞれ {n} 時間",
    "compare.dialog": "この瞬間を記録",
    "compare.prompt": "いま何を変えましたか？（例：5GHz に変更、DNS を 8.8.8.8 に、有線に変更）",
    "compare.marked": "記録しました。しばらく動かすと、レポートに前後の比較が出ます。",
    "compare.waiting": "「後」のデータを収集中",
    "history.markers": "記録した変更",

    # ------------------------------------------------------------ speed test
    "menu.speedtest": "回線速度を測る…",
    "speed.title": "速度テスト",
    "speed.host": "測定先",
    "speed.confirm": "帯域を使い切って {seconds} 秒ダウンロードします（最大 {megabytes} MB）。"
                     "その間は遅延が跳ね上がり、配信が止まることもあります——"
                     "それはこのテストのせいで、回線の異常ではありません。\n\n"
                     "視聴中の CDN からダウンロードします（何も見ていないときだけ公開測定点）。"
                     "開始しますか？",
    "speed.running": "測定中です。遅延の数値はしばらく無視してください…",
    "speed.result": "ダウンロード速度：{value}",
    "speed.failed": "速度テストを完了できませんでした",
    "speed.source_stream": "視聴中の CDN を測りました——実際に効いてくる経路です。",
    "speed.source_public": "何も視聴していないため、公開測定点（Cloudflare）を使いました。",
    "speed.cost": "{megabytes} MB を {seconds} 秒で使用しました。",
    "speed.short": "（TCP が全速に達する前に終わったため、低めに出ている可能性があります。）",
    "speed.marker": "速度テスト（遅延の急増はこれが原因）",
    "speed.budget": "測定時間（秒）",
    "speed.max_mb": "最大ダウンロード量（MB）",
    "speed.group": "速度テスト",
    "speed.hint": "どちらかの上限に達した時点で終わるので、"
                  "高速回線でも 1 GB を引き落とすことはありません。",
    "speed.tier.4k": "4K に十分（25 Mbps 以上）",
    "speed.tier.1080p60": "1080p60／高画質に十分",
    "speed.tier.1080p": "1080p に十分",
    "speed.tier.720p": "720p に十分",
    "speed.tier.low": "標準画質が限界で、高画質だと読み込みが入ります",
}

KO: dict = {
    "app.title": "LagScope",
    "app.short": "B站 지연",
    "app.short_generic": "지연",

    "menu.show_overlay": "오버레이 표시",
    "menu.lock": "위치 고정",
    "menu.click_through": "클릭 통과",
    "menu.pause": "모니터링 일시정지",
    "menu.resume": "모니터링 재개",
    "menu.reset_position": "오버레이 위치 초기화",
    "menu.settings": "설정…",
    "menu.copy_diag": "진단 정보 복사",
    "menu.open_config": "설정 폴더 열기",
    "menu.about": "정보",
    "menu.quit": "종료",

    "label.total": "총 지연",
    "label.network": "네트워크",
    "label.stream": "스트림",
    "label.display": "화면",
    "label.avg": "평균",
    "label.p95": "P95",
    "label.jitter": "지터",
    "label.range": "범위",
    "label.room": "방송",
    "label.video": "영상",
    "label.startup": "재생 시작",
    "label.speed": "대역폭",
    "label.latency": "지연",
    "label.connections": "연결 수",
    "label.app": "앱",
    "label.target": "대상",
    "label.down": "다운",
    "label.up": "업",
    "label.measured": "실측",
    "label.estimated": "추정",
    "label.auto": "자동",

    "status.no_room": "방송이 설정되지 않았습니다",
    "status.offline": "방송 중이 아닙니다",
    "status.connecting": "연결 중…",
    "status.paused": "일시정지됨",
    "status.error": "측정 실패",
    "status.network_only": "네트워크만 측정",
    "status.no_video": "영상이 설정되지 않았습니다",
    "status.no_app": "앱이 선택되지 않았습니다",
    "status.no_connections": "이 앱은 현재 네트워크 연결이 없습니다",
    "status.unreachable": "대상에 연결할 수 없습니다",
    "status.no_reply": "이 앱의 서버가 응답하지 않습니다 (ping이 차단된 것일 수 있습니다)",
    "status.detecting": "보고 있는 페이지를 확인하는 중…",

    "menu.diagnose": "네트워크 검사…",
    "diag.title": "네트워크 검사",
    "diag.running": "구간별로 측정 중…(약 10초)",
    "diag.you_router": "나 → 공유기",
    "diag.router_isp": "공유기 → 통신사",
    "diag.to_target": "→ 대상 서버",
    "diag.wifi": "Wi-Fi",
    "diag.loss": "손실",
    "diag.dns": "도메인 조회",
    "diag.no_gateway": "기본 게이트웨이를 찾을 수 없습니다",
    "diag.gateway_silent": "공유기가 ping에 응답하지 않습니다 (흔한 설정이며 고장이 아닙니다)",

    "verdict.ok": "네트워크는 정상으로 보입니다",
    "verdict.wifi": "지연 대부분이 나와 공유기 사이에서 발생하고 Wi-Fi 신호도 약합니다"
                    "——공유기에 가까이 가거나 유선으로 바꾸면 확실히 좋아집니다.",
    "verdict.home": "지연 대부분이 집 안 네트워크(나↔공유기)에서 발생합니다. "
                    "Wi-Fi나 공유기 부하를 확인하거나 유선으로 바꿔 보세요.",
    "verdict.isp": "집 안은 정상이고, 지연은 통신사 구간부터 커집니다. "
                   "직접 고칠 수 없는 부분이니 이 보고서를 고객센터에 보여주세요.",
    "verdict.server": "회선은 정상입니다. 지연은 서버까지의 거리나 경로 때문이며, "
                      "더 가까운 서버나 노드로 바꾸는 것이 가장 효과적입니다.",
    "verdict.loss": "패킷 손실이 있습니다——게임과 통화에는 지연보다 더 치명적이니 먼저 해결하세요.",
    "verdict.target_down": "대상이 응답하지 않습니다(ping을 막았거나 꺼져 있을 수 있음). "
                           "다만 내 네트워크 자체는 정상입니다.",
    "verdict.no_ping": "이 PC에서 사용할 수 있는 ping 명령을 찾지 못해 구간별 진단을 할 수 없습니다"
                       "(다른 기능은 정상 동작합니다).",
    "verdict.dns": "회선 자체는 정상이지만 도메인 조회가 느립니다——이것이 돌아와야 무엇이든 시작됩니다. "
                   "DNS를 8.8.8.8이나 1.1.1.1로 바꾸면 대개 바로 해결됩니다.",
    "verdict.unknown": "자료가 부족해 판단할 수 없습니다",

    "settings.title": "설정",
    "settings.tab.general": "일반",
    "settings.tab.overlay": "표시",
    "settings.tab.advanced": "고급",
    "settings.tab.about": "정보",

    "general.target": "측정 대상",
    "general.target.auto": "보고 있는 페이지를 자동으로 따라가기",
    "general.target.live": "방송을 직접 지정",
    "general.target.video": "영상을 직접 지정",
    "general.target.app": "아무 앱이나 (게임／통화／브라우저…)",
    "general.target.custom": "서버 주소 직접 입력",
    "general.app_name": "앱",
    "general.app_follow": "지금 쓰고 있는 앱을 자동으로 따라가기",
    "general.app_hint": "네트워크를 쓰는 프로그램을 고르면 그 앱이 연결한 서버를 찾아 지연을 계속 측정합니다. "
                        "UDP를 쓰는 게임은 자동으로 ping으로 전환합니다.",
    "general.app_refresh": "새로 고침",
    "general.target_host": "서버 주소",
    "general.target_port": "포트",
    "general.target_hint": "게임 서버, 회사 VPN, 8.8.8.8 등. TCP를 먼저 시도하고 안 되면 ping을 씁니다.",
    "general.netspeed": "PC 전체 업로드／다운로드 속도 표시",
    "general.video": "영상 ID 또는 URL",
    "general.video_hint": "BV 번호, av 번호 또는 https://www.bilibili.com/video/BV… "
                          "(파트 지정은 ?p=2).",
    "general.room": "방송 ID 또는 URL",
    "general.room_hint": "https://live.bilibili.com/123456 을 붙여넣거나 123456 만 입력해도 됩니다. "
                         "비워 두면 네트워크만 측정합니다.",
    "general.interval": "측정 간격 (밀리초)",
    "general.sample_window": "통계 구간 (샘플 수)",
    "general.language": "표시 언어",
    "general.language_auto": "시스템 설정 따르기",
    "general.autostart": "PC 시작 시 자동 실행",
    "general.autostart_unsupported": "이 환경에서는 자동 실행을 설정할 수 없습니다. README를 참고하세요.",
    "general.notify": "끊김·지연 급증 시 알림 표시",

    "detect.group": "자동 감지",
    "detect.history": "브라우저 방문 기록 읽기 (읽기 전용)",
    "detect.titles": "열려 있는 창 제목으로 판별 (Windows)",
    "detect.bridge": "유저스크립트 보고 받기 (가장 정확)",
    "detect.client": "공식 PC 클라이언트가 재생 중인 내용 읽기",
    "detect.clipboard": "복사한 링크 감지 (클라이언트용)",
    "detect.remember_titles": "창 제목과 방송의 짝을 기억하기",
    "detect.client_hint": "공식 PC 클라이언트에서는 클라이언트 자체 기록을 읽으므로 따로 할 일이 없습니다. "
                          "버전 차이로 읽지 못하더라도 '공유 → 링크 복사'를 누르면 바로 전환됩니다. "
                          "명령줄에 --detect-report를 붙이면 무엇을 읽었는지 확인할 수 있습니다.",
    "detect.bridge_port": "스크립트 수신 포트",
    "detect.window": "기록을 거슬러 볼 시간 (분)",
    "detect.follow_videos": "일반 영상도 따라가기",
    "detect.interval": "감지 간격 (초)",
    "detect.privacy": "감지는 이 PC 안에서만 이루어집니다. 기록 파일은 임시로 복사한 뒤 읽기 전용으로 열어 "
                      "bilibili.com 주소만 걸러냅니다. 원본에 쓰지 않고 어디에도 올리지 않으며 로그인도 "
                      "필요 없습니다. 원치 않으면 이 항목을 끄면 됩니다.",
    "detect.source.manual": "수동",
    "detect.source.clipboard": "복사한 링크",
    "detect.source.title": "창 제목",
    "detect.source.history": "방문 기록",
    "detect.source.history+title": "현재 탭",
    "detect.source.bridge": "스크립트",
    "menu.auto_detect": "보고 있는 페이지 따라가기",
    "menu.read_clipboard": "클립보드의 링크 읽기",
    "notice.clipboard_read": "클립보드를 읽었습니다. B站 링크였다면 바로 전환됩니다.",

    "menu.phone": "휴대폰 주소…",
    "extras.group": "함께 감시 (추가)",
    "extras.hint": "주 대상 외에 몇 개를 더 지켜보면 \"이것만 느린\" 것인지 \"회선 전체가 느린\" 것인지 "
                   "한눈에 알 수 있습니다. 최대 4개이며 번갈아 측정하므로 주 수치는 느려지지 않습니다.",
    "extras.add": "추가…",
    "extras.remove": "삭제",
    "extras.add_router": "＋공유기",
    "extras.add_dns": "＋DNS",
    "extras.router": "공유기",
    "extras.dns": "DNS",
    "extras.dialog": "감시 대상 추가",
    "extras.kind": "종류",
    "extras.kind.target": "서버 주소",
    "extras.kind.app": "앱",
    "extras.ident": "주소 또는 프로세스명",
    "extras.label": "표시 이름",
    "extras.full": "최대 4개까지만 추가할 수 있습니다",
    "extras.no_router": "공유기 주소를 찾을 수 없습니다",

    "web.group": "휴대폰 대시보드",
    "web.enabled": "같은 네트워크의 휴대폰에서도 볼 수 있게 하기",
    "web.port": "포트",
    "web.code": "접속 코드 (비우면 필요 없음)",
    "web.hint": "아래 주소를 휴대폰 브라우저에서 열면 똑같은 실시간 수치를 볼 수 있습니다. "
                "앱을 설치할 필요가 없고 iPhone과 Android 모두 같습니다. "
                "읽기 전용이라 휴대폰에서는 아무것도 바꿀 수 없고, 주소는 집 네트워크 안에서만 동작합니다.",
    "web.url_label": "휴대폰에서 열기:",
    "web.off": "꺼져 있습니다 (설정에서 켜세요)",
    "web.copied": "주소를 클립보드에 복사했습니다",

    "overlay.enabled": "오버레이 창 표시",
    "overlay.anchor": "위치 모드",
    "overlay.anchor.free": "자유 배치 (끌어서 이동)",
    "overlay.anchor.screen": "화면 모서리에 고정",
    "overlay.anchor.window": "B站 창을 따라가기",
    "overlay.corner": "모서리",
    "overlay.corner.top-left": "왼쪽 위",
    "overlay.corner.top-right": "오른쪽 위",
    "overlay.corner.bottom-left": "왼쪽 아래",
    "overlay.corner.bottom-right": "오른쪽 아래",
    "overlay.screen": "화면",
    "overlay.screen_primary": "주 화면",
    "overlay.offset_x": "가로 오프셋",
    "overlay.offset_y": "세로 오프셋",
    "overlay.opacity": "불투명도",
    "overlay.scale": "배율",
    "overlay.on_top": "항상 위에 표시",
    "overlay.click_through": "클릭 통과 (조작을 방해하지 않음)",
    "overlay.lock": "위치 고정",
    "overlay.theme": "테마",
    "overlay.theme.dark": "어두움",
    "overlay.theme.light": "밝음",
    "overlay.theme.pink": "핑크",
    "overlay.compact": "간단히 표시 (총 지연만)",
    "overlay.show_breakdown": "세부 항목 표시",
    "overlay.show_sparkline": "그래프 표시",
    "overlay.show_stats": "통계 줄 표시",
    "overlay.follow_keyword": "창 제목 키워드",
    "overlay.window_unsupported": "창 따라가기는 Windows에서만 동작하며, "
                                  "다른 운영체제에서는 화면 모서리 고정으로 대체됩니다.",
    "tray.enabled": "상태 표시줄(트레이) 아이콘 표시",
    "tray.show_value": "아이콘에 수치 표시",

    "advanced.timeout": "요청 제한 시간 (밀리초)",
    "advanced.playurl_refresh": "재생 주소 갱신 (초)",
    "advanced.rtt_host": "RTT 측정 호스트",
    "advanced.prefer_hls": "HLS 우선 사용 (더 정확)",
    "advanced.auto_cdn": "가장 빠른 CDN 노드 자동 선택",
    "advanced.auto_cdn_hint": "B站의 같은 방송은 여러 CDN 노드에서 제공되지만 플레이어는 첫 번째 것만 "
                              "쓰기 때문에 가장 빠른 노드보다 수십 밀리초 느린 경우가 흔합니다. "
                              "켜 두면 주기적으로 모든 노드를 비교해 확실히 빠른 노드(25ms 이상이면서 "
                              "20% 이상 빠름)를 찾으면 전환합니다. 전환은 최소 3분 간격이라 비슷한 속도의 "
                              "노드끼리 오가지 않습니다. 바뀌는 것은 이 프로그램이 측정하는 노드뿐이고 "
                              "재생 중인 플레이어의 노드는 바뀌지 않습니다.",
    "advanced.buffer_segments": "플레이어 버퍼 조각 수",
    "advanced.frames_in_flight": "컴포지터 대기 프레임 수",
    "advanced.manual_offset": "모니터 입력 지연 보정 (밀리초)",
    "advanced.include_display": "총 지연에 화면 지연 포함",
    "advanced.csv": "샘플을 CSV로 기록",
    "advanced.csv_hint": "설정 폴더 안 logs에 저장되며 자동으로 순환됩니다.",
    "advanced.good": "초록 임계값 (밀리초)",
    "advanced.warn": "노랑 임계값 (밀리초)",

    "about.body": "무료·오픈소스·로그인 불필요. "
                  "B站 방송의 서버에서 PC를 거쳐 화면까지의 지연을 측정합니다.",
    "about.repo": "프로젝트 페이지",
    "about.version": "버전",

    "button.ok": "확인",
    "button.cancel": "취소",
    "button.apply": "적용",
    "button.defaults": "기본값으로",

    "notice.tray_missing": "시스템 트레이를 쓸 수 없어 오버레이만 표시합니다.",
    "notice.copied": "진단 정보를 클립보드에 복사했습니다.",
    "notice.stall": "서버를 놓쳤습니다 — 다시 시도하는 중…",
    "notice.spike": "지연 급증: {value} (평소 약 {baseline})",
    "notice.hidden_hint": "오버레이를 숨겼습니다. 트레이 아이콘에서 다시 열 수 있습니다.",

    "tray.tooltip": "{title}\n총 지연 {total}\n"
                    "네트워크 {network} / 스트림 {stream} / 화면 {display}\n{status}",
    "tray.tooltip_video": "{title}\n영상 총 지연 {total}\n"
                          "네트워크 {network} / 재생 시작 {stream} / 화면 {display}\n"
                          "대역폭 {speed}\n{status}",
    "tray.tooltip_app": "{title}\n지연 {total}\n서버 {host}\n"
                        "연결 {conns}   ↓{down} ↑{up}\n{status}",

    "menu.history": "지연 기록…",
    "menu.report": "진단 보고서 내보내기…",
    "history.title": "지연 기록",
    "history.range.1h": "1시간",
    "history.range.6h": "6시간",
    "history.range.24h": "24시간",
    "history.range.all": "전체",
    "history.export": "보고서 내보내기",
    "history.copy": "요약 복사",
    "history.empty": "아직 기록이 없습니다. 몇 분만 두면 여기에 추이가 나타납니다.",
    "history.group": "기록",
    "history.enabled": "지연 기록 저장 (그래프와 보고서에 사용)",
    "history.keep": "보관 기간 (시간)",
    "history.clear": "기록 지우기",
    "history.hint": "1분마다 요약 한 줄(평균／최선／최악／손실)만 저장하므로 하루에 약 130 KB이고 "
                    "프로그램을 종료해도 남습니다. 파일은 설정 폴더에 있으며 언제든 지울 수 있습니다.",
    "history.auto_check": "끊길 때 원인을 자동으로 확인",
    "history.auto_check_hint": "측정이 실패하거나 지연이 급증하면 간소화한 구간 진단"
                               "(ping 3회, 약 2초)을 백그라운드에서 실행해 그 결론을 해당 1분에 "
                               "기록합니다. 나중에 \"어젯밤 9시는 Wi-Fi 문제였다\"까지 알 수 있습니다.",

    "report.title": "네트워크 진단 보고서",
    "report.generated": "생성 시각",
    "report.window": "집계 범위",
    "report.watching": "측정 대상",
    "report.chart": "지연 추이",
    "report.worst": "가장 불안정했던 시간대",
    "report.segments": "구간별 진단",
    "report.extras": "그 밖의 감시 대상",
    "report.uptime": "응답률",
    "report.samples": "샘플 수",
    "report.stalls": "끊김",
    "report.spikes": "지연 급증",
    "report.hours": "최근 {n}시간",
    "report.all": "기록 전체",
    "report.no_data": "아직 기록이 부족합니다",
    "report.legend_avg": "평균 지연",
    "report.legend_range": "1분마다 최선～최악",
    "report.legend_marks": "끊김／급증",
    "report.worst_line": "{time}　평균 {avg}, 최대 {max}, 끊김·급증 {stalls}회",
    "report.no_trouble": "이 기간에는 끊김도 지연 급증도 없었습니다.",
    "report.privacy": "이 보고서에는 지연 수치, 집 안 네트워크 주소, 측정한 서버만 들어 있습니다. "
                      "공인 IP, 계정, 방문 기록, 쿠키는 포함되지 않습니다.",
    "report.saved": "보고서 저장 위치:",
    "report.copied": "요약을 클립보드에 복사했습니다",
    "report.failed": "보고서 파일을 쓸 수 없습니다",
    "report.findings": "끊겼을 때 무슨 일이 있었나",
    "report.switches": "자동으로 바꾼 노드",
    "report.switches_hint": "같은 방송이 여러 CDN 노드에서 제공되지만 플레이어는 첫 번째 것만 씁니다. "
                            "확실히 더 빠른 노드가 있으면 자동으로 전환합니다.",
    "report.auto_check": "자동 확인",

    "wizard.title": "초기 설정",
    "wizard.welcome": "{app}에 오신 것을 환영합니다",
    "wizard.blurb": "세 가지만 답하면 바로 시작합니다. "
                    "나머지는 적당한 기본값이며 나중에 설정에서 언제든 바꿀 수 있습니다.",
    "wizard.watch": "① 무엇을 측정할까요?",
    "wizard.watch.auto": "내가 보고 있는 B站 방송／영상 (자동으로 따라감)",
    "wizard.watch.app": "어떤 앱 (게임, 음성, 브라우저 등)",
    "wizard.watch.target": "서버 주소",
    "wizard.watch.network": "우선 네트워크 전체만",
    "wizard.detail.app": "앱 이름",
    "wizard.detail.target": "주소",
    "wizard.hint.auto": "브라우저와 공식 PC 클라이언트 모두 지원하며, 방송을 바꾸면 알아서 따라갑니다.",
    "wizard.hint.app": "비워 두면 지금 쓰고 있는 앱을 따라갑니다. 나중에 설정에서 목록으로 고를 수 있습니다.",
    "wizard.hint.target": "예: 8.8.8.8, 게임 서버, 회사 VPN.",
    "wizard.place": "② 오버레이를 어디에 둘까요?",
    "wizard.place.free": "자유 배치 (직접 옮김)",
    "wizard.updates": "③ 업데이트를 확인할까요?",
    "wizard.footer": "버전 {version}　·　로그인이 필요 없고 사용 데이터를 수집하지 않습니다.",
    "wizard.start": "시작하기",

    "update.enabled": "새 버전이 나오면 알려주기",
    "update.hint": "하루에 최대 한 번 GitHub에 \"최신 버전 번호\"를 물어봅니다. 공개 페이지 하나를 "
                   "읽을 뿐이며 식별자도 보내지 않고, 아무것도 올리지 않으며, 자동으로 내려받거나 "
                   "설치하지도 않습니다. 꺼도 다른 기능에는 영향이 없습니다.",
    "update.available": "새 버전 {version}이(가) 있습니다 (현재 {current})",
    "update.open": "다운로드 페이지 열기",
    "update.skip": "이 버전 건너뛰기",
    "update.later": "나중에",
    "update.none": "이미 최신 버전입니다",
    "update.failed": "버전 정보를 가져오지 못했습니다 (오프라인?)",
    "menu.check_update": "업데이트 확인…",
    "update.group": "업데이트",

    # ----------------------------------------------------- before and after
    "menu.mark": "이 순간 표시 (설정을 바꿨음)…",
    "compare.title": "바꾼 게 효과가 있었나",
    "compare.hint": "앞뒤로 같은 길이의 기간을 쓰고, 양쪽 모두 자료가 있는 짧은 쪽에 맞춥니다. "
                    "하룻밤치 '이전'과 5분치 '이후'를 비교하지 않기 위해서입니다.",
    "compare.better": "좋아졌습니다 ({value} 빨라짐)",
    "compare.worse": "오히려 나빠졌습니다 ({value} 느려짐)",
    "compare.same": "뚜렷한 차이가 없습니다",
    "compare.unclear": "자료가 부족해 판단할 수 없습니다",
    "compare.span_min": "앞뒤 각 {n}분",
    "compare.span_hour": "앞뒤 각 {n}시간",
    "compare.dialog": "이 순간 표시",
    "compare.prompt": "방금 무엇을 바꿨나요? (예: 5GHz로 변경, DNS를 8.8.8.8로, 유선으로 교체)",
    "compare.marked": "표시했습니다. 조금 더 두면 보고서에 전후 비교가 나타납니다.",
    "compare.waiting": "'이후' 자료를 모으는 중",
    "history.markers": "표시한 변경",

    # ------------------------------------------------------------ speed test
    "menu.speedtest": "회선 속도 측정…",
    "speed.title": "속도 측정",
    "speed.host": "측정 대상",
    "speed.confirm": "대역폭을 모두 써서 {seconds}초 동안 내려받습니다(최대 {megabytes} MB). "
                     "그동안 지연이 치솟고 방송이 끊길 수 있는데, 이 측정 때문이지 "
                     "회선에 문제가 생긴 것이 아닙니다.\n\n"
                     "보고 있는 CDN에서 내려받습니다(아무것도 보고 있지 않을 때만 공개 측정 서버). "
                     "시작할까요?",
    "speed.running": "측정 중입니다. 잠시 지연 수치는 무시하세요…",
    "speed.result": "다운로드 속도: {value}",
    "speed.failed": "속도 측정을 끝내지 못했습니다",
    "speed.source_stream": "보고 있는 CDN을 측정했습니다 — 실제로 영향을 주는 경로입니다.",
    "speed.source_public": "보고 있는 것이 없어 공개 측정 서버(Cloudflare)를 썼습니다.",
    "speed.cost": "{megabytes} MB를 {seconds}초 동안 사용했습니다.",
    "speed.short": "(TCP가 최고 속도에 이르기 전에 끝나 실제보다 낮게 나왔을 수 있습니다.)",
    "speed.marker": "속도 측정 (지연 급증은 이 때문)",
    "speed.budget": "측정 시간(초)",
    "speed.max_mb": "최대 다운로드(MB)",
    "speed.group": "속도 측정",
    "speed.hint": "두 상한 중 먼저 도달하는 쪽에서 멈추므로, "
                  "기가 회선이라도 1 GB를 끌어내리지 않습니다.",
    "speed.tier.4k": "4K에 충분 (25 Mbps 이상)",
    "speed.tier.1080p60": "1080p60／고화질에 충분",
    "speed.tier.1080p": "1080p에 충분",
    "speed.tier.720p": "720p에 충분",
    "speed.tier.low": "표준 화질까지만 가능하고, 고화질은 버퍼링이 생깁니다",
}

OVERLAYS: dict = {"ja": JA, "ko": KO}
