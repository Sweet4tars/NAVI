from __future__ import annotations

from copy import deepcopy
import re


CASE_CITY_COORDS = {
    "宜宾": (104.6417, 28.7513),
    "西昌": (102.2644, 27.8945),
    "丽江": (100.2278, 26.8550),
    "大理": (100.2676, 25.6075),
    "攀枝花": (101.7185, 26.5823),
}

CASE_ZONE_TAGS = {
    "宜宾": ["接人方便", "次日出城快", "夜里好停车"],
    "西昌": ["去邛海方便", "吃饭选择多", "出城效率高"],
    "丽江": ["停车更友好", "小吃密度高", "打车步行都方便"],
    "大理": ["古城外围更安静", "停车更稳", "吃饭更实用"],
    "攀枝花": ["城区最成熟", "补给方便", "返程最好发车"],
}


CASE_ZONE_LAYOUTS = {
    "宜宾": {
        "width": 220,
        "height": 140,
        "primary": {"x": 64, "y": 56, "label": "西站"},
        "secondary": {"x": 154, "y": 84, "label": "合江门"},
        "poi": {"x": 170, "y": 52, "label": "大观楼"},
        "food": {"x": 146, "y": 106, "label": "老馆子"},
        "parking": {"x": 76, "y": 92, "label": "停车"},
    },
    "西昌": {
        "width": 220,
        "height": 140,
        "primary": {"x": 92, "y": 72, "label": "集散中心"},
        "secondary": {"x": 150, "y": 42, "label": "建昌古城"},
        "poi": {"x": 168, "y": 96, "label": "邛海"},
        "food": {"x": 118, "y": 104, "label": "烧烤"},
        "parking": {"x": 68, "y": 96, "label": "停车"},
    },
    "丽江": {
        "width": 220,
        "height": 140,
        "primary": {"x": 94, "y": 88, "label": "南门"},
        "secondary": {"x": 154, "y": 54, "label": "大水车"},
        "poi": {"x": 164, "y": 86, "label": "古城"},
        "food": {"x": 110, "y": 110, "label": "忠义市场"},
        "parking": {"x": 62, "y": 92, "label": "停车"},
    },
    "大理": {
        "width": 220,
        "height": 140,
        "primary": {"x": 86, "y": 62, "label": "古城南门"},
        "secondary": {"x": 150, "y": 96, "label": "大理站"},
        "poi": {"x": 154, "y": 52, "label": "古城"},
        "food": {"x": 92, "y": 98, "label": "小吃"},
        "parking": {"x": 58, "y": 74, "label": "停车"},
    },
    "攀枝花": {
        "width": 220,
        "height": 140,
        "primary": {"x": 100, "y": 66, "label": "炳草岗"},
        "secondary": {"x": 148, "y": 86, "label": "商业带"},
        "poi": {"x": 164, "y": 52, "label": "主城区"},
        "food": {"x": 110, "y": 104, "label": "吃饭"},
        "parking": {"x": 70, "y": 88, "label": "停车"},
    },
}

CASE_ZONE_GEO = {
    "宜宾": {
        "primary": (104.626, 28.798),
        "secondary": (104.650, 28.767),
        "poi": (104.648, 28.774),
        "food": (104.646, 28.762),
        "parking": (104.628, 28.790),
    },
    "西昌": {
        "primary": (102.276, 27.887),
        "secondary": (102.268, 27.901),
        "poi": (102.295, 27.865),
        "food": (102.284, 27.881),
        "parking": (102.273, 27.879),
    },
    "丽江": {
        "primary": (100.230, 26.865),
        "secondary": (100.239, 26.877),
        "poi": (100.238, 26.872),
        "food": (100.228, 26.860),
        "parking": (100.224, 26.866),
    },
    "大理": {
        "primary": (100.164, 25.694),
        "secondary": (100.301, 25.612),
        "poi": (100.170, 25.700),
        "food": (100.162, 25.688),
        "parking": (100.156, 25.692),
    },
    "攀枝花": {
        "primary": (101.718, 26.585),
        "secondary": (101.732, 26.577),
        "poi": (101.744, 26.593),
        "food": (101.724, 26.579),
        "parking": (101.710, 26.580),
    },
}


