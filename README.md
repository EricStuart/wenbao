# wenbao

# 观迹 · 中国国保地图

手机地图界面，采用透明模糊、圆角悬浮控件与底部抽屉。主屏保留地图、圆形搜索、地区/类型/时代/批次标签与筛选入口。底部不再显示详情卡片和说明文字：左下角数字按钮显示当前筛选条件下的总数（含待定位记录），缩放、平移不会改变该数字；点击打开同一筛选结果名录。地名层级位于数字下方，可逐级返回。点击具体文物标记直接打开图文介绍，“在地图上查看”进入街道地图。

筛选面板采用手机尺寸的圆角选择框，点击打开标签面板，选择后返回筛选面板。地图支持全国→省→市→县→文物位置，每一级显示对应边界；长名称完整换行。桌面容器宽430px，手机占满可视区域。

全国重点文物保护单位浏览网站。纯静态 HTML / CSS / JavaScript，自带 ECharts、Leaflet 和行政边界，无运行时密钥或构建步骤。

## 本地预览

在本目录执行 `python -m http.server 8765 --bind 127.0.0.1 --directory dist`，访问 http://127.0.0.1:8765 。

## 数据

- 原始数据位于 `sources/`；核对依据为 `research_sources.json`。
- `python fetch_boundaries.py` 缓存31省、329市的GeoJSON并重建行政区划索引，县界从所属市文件提取。浏览行政边界不依赖外部网络；文物周边街道底图使用按需加载的 OpenStreetMap 在线瓦片，遵循浏览器缓存和可见署名，不预取、不批量下载。
- `node --test geo-model.test.cjs` 验证层级与边界逻辑。
- `python prepare_data.py` 重建 `dist/data/heritage.json`、`dist/data/research.json` 和 `data-audit.json`。
- 数据核对日期：2026-11-06；覆盖八批及已核对的增补、单列与合并记录。
- 5,058 条整理记录；5,016 条有第三方参考点位；4,756 条可解析城市；3,709 条可解析单一区县。
- 未取得坐标的 42 条保留在名录中，不以行政中心冒充真实地点。线性、多子项文物的单点不等于完整范围。行政区划基于地址匹配，历史地址可能与现行区划不同。
- 5056 + 3 − 1 的修正是对已发现差额的核对，不是对所有历次名称、扩展子项、合并或撤销的完整审计。
- 地理点来自 Atlas of China 与 ArcGIS 公开数据，未经逐点实地核验。不得用于边界、保护范围认定或精确导航。
- 类型统一为六类并保留原始类别；时代标签按文本规则提取，范围年代不保证覆盖中间全部朝代。

## 本地维基百科图文

