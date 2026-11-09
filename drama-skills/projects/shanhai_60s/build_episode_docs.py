#!/usr/bin/env python3
"""
生成《山海寻光记：赴一场四季星河》（EP001 · 60.0s 治愈系 3D AI 漫剧）全套五份 zenstory-ai/drama-skills 规范文档
并通过 creator_markdown_check.py 跨文档一致性锁与真实资产引用校验，同时输出双云 GPU 生产清单 episode_manifest_60s.json。
"""
import json
from pathlib import Path

PROJ = Path(__file__).resolve().parent
EP = PROJ / "剧集" / "EP001"
EP.mkdir(parents=True, exist_ok=True)

LOCK_LULU = "chubby golden-yellow plush hippo-capybara boy Lulu with a small orange tangerine on his head and warm brown shorts"
LOCK_LUMEI = "petite cream-yellow plush hippo-capybara girl Lumei in a white ruffled sprout bonnet and pastel pink strawberry-pocket dress"

SHOTS = [
    # ==================== ACT I: 破晓云谷 (00s - 15s) ====================
    {
        "idx": 1,
        "id": "SHOT-EP001-001",
        "motion_id": "MOTION-EP001-001",
        "scene_id": "EP001-SC001",
        "act": "第一幕·破晓云谷",
        "title": "云海石桥与晨光列车",
        "kind": "landscape",
        "speaker": "噜妹",
        "voice_mode": "VO",
        "line": "听说山海尽头，藏着整片会发光的星河。",
        "sub_display": "噜妹（独白）：听说山海尽头\\N藏着整片会发光的星河",
        "place": "破晓云海高架桥",
        "purpose": "以吉卜力式壮阔破晓云海与蒸汽绿皮小火车大远景开篇，瞬间立住山海寻光的世界观与晨光色温。",
        "camera": "高空俯瞰大远景缓推，越过松林峡谷推向驶过石拱桥的蒸汽小火车。",
        "start_state": "朝霞刺破粉色翻涌云海，奶油绿复古小火车刚驶上高架石桥，白雾初升。",
        "action": "火车沿弧形石桥平稳向前行驶，车头喷出绵密洁白蒸汽随山风向后飘散，云海翻涌，两只白鸟掠过金色丁达尔光束。",
        "end_state": "列车行至石桥中段，金色晨光铺满整座峡谷。",
        "kf_prompt": "9:16 vertical cinematic 3D animated film grand landscape establishing shot in a tactile felt-and-wood miniature aesthetic: golden sunrise rays break through a glowing sea of pink morning clouds in an emerald pine valley, an ancient arched stone viaduct spans the canyon as a vintage cream-and-green steam train puffs white steam across the bridge, tiny white birds gliding through volumetric sunbeams, no text, no logo.",
        "motion_prompt": "In a 9:16 vertical 3D miniature animated mountain valley at sunrise, a vintage cream-and-green steam train rides smoothly forward along the curved stone viaduct bridge above a rolling sea of pink and golden clouds. Billowing white steam puffs continuously from the locomotive chimney and drifts backward in the mountain breeze, golden sunbeams shimmer through the mist, and small white birds glide gracefully across the upper sky as the camera gently pushes forward. Smooth cinematic motion, no text, no logo.",
    },
    {
        "idx": 2,
        "id": "SHOT-EP001-002",
        "motion_id": "MOTION-EP001-002",
        "scene_id": "EP001-SC001",
        "act": "第一幕·破晓云谷",
        "title": "木质车厢里的星河车票",
        "kind": "character",
        "speaker": "噜妹",
        "voice_mode": "DIALOGUE",
        "line": "噜噜快看，列车穿过云海啦！",
        "sub_display": "噜妹：噜噜快看\\N列车穿过云海啦！",
        "place": "复古木质列车车厢",
        "purpose": "从大远景切入温暖车厢内景，交代两位主角身份与星河车票信物，窗外粉色云海与上一镜严丝合缝。",
        "camera": "车厢双人中近景微推，暖金晨光从后方大车窗逆光包裹两人绒毛轮廓。",
        "start_state": "噜噜坐在左排木椅递出金色星河车票，噜妹坐在右排望向窗外云海。",
        "action": "窗外粉色云海向后流动，噜妹开心地晃动小脚丫、转头看向车票并拍手欢呼，噜噜眉眼弯弯把金色车票往前递。",
        "end_state": "两人隔着过道相视灿烂微笑，窗外晨光柔和流淌。",
        "kf_prompt": f"9:16 vertical 3D soft plush felt animation medium shot inside a cozy vintage wooden train carriage lit by rose-gold sunrise through a large window showing pink clouds: on frame left sits {LOCK_LULU} holding out a golden star train ticket; on frame right sits {LOCK_LUMEI} looking delightedly toward the glowing cloud sea, warm dust motes in sunbeams, no text, no logo.",
        "motion_prompt": f"Inside a warm sunlit wooden train carriage in 9:16 vertical 3D plush animation, {LOCK_LULU} on the left smiles warmly and extends his paw holding a golden star ticket, while {LOCK_LUMEI} on the right claps her paws joyfully and nods with sparkling eyes as pink morning clouds glide past outside the window and golden dust motes float in the sunbeams. Gentle camera push-in, consistent plush faces, no text, no logo.",
    },
    {
        "idx": 3,
        "id": "SHOT-EP001-003",
        "motion_id": "MOTION-EP001-003",
        "scene_id": "EP001-SC001",
        "act": "第一幕·破晓云谷",
        "title": "森林小站牵手启程",
        "kind": "character",
        "speaker": "噜噜",
        "voice_mode": "DIALOGUE",
        "line": "车票收好，今天带你把山海走遍。",
        "sub_display": "噜噜：车票收好\\N今天带你把山海走遍",
        "place": "森林木质火车站台",
        "purpose": "列车到站，两人走上洒满丁达尔晨光的森林站台牵手出发，完成第一幕行动立意。",
        "camera": "全身双人中景，顺着站台木板向前缓跟。",
        "start_state": "奶油绿蒸汽火车停靠在身后吐着白雾，噜噜背着棕色帆布小包牵住噜妹的手站在木站台上。",
        "action": "两人手牵手沿着洒满晨光的木质站台向镜头前方轻快迈步，身后火车头白雾袅袅升腾，树叶光斑摇曳。",
        "end_state": "两人并肩走到站台前缘，笑容温暖坚定。",
        "kf_prompt": f"9:16 vertical 3D soft plush felt animation full-body medium shot on a sunlit wooden forest train station platform: {LOCK_LULU} wearing a small brown canvas satchel holds hands with {LOCK_LUMEI}, both facing front smiling brightly, vintage cream-and-green steam locomotive puffing white steam under lush green trees behind them, golden Tyndall sunbeams, no text, no logo.",
        "motion_prompt": f"On a sunlit wooden forest station platform in 9:16 vertical 3D plush animation, {LOCK_LULU} with a brown canvas satchel and {LOCK_LUMEI} hold paws and walk cheerfully forward toward the camera with gentle bouncy steps while white steam rises softly from the vintage green locomotive behind them and golden sunbeams flicker through green leaves. Smooth forward tracking, no text, no logo.",
    },
    {
        "idx": 4,
        "id": "SHOT-EP001-004",
        "motion_id": "MOTION-EP001-004",
        "scene_id": "EP001-SC001",
        "act": "第一幕·破晓云谷",
        "title": "石阶向晴·远望风车苍山",
        "kind": "character",
        "speaker": "噜妹",
        "voice_mode": "DIALOGUE",
        "line": "嗯！只要和你并肩，多远都不怕！",
        "sub_display": "噜妹：嗯！只要和你并肩\\N多远都不怕！",
        "place": "山坡青石步道",
        "purpose": "第一幕收尾过渡镜：天色由晨雾转为晴空碧草，远处雪山与白色大风车提前入画，无缝衔接第二幕花海。",
        "camera": "开阔远中景缓升，展现两人融入壮阔山坡草甸与远方雪山风车。",
        "start_state": "翠绿山坡青石小径上，噜噜与噜妹手牵手站在中景，远方雪山与白色风车清晰可见。",
        "action": "微风吹拂碧绿草浪，两人手牵手轻快迈步并相视一笑，远处白色风车叶片悠然转动，白云缓缓飘移。",
        "end_state": "阳光洒满整片山坡，两人步伐轻盈奔向远方风车岭。",
        "kf_prompt": f"9:16 vertical 3D soft plush felt animation wide scenic shot on a sunlit stone path curving up an emerald green hillside: {LOCK_LULU} and {LOCK_LUMEI} walk hand in hand in three-quarter front view smiling fondly at each other, distant snow-capped peaks and white wooden windmills rising under a clear blue sky with fluffy white clouds, no text, no logo.",
        "motion_prompt": f"Along a sunlit stone path on an emerald green hillside in 9:16 vertical 3D plush animation, {LOCK_LULU} and {LOCK_LUMEI} hold hands and walk happily together as lush grass ripples in the breeze, distant white windmill blades turn slowly on the horizon ridge, and white clouds drift across the bright blue sky. Gentle upward crane motion, no text, no logo.",
    },

    # ==================== ACT II: 晴风花海与林涧晴雨 (15s - 30s) ====================
    {
        "idx": 5,
        "id": "SHOT-EP001-005",
        "motion_id": "MOTION-EP001-005",
        "scene_id": "EP001-SC002",
        "act": "第二幕·晴风花海与晴雨",
        "title": "雪峰风车与无边花海",
        "kind": "landscape",
        "speaker": "噜噜",
        "voice_mode": "VO",
        "line": "春风拂过山岗的时候，连时间都慢了下来。",
        "sub_display": "噜噜（独白）：春风拂过山岗的时候\\N连时间都慢了下来",
        "place": "风车波斯菊花海",
        "purpose": "第二幕开篇纯风景空镜：承接上一镜远景中的雪峰与白风车，展开漫山遍野粉色波斯菊与金色蒲公英花浪。",
        "camera": "贴近花丛的低机位大远景横摇缓推，花瓣与蒲公英绒毛迎风掠过镜头。",
        "start_state": "晴空积雨云与雪山之下，粉色波斯菊与黄花铺满山坡，两座白色木风车伫立山脊。",
        "action": "山风吹起层层粉色与金色花浪，两座白色风车木翼平稳旋转，粉色花瓣与洁白蒲公英绒毛在阳光里随风飘舞。",
        "end_state": "花海波浪翻涌，积雨云洁白明亮，春意盎然。",
        "kf_prompt": "9:16 vertical cinematic 3D animated film grand landscape establishing shot in a tactile felt-and-wood aesthetic: under a bright azure sky with towering fluffy cumulus clouds and snow-dusted peaks, rolling hills of pink cosmos flowers and golden dandelions sway in waves toward two tall white wooden windmills on the ridge, floating petals and dandelion seeds in sunlight, no text, no logo.",
        "motion_prompt": "In a radiant 9:16 vertical 3D animated alpine meadow under a blue sky and fluffy cumulus clouds, endless hills of pink cosmos flowers and yellow dandelions sway rhythmically in waves in the spring breeze while the blades of two white wooden windmills rotate steadily on the sunlit ridge and delicate flower petals and white dandelion fluff drift gracefully across the air. Smooth slow push-in, no text, no logo.",
    },
    {
        "idx": 6,
        "id": "SHOT-EP001-006",
        "motion_id": "MOTION-EP001-006",
        "scene_id": "EP001-SC002",
        "act": "第二幕·晴风花海与晴雨",
        "title": "花径吹散蒲公英许愿星",
        "kind": "character",
        "speaker": "噜妹",
        "voice_mode": "DIALOGUE",
        "line": "风把蒲公英吹走啦，像不像许愿星？",
        "sub_display": "噜妹：风把蒲公英吹走啦\\N像不像许愿星？",
        "place": "风车波斯菊花海",
        "purpose": "切入花海中央双人近中景互动，背景保留同一座白风车与花丛，细节灵动治愈。",
        "camera": "齐腰双人近中景，浅景深聚焦飘飞的蒲公英绒毛与两人笑脸。",
        "start_state": "花海小径上，噜妹举着白色蒲公英绒球准备吹气，噜噜站在右侧温柔看着她。",
        "action": "噜妹嘟嘴轻轻一吹，洁白的蒲公英绒毛纷纷散开随微风飘向空中，噜噜开心地伸爪轻托飞起的绒毛，身后风车缓转。",
        "end_state": "漫天白色绒毛在阳光下闪烁如星点，两人眉眼弯弯。",
        "kf_prompt": f"9:16 vertical 3D soft plush felt animation medium-close shot along a sunlit flower path of pink cosmos and dandelions with a white wooden windmill softly blurred behind: on frame left {LOCK_LUMEI} blows a fluffy white dandelion seed ball as seeds float into sunlit air; on frame right {LOCK_LULU} smiles fondly watching the drifting seeds, crisp plush detail, no text, no logo.",
        "motion_prompt": f"Standing in a sunlit flower meadow in 9:16 vertical 3D plush animation with a white windmill turning softly in the background, {LOCK_LUMEI} gently blows a white dandelion puff, sending dozens of fluffy white seeds floating across the sunny air while {LOCK_LULU} beside her smiles warmly and sways happily as pink flowers ripple in the breeze. Crisp character consistency, no text, no logo.",
    },
    {
        "idx": 7,
        "id": "SHOT-EP001-007",
        "motion_id": "MOTION-EP001-007",
        "scene_id": "EP001-SC003",
        "act": "第二幕·晴风花海与晴雨",
        "title": "林涧石桥·偏向你的太阳雨伞",
        "kind": "character",
        "speaker": "噜噜",
        "voice_mode": "DIALOGUE",
        "line": "山里下太阳雨啦，往我怀里靠一点。",
        "sub_display": "噜噜：山里下太阳雨啦\\N往我怀里靠一点",
        "place": "翠溪青苔古石桥",
        "purpose": "情绪小波折与升温：山间突降晶莹太阳雨，古石桥、翡翠溪流与倾斜的透明伞构成极致唯美江南/吉卜力雨景。",
        "camera": "溪面低角度中远景缓推，同时捕捉桥下涟漪与桥上撑伞相依的两人。",
        "start_state": "金色阳光穿透树冠洒在青苔石拱桥上，晶莹雨丝落下，噜噜撑着透明雨伞护住噜妹。",
        "action": "银亮太阳雨滴不断落下并在翡翠色溪面激起一圈圈涟漪，噜噜把透明雨伞进一步往噜妹头顶倾斜，噜妹安心地贴近噜噜手臂。",
        "end_state": "伞面水珠闪烁金光，两人在雨丝中温馨依偎。",
        "kf_prompt": f"9:16 vertical 3D soft plush felt animation scenic medium-wide shot on a mossy arched stone bridge over a crystal emerald forest stream during a golden sun-shower: {LOCK_LULU} holds a transparent umbrella tilted over {LOCK_LUMEI} nestled close beside him, golden sunbeams piercing lush green leaves as sparkling raindrops fall and form concentric ripples on the water below, no text, no logo.",
        "motion_prompt": f"On a mossy stone arch bridge over an emerald stream in 9:16 vertical 3D plush animation, sparkling sun-shower raindrops fall steadily through golden sunbeams and create expanding ripples across the clear water below while {LOCK_LULU} tilts his transparent umbrella lovingly over {LOCK_LUMEI} who leans affectionately against his arm, both smiling gently. Smooth subtle push-in, no text, no logo.",
    },
    {
        "idx": 8,
        "id": "SHOT-EP001-008",
        "motion_id": "MOTION-EP001-008",
        "scene_id": "EP001-SC003",
        "act": "第二幕·晴风花海与晴雨",
        "title": "雨霁云开·瀑布山谷双彩虹",
        "kind": "character",
        "speaker": "噜妹",
        "voice_mode": "DIALOGUE",
        "line": "哇，雨停之后真的有彩虹桥耶！",
        "sub_display": "噜妹：哇，雨停之后\\N真的有彩虹桥耶！",
        "place": "翠溪青苔古石桥",
        "purpose": "第二幕高潮收束并转入暖金色调：雨停收伞，瀑布山谷升起双彩虹，暖霞初染云层，自然过渡至第三幕暮色海岸。",
        "camera": "石桥中景微仰摇，将前景惊喜的两人与后景飞瀑双彩虹同框收纳。",
        "start_state": "古石桥边雨止云开，噜妹收起透明雨伞望向远方山谷瀑布与双彩虹，噜噜含笑立于身侧。",
        "action": "远处白练瀑布奔流而下激起水雾，双彩虹在暖金云层下熠熠生辉，噜妹欢快地举起透明伞指向彩虹，噜噜点头温柔微笑。",
        "end_state": "暖金天光洒满峡谷与两人脸庞，充满希望感。",
        "kf_prompt": f"9:16 vertical 3D soft plush felt animation scenic medium shot on the mossy stone bridge overlooking a lush green waterfall canyon as rain clears into warm golden light: {LOCK_LULU} smiles warmly beside {LOCK_LUMEI} holding a folded transparent umbrella and pointing joyfully toward a glowing double rainbow arching over the misty waterfall under warm golden clouds, no text, no logo.",
        "motion_prompt": f"Beside a mossy stone bridge overlooking a misty emerald waterfall valley in 9:16 vertical 3D plush animation, white waterfall cascades flow continuously in the background beneath a glowing double rainbow while {LOCK_LUMEI} waves her folded umbrella joyfully toward the rainbow and {LOCK_LULU} looks at her with a warm affectionate smile in golden afternoon light. Gentle upward tilt, no text, no logo.",
    },

    # ==================== ACT III: 暮色橘子海与悬崖灯塔 (30s - 45s) ====================
    {
        "idx": 9,
        "id": "SHOT-EP001-009",
        "motion_id": "MOTION-EP001-009",
        "scene_id": "EP001-SC004",
        "act": "第三幕·暮色橘子海与灯塔",
        "title": "悬崖白灯塔与橘子海落日",
        "kind": "landscape",
        "speaker": "噜妹",
        "voice_mode": "VO",
        "line": "原来最温柔的黄昏，是山风吹向大海的那一刻。",
        "sub_display": "噜妹（独白）：原来最温柔的黄昏\\N是山风吹向大海的那一刻",
        "place": "海岬悬崖白灯塔",
        "purpose": "第三幕开篇纯风景大远景：视野豁然开朗至大海与悬崖灯塔，漫天橘红晚霞将情绪推向浪漫高潮。",
        "camera": "海岬高空航拍感大远景缓推，海浪拍岸、海鸥掠过霞光、灯塔暖光亮起。",
        "start_state": "翠绿海岬悬崖顶矗立纯白灯塔，下方橘子海波光潋滟，落日临近海平线，海鸥展翅。",
        "action": "金色海面波浪层层涌动闪烁碎金光芒，海鸥乘着晚风滑翔掠过橙粉霞云，悬崖顶白灯塔的琥珀色灯室发出温暖光芒。",
        "end_state": "漫天橘色霞光与波光海面交相辉映。",
        "kf_prompt": "9:16 vertical cinematic 3D animated film grand coastal landscape establishing shot in a tactile felt-and-wood aesthetic: an emerald-green headland cliff rises above a shimmering tangerine-orange sunset ocean, a charming round white lighthouse glows with warm amber light on the cliff edge, golden sun touching the horizon under coral and lavender clouds as white seagulls soar, no text, no logo.",
        "motion_prompt": "In a breathtaking 9:16 vertical 3D animated coastal sunset landscape, golden-orange ocean waves shimmer and roll gently against the base of an emerald headland cliff topped with a glowing white lighthouse, while white seagulls glide smoothly across warm coral-and-amber clouds as the camera slowly pushes forward over the sea. Rich atmospheric depth, no text, no logo.",
    },
    {
        "idx": 10,
        "id": "SHOT-EP001-010",
        "motion_id": "MOTION-EP001-010",
        "scene_id": "EP001-SC004",
        "act": "第三幕·暮色橘子海与灯塔",
        "title": "追着落日海风骑行",
        "kind": "character",
        "speaker": "噜噜",
        "voice_mode": "DIALOGUE",
        "line": "抓稳咯，趁太阳落山前赶去海边！",
        "sub_display": "噜噜：抓稳咯\\N趁太阳落山前赶去海边！",
        "place": "落日滨海公路",
        "purpose": "高动态骑行镜头，右后方远景依然可见上一镜的悬崖白灯塔，地理空间完全贯通！",
        "camera": "侧前方中景同步跟拍，海风拂动裙摆与帽带。",
        "start_state": "金色夕阳滨海公路上，噜噜驾驶奶油白小踏板车，噜妹坐在后座挥手感受海风，远处悬崖灯塔伫立。",
        "action": "奶油白小踏板车沿着滨海弯道轻快向前行驶，身旁金色海面波光飞驰，噜妹开心挥动小手、帽带随风轻扬，噜噜稳稳握把微笑。",
        "end_state": "两人沐浴着橘金夕阳驶向海畔木栈道。",
        "kf_prompt": f"9:16 vertical 3D soft plush felt animation dynamic medium shot on a golden-orange sunset coastal road with a white cliffside lighthouse in the far background: {LOCK_LULU} happily steers a cute cream-white vintage scooter while {LOCK_LUMEI} sits behind hugging his waist with one paw and waving cheerfully in the sea breeze beside sparkling amber waves, no text, no logo.",
        "motion_prompt": f"Along a golden sunset coastal road beside sparkling orange ocean waves in 9:16 vertical 3D plush animation, {LOCK_LULU} steers a cream-white vintage scooter smoothly forward toward the camera while {LOCK_LUMEI} on the back seat waves her paw joyfully in the sea breeze with a distant white cliff lighthouse behind them. Smooth dynamic tracking shot, no text, no logo.",
    },
    {
        "idx": 11,
        "id": "SHOT-EP001-011",
        "motion_id": "MOTION-EP001-011",
        "scene_id": "EP001-SC004",
        "act": "第三幕·暮色橘子海与灯塔",
        "title": "木栈并肩·共看橘子海晚霞",
        "kind": "character",
        "speaker": "噜妹",
        "voice_mode": "DIALOGUE",
        "line": "要是每天傍晚，都能和你一起看海就好啦。",
        "sub_display": "噜妹：要是每天傍晚\\N都能和你一起看海就好啦",
        "place": "海畔落日木栈道",
        "purpose": "停下车并肩坐在海边木栈道静赏橘子海，动静结合沉淀温柔情感。",
        "camera": "木栈道双人近中景缓推，暖橘逆光勾勒两人柔和轮廓。",
        "start_state": "两人并肩坐在海边木栈道边缘，双脚轻悬，身后是漫天橘红霞光与金色海浪。",
        "action": "金色海浪轻柔拍岸闪烁波光，噜妹微微歪头靠向噜噜肩膀，噜噜轻轻握住她的小手并温柔点头，微风拂过。",
        "end_state": "两人在琥珀色落日余晖里静静相依。",
        "kf_prompt": f"9:16 vertical 3D soft plush felt animation medium shot on a seaside wooden pier at sunset: {LOCK_LULU} and {LOCK_LUMEI} sit side by side on the wooden pier edge facing three-quarter front with warm orange sunset rim light on their plush cheeks, shimmering tangerine ocean waves and glowing sunset sky behind them, no text, no logo.",
        "motion_prompt": f"Sitting side by side on a wooden seaside pier at golden-orange sunset in 9:16 vertical 3D plush animation, {LOCK_LULU} and {LOCK_LUMEI} sway their feet gently and lean warmly toward each other with tender smiles while shimmering amber ocean waves ripple continuously across the sunset horizon behind them. Slow intimate push-in, no text, no logo.",
    },
    {
        "idx": 12,
        "id": "SHOT-EP001-012",
        "motion_id": "MOTION-EP001-012",
        "scene_id": "EP001-SC005",
        "act": "第三幕·暮色橘子海与灯塔",
        "title": "暮色蓝调·万家灯火陪我们回家",
        "kind": "character",
        "speaker": "噜噜",
        "voice_mode": "DIALOGUE",
        "line": "天黑也不怕，满街灯火都在陪我们往前走。",
        "sub_display": "噜噜：天黑也不怕\\N满街灯火都在陪我们往前走",
        "place": "暮色古镇暖灯石街",
        "purpose": "第三幕向第四幕的色温桥梁：天色步入深蓝暮色，街头串灯与灯笼渐次亮起，自然引出第四幕万灯星夜。",
        "camera": "青石板长街双人全身中景正面跟拍，背景暖黄串灯形成梦幻散景光斑。",
        "start_state": "暮色蓝调下的古镇石板街挂满暖黄灯笼与串灯，噜噜拎着小篮、噜妹捧着小花束手牵手站在街中。",
        "action": "两人手牵手沿着暖光映照的青石板路向镜头前方轻快行走，头顶灯笼随晚风轻轻摇晃，暖金光晕流转。",
        "end_state": "灯火辉煌的古镇夜色温柔包裹两人。",
        "kf_prompt": f"9:16 vertical 3D soft plush felt animation full-body medium shot on a twilight cobblestone street hung with glowing warm yellow lanterns and fairy string lights: {LOCK_LULU} and {LOCK_LUMEI} walk hand in hand facing front with warm lantern light on their smiling faces, deep twilight-blue sky above cozy wooden eaves, no text, no logo.",
        "motion_prompt": f"Walking hand in hand down a charming cobblestone town lane at twilight in 9:16 vertical 3D plush animation, {LOCK_LULU} and {LOCK_LUMEI} step forward cheerfully toward the camera smiling warmly at each other as overhead strings of warm golden lanterns sway gently in the evening breeze with dreamy bokeh lights behind them. Smooth backward tracking shot, no text, no logo.",
    },

    # ==================== ACT IV: 河灯万千与四季星河 (45s - 60s) ====================
    {
        "idx": 13,
        "id": "SHOT-EP001-013",
        "motion_id": "MOTION-EP001-013",
        "scene_id": "EP001-SC005",
        "act": "第四幕·万灯星河收束",
        "title": "古镇千盏河灯汇入银河",
        "kind": "landscape",
        "speaker": "噜妹",
        "voice_mode": "VO",
        "line": "人间万千灯火，顺着晚风飘向了星河。",
        "sub_display": "噜妹（独白）：人间万千灯火\\N顺着晚风飘向了星河",
        "place": "星夜河灯古镇水巷",
        "purpose": "第四幕开篇纯风景夜景奇观：蜿蜒河道千盏金色莲花灯与夜空璀璨银河交融，将视觉浪漫感拉至巅峰。",
        "camera": "贴近水面的大远景缓推微仰，从漂流的河灯一路摇向深蓝银河与孔明灯。",
        "start_state": "静谧古镇夜河上漂浮着成百上千盏金色莲花河灯，两岸木楼灯火倒映，天际银河璀璨。",
        "action": "数百盏温暖金黄的莲花河灯顺着微波荡漾的河水缓缓漂流，水面金色倒影摇曳，几盏暖光孔明灯冉冉升向璀璨银河夜空。",
        "end_state": "河面万灯与天上星河连成一片金色光海。",
        "kf_prompt": "9:16 vertical cinematic 3D animated film enchanted night landscape establishing shot in a tactile felt-and-wood aesthetic: a winding tranquil river in an ancient wooden riverside town glows with hundreds of floating golden-amber lotus river lanterns reflecting on dark blue water, merging at the horizon into a deep-indigo night sky filled with the luminous Milky Way galaxy and rising warm sky lanterns, no text, no logo.",
        "motion_prompt": "In an enchanted 9:16 vertical 3D animated riverside town at night, hundreds of glowing golden lotus lanterns float gently downstream along rippling dark water reflecting warm amber light while warm sky lanterns drift slowly upward toward a sparkling deep-indigo Milky Way night sky as the camera glides smoothly forward above the river. Magical cinematic lighting, no text, no logo.",
    },
    {
        "idx": 14,
        "id": "SHOT-EP001-014",
        "motion_id": "MOTION-EP001-014",
        "scene_id": "EP001-SC006",
        "act": "第四幕·万灯星河收束",
        "title": "木屋暖灯与两杯热可可",
        "kind": "character",
        "speaker": "噜妹",
        "voice_mode": "DIALOGUE",
        "line": "捧着热可可，连山顶的晚风都暖呼呼啦！",
        "sub_display": "噜妹：捧着热可可\\N连山顶的晚风都暖呼呼啦！",
        "place": "山顶木屋暖灯客厅",
        "purpose": "观星前的温暖小憩：木屋暖黄台灯与热可可袅袅白雾，与窗外寒凉星夜形成极致温暖反差。",
        "camera": "室内双人中景微推，聚焦杯口升腾的白色热气与两人相视笑颜。",
        "start_state": "山顶木屋暖黄落地灯下，噜噜与噜妹坐在柔软地毯靠垫上手捧白色陶瓷热可可杯。",
        "action": "两只陶瓷杯口袅袅升起柔和洁白热气，噜噜与噜妹轻轻碰杯、相视一笑并低头轻抿热可可，暖光静静流淌。",
        "end_state": "热气氤氲，满屋温馨静谧。",
        "kf_prompt": f"9:16 vertical 3D soft plush felt animation cozy medium shot inside a warm wooden cabin lit by a golden floor lamp at night: {LOCK_LULU} and {LOCK_LUMEI} sit side by side on a plush rug holding white ceramic mugs of steaming hot cocoa with soft white steam rising, warm amber light, no text, no logo.",
        "motion_prompt": f"Inside a cozy warm-lit wooden cabin at night in 9:16 vertical 3D plush animation, {LOCK_LULU} and {LOCK_LUMEI} sit together holding ceramic mugs as delicate white steam curls steadily upward from the hot cocoa; they gently clink their mugs together and smile fondly at each other in golden lamp light. Subtle warm camera push-in, no text, no logo.",
    },
    {
        "idx": 15,
        "id": "SHOT-EP001-015",
        "motion_id": "MOTION-EP001-015",
        "scene_id": "EP001-SC006",
        "act": "第四幕·万灯星河收束",
        "title": "观星木台·双流星划过银河",
        "kind": "landscape",
        "speaker": "噜噜",
        "voice_mode": "VO",
        "line": "抬头看，山海尽头的整片星河，真的在等我们。",
        "sub_display": "噜噜（独白）：抬头看，山海尽头的星河\\N真的在等我们",
        "place": "山顶串灯观星露台",
        "purpose": "终极星空纯风景空镜：推门来到挂满暖黄串灯的山顶木露台，浩瀚银河与流星雨呼应开篇第一句约定！",
        "camera": "山顶木栏与浩瀚银河大广角仰拍缓推，流星划破深蓝天幕。",
        "start_state": "挂着暖黄串灯的山顶木质观星台面向群山云海，深蓝夜空横跨璀璨银河，繁星闪烁。",
        "action": "木栏上的暖黄串灯在夜风中微微轻晃，璀璨银河星光闪烁流转，两道耀眼银白流星拖着长长光尾划过夜空山巅。",
        "end_state": "星河浩瀚静美，串灯温暖守候。",
        "kf_prompt": "9:16 vertical cinematic 3D animated film grand starry night landscape establishing shot in a tactile felt-and-wood aesthetic: a cozy hilltop wooden stargazing terrace railing strung with glowing warm fairy lights overlooks misty mountain silhouettes under a vast deep-indigo Milky Way galaxy sky as bright silver shooting stars streak gracefully across the stars, no text, no logo.",
        "motion_prompt": "From a hilltop wooden stargazing terrace decorated with warm glowing fairy string lights in 9:16 vertical 3D animation, warm string lights sway gently in the night breeze in the foreground while millions of stars shimmer across a luminous deep-indigo Milky Way sky and bright silver shooting stars streak smoothly across the heavens above misty mountain peaks. Slow awe-inspiring tilt-up push, no text, no logo.",
    },
    {
        "idx": 16,
        "id": "SHOT-EP001-016",
        "motion_id": "MOTION-EP001-016",
        "scene_id": "EP001-SC006",
        "act": "第四幕·万灯星河收束",
        "title": "星河烟花·岁岁年年在你身边",
        "kind": "character",
        "speaker": "噜噜",
        "voice_mode": "DIALOGUE",
        "line": "走过山海四季，往后岁岁年年，都在你身边。",
        "sub_display": "噜噜：走过山海四季\\N往后岁岁年年，都在你身边",
        "place": "山顶串灯观星露台",
        "purpose": "全片 60s 情感收官定格：承接上一镜同一座串灯观星木露台，金色烟花在星河下绽放，两人脸贴脸幸福收尾。",
        "camera": "观星木露台双人近中景温柔定格微拉，烟花光晕点亮夜空后柔和渐暗留白。",
        "start_state": "璀璨星空与串灯木露台上，噜噜与噜妹并肩脸贴着脸闭眼微笑，夜空第一朵金色烟花初绽。",
        "action": "深蓝繁星夜空中朵朵温暖金色烟花依次升空绚烂绽放、化作漫天金粉星雨缓缓飘落，噜噜与噜妹脸贴着脸幸福依偎轻晃。",
        "end_state": "漫天星光与金色余晖温柔包裹两人，圆满定格。",
        "kf_prompt": f"9:16 vertical 3D soft plush felt animation heartwarming close-medium finale shot on the fairy-lit hilltop wooden terrace under a starry night sky with blooming golden fireworks: {LOCK_LULU} and {LOCK_LUMEI} stand side by side leaning cheek-to-cheek with happy closed-eye smiles and rosy cheeks, warm golden string light bokeh, no text, no logo.",
        "motion_prompt": f"On a fairy-lit hilltop wooden terrace under a starry indigo night sky in 9:16 vertical 3D plush animation, {LOCK_LULU} and {LOCK_LUMEI} cuddle cheek-to-cheek swaying gently with blissful closed-eye smiles while warm golden fireworks bloom and sparkle gracefully across the starry sky behind them, casting soft golden glow over their plush faces. Gentle heartwarming finale motion, no text, no logo.",
    },
]