CASE_STUDIES = {
    "yunnan-roadtrip-yibin-loop": {
        "id": "yunnan-roadtrip-yibin-loop",
        "title": "宜宾集合 · 西昌丽江大理攀枝花学生向自驾线",
        "subtitle": "位置优先、预算优先、五一 5 晚 6 天",
        "date_range": "2026-04-30 ~ 2026-05-05",
        "travelers": "4 人，2 间房，宜宾发车",
        "transport_mode": "自驾",
        "budget_target": "酒店尽量控制在 ¥160-250/间/晚",
        "summary": (
            "这版主线按 宜宾 -> 西昌 -> 丽江 -> 大理 -> 攀枝花 -> 宜宾 收敛，"
            "住宿先定位置，再在该位置里选最有性价比、适合学生住的酒店或民宿。"
        ),
        "route_nodes": ["宜宾", "西昌", "丽江", "大理", "攀枝花", "宜宾"],
        "route_legs": [
            {
                "from": "宜宾",
                "to": "西昌",
                "distance": "约 440km",
                "drive_time": "约 6.5-7h",
                "intensity": "中高",
                "note": "第一天长路，但还能承受；尽量在西昌只做轻松活动。",
            },
            {
                "from": "西昌",
                "to": "丽江",
                "distance": "约 460km",
                "drive_time": "约 7.5-8.5h",
                "intensity": "高",
                "note": "全程最累段之一，丽江当晚不要再叠加重景点。",
            },
            {
                "from": "丽江",
                "to": "大理",
                "distance": "约 180km",
                "drive_time": "约 2.5-3h",
                "intensity": "中",
                "note": "适合作为缓冲日，兼顾丽江收尾和大理落地。",
            },
            {
                "from": "大理",
                "to": "攀枝花",
                "distance": "约 360km",
                "drive_time": "约 5.5-6.5h",
                "intensity": "中高",
                "note": "返程开始收口，不建议再叠加环海深度游。",
            },
            {
                "from": "攀枝花",
                "to": "宜宾",
                "distance": "约 540km",
                "drive_time": "约 8-9h",
                "intensity": "高",
                "note": "返程最长日之一，晚餐后不建议再夜开回成都或重庆。",
            },
        ],
        "stay_recommendations": [
            {
                "city": "宜宾",
                "priority_zone": "宜宾西站周边",
                "secondary_zone": "合江门 / 大观楼",
                "zone_reason": "更适合接人、停车和第二天直接出城；如果更想集合夜吃好一点，再退到合江门。",
                "student_fit": "高",
                "hotel_candidates": [
                    {
                        "name": "泥木·SKY CITY HOTEL(宜宾站西站店)",
                        "type": "酒店",
                        "price": "约 ¥178/晚",
                        "reason": "离西站近，最适合集合夜和次日一早直接发车。",
                        "source_url": "https://m.ctrip.com/webapp/hotels/xtaro/detail?hotelid=122053547",
                    },
                    {
                        "name": "宜宾希程酒店(宜宾高铁西站店)",
                        "type": "酒店",
                        "price": "建议下单前复核",
                        "reason": "位置型备选，适合在前两家无房时兜底。",
                        "source_url": "https://m.ctrip.com/html5/hotel/hoteldetail/95268346.html",
                    },
                    {
                        "name": "恒朵酒店(翠屏山景区合江门店)",
                        "type": "酒店",
                        "price": "约 ¥199/晚",
                        "reason": "如果更看重集合夜吃饭方便，这家比西站周边更适合。",
                        "source_url": "https://m.ctrip.com/webapp/hotels/xtaro/detail?hotelid=128130341",
                    },
                ],
            },
            {
                "city": "西昌",
                "priority_zone": "航天大道 / 旅游集散中心",
                "secondary_zone": "建昌古城外围",
                "zone_reason": "这片对自驾最友好，去邛海、月亮湖和市区吃饭都不算远，停车和次日出城效率更高。",
                "student_fit": "高",
                "hotel_candidates": [
                    {
                        "name": "7天优品Premium酒店(西昌航天大道旅游集散中心店)",
                        "type": "酒店",
                        "price": "预算友好",
                        "reason": "最符合“便宜、稳、停车省心”的学生向需求。",
                        "source_url": "https://m.ctrip.com/html5/hotel/hoteldetail/4496316.html",
                    },
                    {
                        "name": "汉庭酒店(西昌航天大道月亮湖湿地公园店)",
                        "type": "酒店",
                        "price": "预算友好",
                        "reason": "标准化体验更稳，适合不想住本地小酒店的情况。",
                        "source_url": "https://hotels.ctrip.com/hotel/97345330.html",
                    },
                    {
                        "name": "西昌印象酒店（西昌旅游集散中心店）",
                        "type": "酒店",
                        "price": "中高，建议尽早订",
                        "reason": "想在预算之上多一点舒适度时可选。",
                        "source_url": "https://gs.ctrip.com/html5/you/travels/592/4162726.html",
                    },
                ],
            },
            {
                "city": "丽江",
                "priority_zone": "古城南门 / 忠义市场",
                "secondary_zone": "大水车外围 / 机场大巴站",
                "zone_reason": "古城南门对自驾最友好，吃饭便宜、停车方便、打车和步行都比古城深处强。",
                "student_fit": "高",
                "hotel_candidates": [
                    {
                        "name": "汉庭酒店(丽江古城南门店)",
                        "type": "酒店",
                        "price": "预算友好",
                        "reason": "位置就是它的最大优势，比住进古城巷子里更省心。",
                        "source_url": "https://my.trip.com/hotels/lijiang-hotel-detail-116697887/han-ting-jiu-dian/photo.html",
                    },
                    {
                        "name": "7天优品酒店(丽江古城大水车机场大巴站店)",
                        "type": "酒店",
                        "price": "预算友好",
                        "reason": "如果想步行去古城更直接，又不想住太贵，这家是稳妥方案。",
                        "source_url": "https://m.ctrip.com/html5/hotel/hoteldetail/1510526.html",
                    },
                    {
                        "name": "星程酒店(丽江古城大水车店)",
                        "type": "酒店",
                        "price": "中高，建议尽早锁房",
                        "reason": "更适合想兼顾古城步行便利和连锁稳定感的人。",
                        "source_url": "https://hotels.corporatetravel.ctrip.com/hotels/133414471.html",
                    },
                ],
            },
            {
                "city": "大理",
                "priority_zone": "古城南门 / 苍山门外围",
                "secondary_zone": "大理站周边",
                "zone_reason": "古城外围比古城核心区更适合拖箱子和停车，周边小吃和市场密度也更适合学生预算。",
                "student_fit": "高",
                "hotel_candidates": [
                    {
                        "name": "汉庭酒店(大理古城店)",
                        "type": "酒店",
                        "price": "预算友好",
                        "reason": "这版大理不追海景，追的是预算、位置和不折腾。",
                        "source_url": "https://m.ctrip.com/html5/hotel/hoteldetail/116954948.html",
                    },
                    {
                        "name": "7天酒店(大理洱海公园店)",
                        "type": "酒店",
                        "price": "预算友好",
                        "reason": "如果房价上浮，这是更容易压住预算的回退选项。",
                        "source_url": "https://www.ehotelsreviews.com/7days-inn-dali-erhai-park-branch-6447983-zh",
                    },
                    {
                        "name": "大理芷兰庭客栈",
                        "type": "民宿 / 客栈",
                        "price": "中高",
                        "reason": "如果还是想保留一点大理客栈感，这类预算型客栈更合适。",
                        "source_url": "https://www.chinaholiday.com/cn/city_1322/440144.html",
                    },
                ],
            },
            {
                "city": "攀枝花",
                "priority_zone": "东区炳草岗 / 五十四转盘",
                "secondary_zone": "东区主城区商业带",
                "zone_reason": "攀枝花最成熟的城区就在这片，找吃的、找停车、买补给和第二天返程都最省心。",
                "student_fit": "高",
                "hotel_candidates": [
                    {
                        "name": "7天酒店(攀枝花五十四转盘中心店)",
                        "type": "酒店",
                        "price": "预算友好",
                        "reason": "返程夜更看重省心和位置，这种经济连锁很合适。",
                        "source_url": "https://mm.ctrip.com/webapp/hotel/panzhihua1097/h1638?seoRedirect=1",
                    },
                    {
                        "name": "新视窗酒店连锁(攀枝花凤凰店)",
                        "type": "酒店",
                        "price": "约 ¥236/晚",
                        "reason": "明确更贴近预算，是返程夜很实用的性价比选项。",
                        "source_url": "https://www.chinaholiday.com/cn/city_1247/39586.html",
                    },
                    {
                        "name": "宜尚酒店(攀枝花东区银江湖公园店)",
                        "type": "酒店",
                        "price": "中，需复核",
                        "reason": "如果能接受最后一晚稍高一点预算，住感会更好。",
                        "source_url": "https://m.ctrip.com/html5/hotel/hoteldetail/85497137.html",
                    },
                ],
            },
        ],
        "days": [
            {
                "day_index": 0,
                "date": "2026-04-30",
                "title": "宜宾集合夜",
                "intensity": "低",
                "base_city": "宜宾",
                "priority_zone": "宜宾西站周边",
                "schedule": [
                    "18:30-21:00 成都、重庆方向成员陆续到宜宾",
                    "21:00-22:00 统一晚饭，检查车况，安排第二天主驾 / 副驾",
                    "22:30 尽量早休息",
                ],
                "hotel_candidates": [],
                "meals": [
                    {
                        "slot": "晚餐",
                        "candidates": [
                            {
                                "name": "正宗知味轩李庄白肉(旧州路店)",
                                "source": "大众点评",
                                "reason": "宜宾最有辨识度的一类地方菜，适合作为开场饭。",
                                "url": "https://www.dianping.com/shop/3006910/photos",
                            },
                            {
                                "name": "老字号临江园餐饮店",
                                "source": "大众点评",
                                "reason": "更适合围桌正餐和集合夜聚餐。",
                                "url": "https://www.dianping.com/shop/l8otVnY4o9zA7TCF",
                            },
                        ],
                    }
                ],
            },
            {
                "day_index": 1,
                "date": "2026-05-01",
                "title": "宜宾 -> 西昌",
                "intensity": "中高",
                "base_city": "西昌",
                "priority_zone": "航天大道 / 旅游集散中心",
                "schedule": [
                    "07:30 宜宾出发",
                    "10:00 途中第一次休息",
                    "13:00-14:00 抵达西昌后午餐",
                    "15:00-16:00 办理入住",
                    "17:00-19:00 邛海边或月亮湖湿地周边轻松散步",
                    "19:30-21:00 西昌晚餐",
                ],
                "hotel_candidates": [],
                "meals": [
                    {
                        "slot": "早餐",
                        "candidates": [
                            {
                                "name": "炖鸡面(南街店)",
                                "source": "大众点评",
                                "reason": "出发日早餐重点是热、快、稳。",
                                "url": "https://www.dianping.com/shop/3656572/photos/album",
                            },
                            {
                                "name": "宜宾燃面非遗传承店",
                                "source": "大众点评",
                                "reason": "离开宜宾前补一次最有代表性的本地小吃。",
                                "url": "https://www.dianping.com/shop/k9ht6vbwv2IRK5mQ",
                            },
                        ],
                    },
                    {
                        "slot": "午餐",
                        "candidates": [
                            {
                                "name": "会理名小吃(南坛路店)",
                                "source": "大众点评",
                                "reason": "长途第一天中午更适合吃快而稳的小吃。",
                                "url": "https://www.dianping.com/shop/l5VyErby2WZtxSdr",
                            },
                            {
                                "name": "正宗会理鸡火丝(龙眼井店)",
                                "source": "大众点评城市页",
                                "reason": "地方感明确，适合稳住胃口。",
                                "url": "https://www.dianping.com/xichang",
                            },
                        ],
                    },
                    {
                        "slot": "晚餐",
                        "candidates": [
                            {
                                "name": "醉南山·西昌火盆烧烤(唐园店)",
                                "source": "大众点评",
                                "reason": "西昌最值得专门吃一顿的就是火盆烧烤。",
                                "url": "https://www.dianping.com/shop/l1ihbiBzMgmx4cbl",
                            },
                            {
                                "name": "黑妹冕宁火盆烧烤(西昌店)",
                                "source": "大众点评",
                                "reason": "也是地方辨识度很强的稳定备选。",
                                "url": "https://www.dianping.com/shop/l4s7J7RnBaaWOuDs",
                            },
                        ],
                    },
                ],
            },
            {
                "day_index": 2,
                "date": "2026-05-02",
                "title": "西昌 -> 丽江",
                "intensity": "高",
                "base_city": "丽江",
                "priority_zone": "古城南门 / 忠义市场",
                "schedule": [
                    "08:00 西昌早餐",
                    "09:00 西昌出发",
                    "12:30-13:30 途中午餐",
                    "17:00-18:30 抵达丽江，办理入住",
                    "19:30-21:30 丽江古城晚餐 + 轻松散步",
                ],
                "hotel_candidates": [],
                "meals": [
                    {
                        "slot": "早餐",
                        "candidates": [
                            {
                                "name": "熊氏牛羊杂粉(龙眼井总店)",
                                "source": "大众点评城市页",
                                "reason": "西昌早餐更适合热汤粉杂，抗饿且适合长车程。",
                                "url": "https://www.dianping.com/xichang",
                            },
                            {
                                "name": "正宗会理鸡火丝(龙眼井店)",
                                "source": "大众点评城市页",
                                "reason": "不想吃粉杂时更清爽的地方早餐备选。",
                                "url": "https://www.dianping.com/xichang",
                            },
                        ],
                    },
                    {
                        "slot": "午餐",
                        "candidates": [
                            {
                                "name": "渣渣米线",
                                "source": "大众点评丽江页",
                                "reason": "赶路日落地吃米线最稳，出餐快、接受度高。",
                                "url": "https://www.dianping.com/lijiang",
                            },
                            {
                                "name": "勺子米线",
                                "source": "大众点评丽江页",
                                "reason": "同类稳妥备选，不会把晚上状态吃没。",
                                "url": "https://www.dianping.com/lijiang",
                            },
                        ],
                    },
                    {
                        "slot": "晚餐",
                        "candidates": [
                            {
                                "name": "阿婆腊排骨火锅(丽江古城店)",
                                "source": "大众点评丽江页",
                                "reason": "丽江最有代表性的多人锅物之一。",
                                "url": "https://www.dianping.com/lijiang",
                            },
                            {
                                "name": "勇勇清真牛肉馆",
                                "source": "大众点评丽江页",
                                "reason": "如果不想吃锅物，这类高热度本地馆子更合适。",
                                "url": "https://www.dianping.com/lijiang",
                            },
                        ],
                    },
                ],
            },
            {
                "day_index": 3,
                "date": "2026-05-03",
                "title": "丽江 -> 大理",
                "intensity": "中",
                "base_city": "大理",
                "priority_zone": "古城南门 / 苍山门外围",
                "schedule": [
                    "08:30 早餐",
                    "10:00-12:00 丽江古城 / 大水车一带轻松收尾",
                    "12:30-13:30 丽江午餐",
                    "14:30 出发去大理",
                    "17:00-18:00 抵达大理入住",
                    "19:00-21:00 大理晚餐 + 古城夜逛",
                ],
                "hotel_candidates": [],
                "meals": [
                    {
                        "slot": "早餐",
                        "candidates": [
                            {
                                "name": "渣渣米线",
                                "source": "大众点评丽江页",
                                "reason": "丽江离开前早餐继续选热食最稳。",
                                "url": "https://www.dianping.com/lijiang",
                            },
                            {
                                "name": "勺子米线",
                                "source": "大众点评丽江页",
                                "reason": "同样属于高接受度早餐型选择。",
                                "url": "https://www.dianping.com/lijiang",
                            },
                        ],
                    },
                    {
                        "slot": "午餐",
                        "candidates": [
                            {
                                "name": "勇勇清真牛肉馆",
                                "source": "大众点评丽江页",
                                "reason": "比锅物更适合作为转场日前的午餐。",
                                "url": "https://www.dianping.com/lijiang",
                            },
                            {
                                "name": "阿婆腊排骨火锅(丽江古城店)",
                                "source": "大众点评丽江页",
                                "reason": "想在离开丽江前把标志性味道吃完整时可选。",
                                "url": "https://www.dianping.com/lijiang",
                            },
                        ],
                    },
                    {
                        "slot": "晚餐",
                        "candidates": [
                            {
                                "name": "大理段公子·大理古国文化体验店",
                                "source": "大众点评精选",
                                "reason": "四人同行吃白族特色菜很合适。",
                                "url": "https://m.dianping.com/discovery/599763534",
                            },
                            {
                                "name": "我在大理等你·方舟胖子厨房",
                                "source": "大众点评精选",
                                "reason": "第一次到大理不想踩雷的稳妥选择。",
                                "url": "https://m.dianping.com/discovery/865519170",
                            },
                        ],
                    },
                ],
            },
            {
                "day_index": 4,
                "date": "2026-05-04",
                "title": "大理 -> 攀枝花",
                "intensity": "中高",
                "base_city": "攀枝花",
                "priority_zone": "东区炳草岗 / 五十四转盘",
                "schedule": [
                    "08:30 早餐",
                    "10:00-12:00 大理古城或洱海边选 1 个点轻松逛",
                    "12:30-13:30 大理午餐",
                    "14:30 出发去攀枝花",
                    "19:00-20:00 抵达攀枝花，入住",
                    "20:00-21:30 攀枝花晚餐",
                ],
                "hotel_candidates": [],
                "meals": [
                    {
                        "slot": "早餐",
                        "candidates": [
                            {
                                "name": "酥香园和尚喜洲破酥粑粑",
                                "source": "大众点评精选",
                                "reason": "离开大理前再吃一次地方早点，记忆点更完整。",
                                "url": "https://m.dianping.com/discovery/599763534",
                            },
                            {
                                "name": "桥香园过桥米线",
                                "source": "大众点评",
                                "reason": "不想再吃粑粑时的稳妥早餐替代。",
                                "url": "https://www.dianping.com/shop/97940560/photos",
                            },
                        ],
                    },
                    {
                        "slot": "午餐",
                        "candidates": [
                            {
                                "name": "双廊白族私房菜·白族烧烤(双廊古镇店)",
                                "source": "大众点评精选",
                                "reason": "如果上午活动偏双廊方向，这家最贴动线。",
                                "url": "https://m.dianping.com/discovery/599763534",
                            },
                            {
                                "name": "凤翔饭庄·洱海畔的味道",
                                "source": "大众点评",
                                "reason": "适合把大理段最后一顿午餐吃得更正式一点。",
                                "url": "https://www.dianping.com/shop/G8AsnnbiU5xm4Ivt/photos?pg=1",
                            },
                        ],
                    },
                    {
                        "slot": "晚餐",
                        "candidates": [
                            {
                                "name": "香佰里鲜货火锅(攀枝花店)",
                                "source": "大众点评攀枝花页",
                                "reason": "高热度、多人好点菜的稳定晚餐。",
                                "url": "https://www.dianping.com/panzhihua",
                            },
                            {
                                "name": "大笮风·新派特色川菜(攀枝花店)",
                                "source": "大众点评攀枝花页",
                                "reason": "不想吃火锅时的返程夜稳妥替代。",
                                "url": "https://www.dianping.com/panzhihua",
                            },
                        ],
                    },
                ],
            },
            {
                "day_index": 5,
                "date": "2026-05-05",
                "title": "攀枝花 -> 宜宾",
                "intensity": "高",
                "base_city": "宜宾解散",
                "priority_zone": "返程日，不再新增住宿",
                "schedule": [
                    "07:30-08:30 早餐",
                    "09:00 攀枝花出发",
                    "12:30-13:30 途中或回宜宾后午餐",
                    "17:30-18:30 回到宜宾",
                    "19:00 解散餐 / 散伙饭",
                ],
                "hotel_candidates": [],
                "meals": [
                    {
                        "slot": "早餐",
                        "candidates": [
                            {
                                "name": "任德琼盐边羊肉米线",
                                "source": "大众点评攀枝花页",
                                "reason": "返程日早餐最适合热汤粉面，补体力最稳。",
                                "url": "https://www.dianping.com/panzhihua",
                            },
                            {
                                "name": "小倪羊肉米线馆(攀枝花店)",
                                "source": "大众点评攀枝花页",
                                "reason": "更接地气的本地早餐备选。",
                                "url": "https://www.dianping.com/panzhihua",
                            },
                        ],
                    },
                    {
                        "slot": "午餐",
                        "candidates": [
                            {
                                "name": "中渡口面王(古叙路店)",
                                "source": "大众点评",
                                "reason": "回到宜宾后想快一点结束午餐时最实用。",
                                "url": "https://www.dianping.com/shop/H8eD0jXYeEDPbnhx",
                            },
                            {
                                "name": "刘臣街燃面(宜宾总店)",
                                "source": "大众点评",
                                "reason": "想用宜宾小吃做返程收尾时更轻快。",
                                "url": "https://www.dianping.com/shop/l7dWpIscLwPlgnyI",
                            },
                        ],
                    },
                    {
                        "slot": "晚餐",
                        "candidates": [
                            {
                                "name": "正宗知味轩李庄白肉(旧州路店)",
                                "source": "大众点评",
                                "reason": "散伙饭最适合选代表性强的宜宾地方菜。",
                                "url": "https://www.dianping.com/shop/3006910/photos",
                            },
                            {
                                "name": "老字号临江园餐饮店",
                                "source": "大众点评",
                                "reason": "更适合把最后一顿吃成老馆子式聚餐。",
                                "url": "https://www.dianping.com/shop/l8otVnY4o9zA7TCF",
                            },
                        ],
                    },
                ],
            },
        ],
        "budget": {
            "hotel_total": "约 ¥1600-2500",
            "car_total": "约 ¥2200-2800",
            "meal_total": "约 ¥2700-3900",
            "grand_total": "约 ¥6500-9200",
        },
        "warnings": [
            "五一期间酒店实时价可能高于常规价，下单前要再次核验是否仍压在预算内。",
            "昭通本次只作为可选缓冲点，不默认并入 5 晚主线。",
            "这条线最累的两段是 西昌 -> 丽江 和 攀枝花 -> 宜宾。",
        ],
    }
}