- 采集工具依赖可安装到项目内：`python -m pip install --target sources/wiki-deps -r requirements-wikipedia.txt`。网站本身仍是无需 Python 依赖的静态页面。
- `python fetch_wikipedia.py --search-missing` 批量收录中文维基百科导言和 Commons 配图；使用断点缓存、默认3个下载线程与限流退避。`--workers` 控制并发，`--deep-search` 可追加逐条全文检索。`--limit 10` 仅用于小范围试运行，会重写当次汇总，因此完整收录后不要再用它覆盖汇总。
- `python complete_wikipedia_images.py --commons` 继续从对应百科正文、Wikidata 的 P18 配图及维基共享资源搜索补图；共享资源搜索同时核对名称与所在地。默认2个线程，可从缓存继续；`--commons-only` 可用于单独重跑共享资源检索。
- `python complete_wikipedia_categories.py` 可补查 Wikidata 明确关联的文物专属相册，跳过已识别的村落集合和考古文化相册。相册关联仍需抽查，不能仅凭 Wikidata 关联判断每张照片都属于该处文物。
- 前两步结束后运行 `python enrich_wikipedia_text.py`，为少于80字的百科导言补入同一引用版本的正文段落，过滤参考文献、图片代码和表格，并保留版本链接。`--prepare-only` 可先缓存正文而不修改详情文字。
- 文字和来源保存在 `dist/data/wikipedia/<文物ID>.json`；实际图片文件保存在 `dist/assets/wikipedia/`，详情页不直接请求维基百科或远程图片。
- API 原始响应缓存位于 `sources/wiki-cache/`；汇总见 `dist/data/wikipedia/index.json`，采集与未匹配记录见 `wikipedia-audit.json`，补图结果见 `wikipedia-images-audit.json`。
- 同名条目结合所在地和参考坐标匹配，并处理括号别名、地名修饰、长城分段和“造象／造像”等写法；拒绝歧义页、目录页、明显异地和同市不同区县的冲突。自动匹配不等于逐条人工审校。
- `python recover_wikipedia_redirects.py` 应用 `sources/wikipedia-overrides.json` 中逐项复核的别名对应关系，处理旧行政区名称或百科重定向导致的漏收；例外仅对指定标题和已核对的版本生效，不放宽其他记录的自动匹配。寺庙中的特定塔、殿等子项另行核对配图主体。
- 图片不直接采用百科页面的全部图片列表：导航模板里的通用标志、地图和其他文物图片会被排除；正文配图须核对名称和市县。已知同名及误图的复核结果保存在 `sources/wikipedia-overrides.json`；剔除与文字修订记录分别见 `wikipedia-rejected-images.json`、`wikipedia-editorial-audit.json`。
- 5,058条记录均有本地文字。未匹配到可靠百科条目的记录，依据已有公布名录中的所在地、时代、类型和批次生成基础简介，单独标为“名录简介／公布名录”，不编造历史叙述或冒充维基百科来源。
- 2026-11-06 本轮收录：4,085条百科介绍、973条名录基础简介；2,435条有本地配图（2,433个独立图片文件），2,623条尚未取得可靠配图。全量文件、署名与已知图片主体限制检查通过；这不代表所有文字或图片已经逐条人工审定。
- 2026-11-09 补充后：4,129条百科介绍、929条名录基础简介；2,452条有本地配图，2,606条仍待配图。为545条已有百科介绍及8条新匹配介绍补充了同一版本正文；20条存在批次、年份或文本格式疑点的正文扩充未采用。
- `python update_missing_wikipedia.py` 可批量检索缺失百科介绍和已复核条目的图片；`--photos-only` 只补查图片。`python curate_wikipedia_update.py` 保存经人工核对的组合文物子项。需先运行 `python enrich_wikipedia_text.py --prepare-only --minimum 80 --maximum 150 --exact-title` 生成候选，再运行 `python apply_wikipedia_expansions.py` 应用冲突检查通过的正文。过程及跳过记录见 `wikipedia-update-*-audit.json`。
- 百科介绍保存页面标题、版本号、永久链接、收录时间和 CC BY-SA 4.0 文字许可；图片保存 Commons 文件页、作者和该文件的许可。仅在取得可靠配图后显示照片，缺图明确标注；不会用通用风景图替代。下载采用来源接口返回的标准移动端缩略图，保留原图链接供追溯，响应类型通过检查后才写入本地。
- `python audit_wikipedia.py` 检查全部本地文字、来源署名、图片引用与文件头，更新覆盖汇总及 `wikipedia-coverage-audit.json`；实际剩余缺图列在该文件的 `missingPhotos` 中。
- `python -m unittest test_wikipedia.py test_wikipedia_text.py test_wikipedia_images.py -v` 验证同名异地、区县冲突、歧义页、别名匹配、文本截取、正文清洗、模板图片排除及署名清洗。

## 来源与署名

- 名录与部分坐标：Atlas of China — https://www.atlasofchina.com/data/ ，CC BY 4.0。本项目补录、归并并整理字段。
- 坐标补充：https://www.arcgis.com/home/item.html?id=77373750e26d4d24a7e38fd9fcce2900
- 省市县轮廓：https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json
- 街道底图：https://www.openstreetmap.org/copyright · https://operations.osmfoundation.org/policies/tiles/
- Leaflet 1.9.4：https://leafletjs.com/ （BSD-2-Clause）
- 行政区划：https://github.com/modood/Administrative-divisions-of-China
- 八批与调整原文逐条保留在网站及研究文件中。

## 验证

数据生成器检查总数、唯一 ID、坐标范围。6项层级测试通过：31省导航、山西/忻州/五台县真实独立边界、内蒙古与北京市直辖区、省直辖县级组、包含未定位记录的聚合计数、文物坐标聚焦和逐级返回。390×844浏览器已实际点击全国→山西530条→忻州36条→五台县12条→佛光寺；已查看真实街道底图、比例尺及版权署名，逐级返回恢复12/36/530/5058条，无控制台错误。

未匹配的市县边界明确降级为参考点位，地址待核对的条目仍保留在名录；边界快照和历史地址并非现行行政区划的全面审计。街道服务需要联网，加载失败时标记与详情仍可使用。

## 发布

当前按用户选择使用本地预览，服务运行于127.0.0.1:8765；本次层级改动未同步到在线部署。

由 Sites 工作流读取 `.openai/hosting.json` 发布 `dist/`。网站初始为仅所有者访问，不自动对公众开放。