# 1. 剧本.md
scenes_meta = [
    ("EP001-SC001", "外/内 · 破晓云海高架桥与森林小站 · 晨", [1, 2, 3, 4]),
    ("EP001-SC002", "外 · 苍山白色风车与波斯菊花海 · 日", [5, 6]),
    ("EP001-SC003", "外 · 森林翡翠溪流古石桥与瀑布峡谷 · 午后晴雨", [7, 8]),
    ("EP001-SC004", "外 · 海岬悬崖白灯塔与落日滨海栈道 · 黄昏", [9, 10, 11]),
    ("EP001-SC005", "外 · 暮色灯笼古街与千盏河灯水巷 · 入夜", [12, 13]),
    ("EP001-SC006", "内/外 · 山顶暖灯木屋与星河观星露台 · 星夜", [14, 15, 16]),
]

script_lines = ["# EP001 · 山海寻光记：赴一场四季星河\n"]
for sc_id, sc_title, s_nums in scenes_meta:
    script_lines.append(f"## {sc_id} {sc_title}\n")
    for n in s_nums:
        s = SHOTS[n - 1]
        script_lines.append(f"{s['start_state']}{s['action']}\n")
        if s["voice_mode"] == "VO":
            script_lines.append(f"[VO] {s['speaker']}：{s['line']}\n")
        else:
            script_lines.append(f"{s['speaker']}：{s['line']}\n")