def _build_route_map(route_nodes: list[str]) -> dict:
    width = 480
    height = 360
    padding = 38
    coords = [CASE_CITY_COORDS[name] for name in route_nodes if name in CASE_CITY_COORDS]
    lons = [item[0] for item in coords]
    lats = [item[1] for item in coords]
    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    lon_span = max(max_lon - min_lon, 0.1)
    lat_span = max(max_lat - min_lat, 0.1)

    def project(city: str) -> tuple[float, float]:
        lon, lat = CASE_CITY_COORDS[city]
        x = padding + ((lon - min_lon) / lon_span) * (width - padding * 2)
        y = padding + ((max_lat - lat) / lat_span) * (height - padding * 2)
        return round(x, 1), round(y, 1)

    nodes = []
    for index, city in enumerate(route_nodes):
        x, y = project(city)
        if city == route_nodes[0] and index == 0:
            label = f"{city}·集合"
        elif city == route_nodes[-1] and index == len(route_nodes) - 1:
            label = f"{city}·解散"
        else:
            label = city
        nodes.append(
            {
                "name": city,
                "label": label,
                "x": x,
                "y": y,
                "is_terminal": index in {0, len(route_nodes) - 1},
            }
        )
    polyline = " ".join(f"{node['x']},{node['y']}" for node in nodes)
    segments = []
    for index in range(len(nodes) - 1):
        start = nodes[index]
        end = nodes[index + 1]
        segments.append(
            {
                "index": index,
                "from": start["name"],
                "to": end["name"],
                "points": f"{start['x']},{start['y']} {end['x']},{end['y']}",
            }
        )
    geo_nodes = []
    for node in nodes:
        lon, lat = CASE_CITY_COORDS[node["name"]]
        geo_nodes.append(
            {
                "name": node["name"],
                "label": node["label"],
                "lng": lon,
                "lat": lat,
                "is_terminal": node["is_terminal"],
            }
        )
    return {
        "width": width,
        "height": height,
        "nodes": nodes,
        "polyline": polyline,
        "segments": segments,
        "geo_nodes": geo_nodes,
    }


