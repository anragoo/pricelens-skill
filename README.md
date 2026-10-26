# PriceLens Skill

PriceLens 多平台比价与购物推荐技能，支持按需求筛选商品、核对规格、比较当前价格，并提供可点击的 PriceLens 商品链接。当前版本为 **3.4.6**。

## 安装到 WorkBuddy

需要 Python 3.11 或更新版本，客户端只使用 Python 标准库。

```sh
git clone https://github.com/anragoo/pricelens-skill.git
cd pricelens-skill
mkdir -p ~/.workbuddy/skills/pricelens/scripts
cp SKILL.md _meta.json ~/.workbuddy/skills/pricelens/
cp scripts/pricelens.py ~/.workbuddy/skills/pricelens/scripts/
```

刷新 WorkBuddy 的技能列表或重启应用后即可使用。其他支持 `SKILL.md` 和 Python 脚本的助手，可按对应应用的技能安装方式安装。

## 文件结构

- `SKILL.md`：通用选品、比价、优惠说明和推荐展示规则。
- `scripts/pricelens.py`：调用 PriceLens 服务的客户端，支持多平台和多商品并行查询。
- `_meta.json`：技能元数据。
- `tests/`：可独立运行、不访问真实商品接口的客户端测试。

## 命令行使用

将“商品关键词”替换为需要查询的商品名称、型号和关键规格：

```sh
python3 scripts/pricelens.py search --keyword "商品关键词" --source jd pdd taobao douyin vip kuaishou
python3 scripts/pricelens.py search --keyword "商品关键词" --source jd --min-price 100 --max-price 500
python3 scripts/pricelens.py detail --id "搜索返回的商品ID"
python3 scripts/pricelens.py detail --id "商品ID1" "商品ID2"
```

默认连接 `https://1zlheidou.cn/pricelens`。可通过 `PRICELENS_API_URL` 指定兼容的 PriceLens 服务地址；服务要求鉴权时，通过 `PRICELENS_API_TOKEN` 配置自己的访问令牌，不要提交令牌到仓库。

## 使用说明

- 本仓库开源的是技能和客户端，使用时需要连接可用的 PriceLens 服务；MIT 许可不代表承诺服务永久免费或持续可用。
- 查询结果只代表本次找到的商品，不代表全部库存或全网最低价。
- 价格、库存和优惠条件可能变化，以下单页面为准。
- 商品链接可能为 PriceLens 服务带来推广佣金。
- 手机能否打开购物 App 取决于商品链接和使用环境，不保证一定唤起。

## 测试与贡献

```sh
python3 -m unittest discover -s tests
```

欢迎提交 Issue 或 Pull Request。修改后请运行测试；不要在代码、Issue 或日志中提交真实账号、访问令牌等敏感信息。

## 许可证

本仓库的技能、客户端及文档采用 [MIT License](LICENSE)。服务访问权限与开源代码许可分开管理。