(EP / "剧本.md").write_text("\n".join(script_lines), encoding="utf-8")

# 2. 视觉设定.md
char_shot_ids = "、".join(s["id"] for s in SHOTS if s["kind"] == "character")
places = []
for s in SHOTS:
    if s["place"] not in places:
        places.append(s["place"])

vis_lines = [
    "# EP001 视觉设定\n",
    "- 制作形态：3D 毛毡绘本治愈系动态漫剧，竖屏 9:16（1080×1920 · 24fps）。",
    "- 视觉世界观：吉卜力与皮克斯微缩毛毡木艺质感结合，从破晓粉色云海 → 晴空雪峰风车花海 → 林涧翡翠晴雨彩虹 → 悬崖灯塔橘子海落日 → 古镇千盏河灯 → 山顶璀璨星河烟花，全片色彩色温随时间自然流转。\n",
    "## 人物 · 噜噜\n",
    "- 憨厚温暖的金黄色圆润河马水豚质感毛绒男孩，身材微胖饱满，头顶稳稳顶着一颗带绿叶的小巧橙色橘子。",
    "- 本集造型：暖棕色短裤（车站启程镜配复古棕色帆布斜挎小包），神态温柔稳重，眼神清澈有神。",
    "- 识别锚点：金黄色毛绒圆脸、宽圆吻部、头顶橙色小橘子、暖棕色短裤。",
    "- 画面代称：Lulu",
    "- 声音参考：设定集/voices/ref_lulu_clean.flac（F5-TTS + Seed-VC 44.1kHz 克隆参考干声）",
    f"- 连续性锁：LOCK-LULU-PLUSH《噜噜金黄毛绒橘子造型》（镜头：{char_shot_ids}；图片提示词项：IMG-LULU-SHEET）· 锁面：{LOCK_LULU}\n",
    "## 人物 · 噜妹\n",
    "- 娇小灵动的奶黄色圆润毛绒女孩，比噜噜略矮半头，头戴白色荷叶花边软帽，帽顶长出一株翠绿小嫩芽。",
    "- 本集造型：浅樱花粉连衣裙，裙摆正面绣有红色小草莓口袋，笑起来眼睛弯成月牙。",
    "- 识别锚点：奶黄色毛绒圆脸、白色荷叶边绿芽软帽、浅粉草莓口袋连衣裙。",
    "- 画面代称：Lumei",
    "- 声音参考：设定集/voices/ref_lumei_clean.flac（F5-TTS + Seed-VC 44.1kHz 克隆参考干声）",
    f"- 连续性锁：LOCK-LUMEI-PLUSH《噜妹奶黄嫩芽粉裙造型》（镜头：{char_shot_ids}；图片提示词项：IMG-LUMEI-SHEET）· 锁面：{LOCK_LUMEI}\n",
]
for pl in places:
    vis_lines.append(f"## 地点 · {pl}\n")
    vis_lines.append(f"- 3D 微缩毛毡木艺自然风景与温馨人文空间锚点：{pl}，保持统一柔光体积雾与细腻材质肌理。")
    vis_lines.append(f"- 识别锚点：{pl}标志性建筑/自然地貌与当幕色温一致。\n")

