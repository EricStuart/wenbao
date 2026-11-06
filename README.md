# 观迹 · 中国国保地图

简约的全国重点文物保护单位浏览网站。纯静态 HTML / CSS / JavaScript，自带 ECharts 和地图轮廓，无运行时密钥或构建步骤。

## 本地预览

在本目录执行 `python -m http.server 8765 --bind 127.0.0.1 --directory dist`，访问 http://127.0.0.1:8765 。

## 数据

- 原始数据位于 `sources/`；核对依据为 `research_sources.json`。
- `python prepare_data.py` 重建 `dist/data/heritage.json`、`dist/data/research.json` 和 `data-audit.json`。
- 数据核对日期：2026-11-06；覆盖八批及已核对的增补、单列与合并记录。
- 5,058 条整理记录；5,016 条有第三方参考点位；4,756 条可解析城市；3,709 条可解析单一区县。
- 未取得坐标的 42 条保留在名录中，不以行政中心冒充真实地点。线性、多子项文物的单点不等于完整范围。行政区划基于地址匹配，历史地址可能与现行区划不同。
- 5056 + 3 − 1 的修正是对已发现差额的核对，不是对所有历次名称、扩展子项、合并或撤销的完整审计。
- 地理点来自 Atlas of China 与 ArcGIS 公开数据，未经逐点实地核验。不得用于边界、保护范围认定或精确导航。
- 类型统一为六类并保留原始类别；时代标签按文本规则提取，范围年代不保证覆盖中间全部朝代。

## 来源与署名

- 名录与部分坐标：Atlas of China — https://www.atlasofchina.com/data/ ，CC BY 4.0。本项目补录、归并并整理字段。
- 坐标补充：https://www.arcgis.com/home/item.html?id=77373750e26d4d24a7e38fd9fcce2900
- 省界轮廓：https://geo.datav.aliyun.com/areas_v3/bound/100000_full.json
- 行政区划：https://github.com/modood/Administrative-divisions-of-China
- 首屏影像：https://www.beijing.gov.cn/renwen/bjgk/hrgk/wl/202212/t20221220_2881074.html
- 八批与调整原文逐条保留在网站及研究文件中。

## 验证

数据生成器检查总数、唯一 ID、坐标范围。浏览器人工检查：桌面/390px 手机布局、山西→忻州→五台县联动、佛光寺搜索及详情、零结果与重置、分页、第八批762条筛选、单条 CSV 导出，控制台无错误。原始公告外链并非全部实时可访问；附件链接可能因来源站点变更失效。

## 发布

由 Sites 工作流读取 `.openai/hosting.json` 发布 `dist/`。网站初始为仅所有者访问，不自动对公众开放。