def _build_zone_map(city: str, priority_zone: str, secondary_zone: str) -> dict:
    layout = deepcopy(CASE_ZONE_LAYOUTS[city])
    layout["primary"]["full_label"] = priority_zone
    layout["secondary"]["full_label"] = secondary_zone
    return layout


def _build_zone_geo(city: str, priority_zone: str, secondary_zone: str) -> dict:
    markers = deepcopy(CASE_ZONE_GEO[city])
    return {
        "center": [CASE_CITY_COORDS[city][0], CASE_CITY_COORDS[city][1]],
        "markers": [
            {"kind": "primary", "label": priority_zone, "lng": markers["primary"][0], "lat": markers["primary"][1]},
            {"kind": "secondary", "label": secondary_zone, "lng": markers["secondary"][0], "lat": markers["secondary"][1]},
            {"kind": "poi", "label": CASE_ZONE_LAYOUTS[city]["poi"]["label"], "lng": markers["poi"][0], "lat": markers["poi"][1]},
            {"kind": "food", "label": CASE_ZONE_LAYOUTS[city]["food"]["label"], "lng": markers["food"][0], "lat": markers["food"][1]},
            {"kind": "parking", "label": CASE_ZONE_LAYOUTS[city]["parking"]["label"], "lng": markers["parking"][0], "lat": markers["parking"][1]},
        ],
    }