(EP / "视觉设定.md").write_text("\n".join(vis_lines), encoding="utf-8")

# 3. 图片提示词.md
img_lines = [
    "# EP001 图片提示词\n",
    "## IMG-LULU-SHEET · 噜噜角色设定板\n",
    "- 用途：锁定噜噜跨 12 个角色镜头的 3D 毛毡材质、身高比例与头顶小橘子造型。",
    "- 参考：REF-CHAR-PAIR（顺序：1）· 设定集/characters/fullbody_pair_ref.jpg《噜噜噜妹3D全身基准图》（用途：身份；控制：脸型、头身比、毛毡质感；不得控制：背景）。\n",
    "### 可复制提示词",
    f"> Full-body 3D soft plush felt character turnaround sheet of {LOCK_LULU}, front and three-quarter views on a clean warm studio ground, adorable round snout, expressive dark eyes, tactile plush fabric fuzz, soft cinematic key light, no text, no logo.\n",
    "## IMG-LUMEI-SHEET · 噜妹角色设定板\n",
    "- 用途：锁定噜妹跨 12 个角色镜头的奶黄毛绒脸型、白色嫩芽花边帽与粉色草莓裙。",
    "- 参考：REF-CHAR-PAIR（顺序：1）· 设定集/characters/fullbody_pair_ref.jpg《噜噜噜妹3D全身基准图》（用途：身份；控制：脸型、头身比、服饰细节；不得控制：背景）。\n",
    "### 可复制提示词",
    f"> Full-body 3D soft plush felt character turnaround sheet of {LOCK_LUMEI}, front and three-quarter views on a clean warm studio ground, adorable round snout, expressive sparkling eyes, tactile plush fabric fuzz, soft cinematic key light, no text, no logo.\n",
]
for s in SHOTS:
    img_id = f"IMG-S{s['idx']:02d}-PLATE"
    img_lines.append(f"## {img_id} · {s['title']}关键帧母版\n")
    img_lines.append(f"- 用途：作为 {s['id']} 的 9:16 冻结起始帧与空间光色锚点。")
    if s["kind"] == "character":
        img_lines.append(
            "- 参考：REF-CHAR-ID（顺序：1）· 设定集/characters/fullbody_pair_ref.jpg《噜噜噜妹3D全身基准图》（用途：身份；控制：双人角色外观与比例；不得控制：场景地貌）。\n"
        )
    else:
        img_lines.append("- 参考：无外部参考；保持全片统一吉卜力/皮克斯 3D 微缩毛毡风景质感。\n")
    img_lines.append("### 可复制提示词")
    img_lines.append(f"> {s['kf_prompt']}\n")

(EP / "图片提示词.md").write_text("\n".join(img_lines), encoding="utf-8")

# 4. 分镜.md
sb_lines = ["# EP001 分镜\n"]
for sc_id, sc_title, s_nums in scenes_meta:
    sb_lines.append(f"## 场景站位 · {sc_id} · {sc_title}")
    sb_lines.append("- 固定锚点：自然远景天际线与主光源方向恒定；双人同框时保持正面或四分之三朝向镜头，轴线稳定不跳轴")
    sb_lines.append("- 人物：噜噜居左或主护持位，噜妹居右或互动位；纯风景空镜无人物入画以留出呼吸感")
    sb_lines.append("- 轴线：噜噜 ↔ 噜妹（双人正面弧形机位）；working side：朝向镜头暖光侧")
    sb_lines.append("- 变化：随破晓、晴昼、午后晴雨、落日黄昏至星河长夜平滑递进\n")

for s in SHOTS:
    img_id = f"IMG-S{s['idx']:02d}-PLATE"
    kf_rel = f"设定集/keyframes/s{s['idx']:02d}.jpg"
    sb_lines.append(f"## {s['id']} · {s['title']}\n")
    sb_lines.append(f"- 来源：{s['scene_id']}")
    sb_lines.append("- 时长：4s")
    sb_lines.append(f"- 目的：{s['purpose']}")
    sb_lines.append(f"- 景别/机位：9:16 竖屏{'大远景纯风景镜头' if s['kind']=='landscape' else '双人互动景别'}。")
    sb_lines.append(f"- 运镜：{s['camera']}")
    sb_lines.append(f"- 起点：{s['start_state']}")
    sb_lines.append(f"- 唯一动作：{s['action']}")
    sb_lines.append(f"- 终点：{s['end_state']}")
    if s["kind"] == "character":
        sb_lines.append(
            f"- 图片提示词项：IMG-LULU-SHEET《噜噜角色设定板》（控制：身份、造型）；IMG-LUMEI-SHEET《噜妹角色设定板》（控制：身份、造型）；{img_id}《{s['title']}关键帧母版》（控制：构图、光色）。"
        )
        sb_lines.append(
            f"- 视觉依据：《视觉设定.md》·人物「噜噜」（控制：身份、本集造型）；人物「噜妹」（控制：身份、本集造型）；地点「{s['place']}」（控制：空间地理与光色）。"
        )
    else:
        sb_lines.append(f"- 图片提示词项：{img_id}《{s['title']}关键帧母版》（控制：地貌构图、大气光效）。")
        sb_lines.append(f"- 视觉依据：《视觉设定.md》·地点「{s['place']}」（控制：自然地貌、光影氛围）。")
    sb_lines.append(
        f"- 输入参考图：REF-KF-{s['idx']:02d}（顺序：1）· {kf_rel}《{s['title']}起始帧》（用途：起始帧；控制：构图、地理、造型状态；不得控制：无）。"
    )
    sb_lines.append(f"- 声音：{'画外独白' if s['voice_mode']=='VO' else '角色同期对白'}（{s['speaker']}）配自然环境声与治愈钢琴弦乐铺底。\n")
    sb_lines.append("### 冻结关键帧提示词")
    sb_lines.append(f"> {s['kf_prompt']}\n")