def _distance_value(text: str) -> int:
    match = re.search(r"(\d+)", text)
    return int(match.group(1)) if match else 0


def _leg_rank(intensity: str) -> int:
    return {"低": 0, "中": 1, "中高": 2, "高": 3}.get(intensity, 0)


def _build_route_summary(case: dict) -> dict:
    total_km = sum(_distance_value(leg["distance"]) for leg in case["route_legs"])
    hardest = sorted(case["route_legs"], key=lambda leg: (_leg_rank(leg["intensity"]), _distance_value(leg["distance"])), reverse=True)[:2]
    return {
        "city_count": len(case["route_nodes"]) - 1,
        "day_count": len(case["days"]),
        "total_km": total_km,
        "hardest_legs": hardest,
        "start": case["route_nodes"][0],
        "end": case["route_nodes"][-1],
    }


for case in CASE_STUDIES.values():
    stay_map = {item["city"]: item["hotel_candidates"] for item in case["stay_recommendations"]}
    for day in case["days"]:
        city = day["base_city"].replace("解散", "").strip()
        day["city_anchor"] = city.lower()
        day["default_expanded"] = False
        if city in stay_map:
            day["hotel_candidates"] = deepcopy(stay_map[city])
    for stay in case["stay_recommendations"]:
        stay["nearby_tags"] = CASE_ZONE_TAGS.get(stay["city"], [])
        if stay["city"] in CASE_ZONE_LAYOUTS:
            stay["zone_map"] = _build_zone_map(stay["city"], stay["priority_zone"], stay["secondary_zone"])
            stay["zone_geo"] = _build_zone_geo(stay["city"], stay["priority_zone"], stay["secondary_zone"])
            stay["anchor"] = stay["city"].lower()
            route_index = max(case["route_nodes"].index(stay["city"]) - 1, 0) if stay["city"] in case["route_nodes"] else 0
            stay["route_index"] = route_index
    case["floating_city_cards"] = [
        {
            "city": stay["city"],
            "anchor": stay["anchor"],
            "priority_zone": stay["priority_zone"],
            "student_fit": stay["student_fit"],
            "nearby_tags": stay["nearby_tags"][:3],
            "zone_geo": stay["zone_geo"],
            "hotel_preview": stay["hotel_candidates"][:2],
            "meal_preview": next(
                (
                    meal["candidates"][:2]
                    for day in case["days"]
                    if day["base_city"] == stay["city"]
                    for meal in day["meals"]
                    if meal["candidates"]
                ),
                [],
            ),
        }
        for stay in case["stay_recommendations"]
    ]
    case["route_map"] = _build_route_map(case["route_nodes"])
    case["share_summary"] = _build_route_summary(case)


def get_case_study(case_id: str) -> dict:
    if case_id not in CASE_STUDIES:
        raise KeyError(case_id)
    return deepcopy(CASE_STUDIES[case_id])


def list_case_study_ids() -> list[str]:
    return sorted(CASE_STUDIES)