(EP / "分镜.md").write_text("\n".join(sb_lines), encoding="utf-8")

# 5. 视频提示词.md
vp_lines = ["# EP001 视频提示词\n"]
for s in SHOTS:
    kf_rel = f"设定集/keyframes/s{s['idx']:02d}.jpg"
    ref_line = f"REF-KF-{s['idx']:02d}（顺序：1）· {kf_rel}《{s['title']}起始帧》（用途：起始帧；控制：构图、地理、造型状态；不得控制：无）。"
    vp_lines.append(f"## {s['motion_id']} · {s['title']}\n")
    vp_lines.append(f"- 分镜：{s['id']}")
    vp_lines.append("- 时长：4s")
    vp_lines.append("- 生成方式：图生视频")
    vp_lines.append(f"- 输入参考图：{ref_line}")
    vp_lines.append(f"- 静态视觉锚点：{s['kf_prompt']}")
    vp_lines.append(f"- 起始帧：{s['start_state']}")
    vp_lines.append(f"- 状态链：{s['start_state']} → {s['action']} → {s['end_state']}")
    vp_lines.append(f"- 终点：{s['end_state']}\n")
    vp_lines.append("### 可复制提示词")
    vp_lines.append(f"> {s['motion_prompt']} No subtitles, captions or text overlays at any moment, no watermark.\n")

(EP / "视频提示词.md").write_text("\n".join(vp_lines), encoding="utf-8")

# Save structured manifest for Colab T4 Voice Cloner + Kaggle Dual-T4 Video Diffuser + Master 60s Assembler
manifest = {
    "title": "山海寻光记：赴一场四季星河",
    "episode": "EP001",
    "target_duration_sec": 60.0,
    "fps": 24,
    "width": 1080,
    "height": 1920,
    "gen_width": 512,
    "gen_height": 896,
    "gen_frames": 97,
    "num_inference_steps": 26,
    "guidance_scale": 4.5,
    "intra_act_xfade_frames": 6,   # 0.250s soft filmic dissolve
    "inter_act_xfade_frames": 12,  # 0.500s act transition dissolve
    "sdxl_night_plates": {
        "13": {
            "prompt": SHOTS[12]["kf_prompt"],
            "seed": 202613,
        },
        "15": {
            "prompt": SHOTS[14]["kf_prompt"],
            "seed": 202615,
        },
    },
    "shots": SHOTS,
}
(PROJ / "episode_manifest_60s.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print("Generated all 5 Creator-First documents + episode_manifest_60s.json!")
