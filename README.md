# ShadeCanopy-01 · 分区气候日志与轮灌计划

温室「分区气候日志与轮灌计划」全栈种子项目（非考勤 OA、非库存）。

## 技术栈

| 层 | 技术 |
| --- | --- |
| 后端 | Python Django 5 · Django REST Framework · SimpleJWT · django-cors-headers · Gunicorn |
| 前端 | Vue 3 · Vite · Pinia · Vue Router |
| 数据库 | PostgreSQL 15 |
| 部署 | Docker Compose · Nginx（前端容器反代 `/api` → Django） |

## 路径与端口

- **项目路径**：`D:\work\document\bytecode\claudeCodePro\ShadeCanopy\ShadeCanopy-01\`
- **前端**：http://localhost:3500
- **后端 API**：http://localhost:8500（也可经前端同源 `/api` 访问）
- **PostgreSQL**：localhost:5435

## 演示账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | admin（管理员，可进 Django Admin） |
| `grower` | `123456` | grower（种植员） |

启动时 `entrypoint.sh` 会执行 `migrate` + `seed_data` 自动写入账号与示例业务数据。

## 快速启动

```bash
cd D:\work\document\bytecode\claudeCodePro\ShadeCanopy\ShadeCanopy-01
docker compose up --build
```

浏览器打开 http://localhost:3500 ，使用 `grower` / `123456` 登录。

停止：

```bash
docker compose down
```

## 业务模块

1. **Auth**：JWT `POST /api/auth/token/`，当前用户 `GET /api/auth/me/`
2. **Greenhouse**：name / location / areaM2 / notes
3. **Zone**：greenhouseId / zoneCode / cropName / status(`idle|growing|fallow`)；同温室 zoneCode 唯一
4. **ClimateLog**：zoneId / recordedAt / tempC / humidityPct / parUmol / co2Ppm；**humidityPct ∈ [20, 100]**
5. **IrrigationCycle**：zoneId / startAt / durationMin / waterLiters / status(`scheduled|running|done|skipped`)
6. **WaterShareBill（水费分摊单）**：greenhouseId / billingMonth(`YYYY-MM`) / pricePerLiter / sealedAt(可空)；**同温室同账期月唯一**
7. **WaterShareEntry（分摊明细）**：billId / cycleId；轮灌所属分区必须属于该温室，一笔轮灌只能挂在一张分摊单
8. **Dashboard**：温室数、growing 分区数、近 24h 气候日志数、今日 scheduled 轮灌数 → `GET /api/dashboard/`

## API 一览

| 方法 | 路径 |
| --- | --- |
| POST | `/api/auth/token/` |
| POST | `/api/auth/token/refresh/` |
| GET | `/api/auth/me/` |
| CRUD | `/api/greenhouses/` |
| CRUD | `/api/zones/?greenhouseId=&status=` |
| CRUD | `/api/climate-logs/?zoneId=` |
| CRUD | `/api/irrigation-cycles/?zoneId=&greenhouseId=&status=` |
| CRUD | `/api/water-share-bills/?greenhouseId=&billingMonth=&sealed=` |
| POST | `/api/water-share-bills/{id}/seal/` |
| GET | `/api/water-share-bills/reconcile/?greenhouseId=` |
| GET/POST/DELETE | `/api/water-share-entries/?billId=` |
| GET | `/api/dashboard/` |

字段对外使用 camelCase（如 `areaM2`、`zoneCode`、`humidityPct`）。

## 水费分摊说明

**费率**：每张分摊单记录每升单价 `pricePerLiter`（元/升，4 位小数，≥ 0）。
分摊单详情返回 `entries`（明细）、`totalLiters`（各轮灌水量加总）与 `totalFee`（总费用）：

```
totalFee = totalLiters × pricePerLiter   （四舍五入到分，误差 ≤ 0.01）
```

`GET /api/water-share-bills/reconcile/` 为费用对账接口：按温室汇总总费用
（`totalFee` = 该温室各分摊单 `totalFee` 之和），并给出与各单合计的差值
`diff`，保证不超过 0.01。

**挂账规则**：

- 分摊明细把一笔轮灌（`cycleId`）挂入一张分摊单（`billId`）；
- 轮灌所属分区必须属于该分摊单的温室，否则 400；
- 一笔轮灌只能挂在一张分摊单上，重复挂账返回 400；
- 已封账的分摊单禁止再挂/再拆轮灌，也禁止修改与删除（409）。

**封账条件**（`POST /api/water-share-bills/{id}/seal/`）：

1. 账单至少两笔轮灌；
2. 各轮灌水量加总须为正。

不满足任一条件返回 409 且 `sealedAt` 保持为空；满足则写入封账时刻，封后只读。

**页面入口**：温室管理 → 每行「水费分摊」按钮，进入该温室的分摊页（`/greenhouses/:id/water-shares`）。

**种子数据**：`seed_data` 预置四种形态——可封（两笔正水量轮灌）、不可封（仅一笔轮灌）、
不可封（两笔但水量加总为 0）、已封账（上月账单，演示封后禁止再挂）。

## 本地开发（可选）

**后端**（需本机 Postgres 或已启动 compose 中的 db）：

```bash
cd backend
pip install -r requirements.txt
set POSTGRES_HOST=127.0.0.1
set POSTGRES_PORT=5435
python manage.py migrate
python manage.py seed_data
python manage.py runserver 0.0.0.0:8500
```

**前端**：

```bash
cd frontend
npm install
npm run dev
```

Vite 已将 `/api` 代理到 `http://127.0.0.1:8500`。

## 目录结构

```
ShadeCanopy-01/
├── docker-compose.yml
├── README.md
├── .gitignore
├── backend/
│   ├── Dockerfile
│   ├── entrypoint.sh      # migrate + seed + gunicorn
│   ├── requirements.txt
│   ├── manage.py
│   ├── config/            # settings / urls
│   ├── accounts/          # 自定义 User + role
│   └── core/              # 温室/分区/气候/轮灌/水费分摊 + seed_data
└── frontend/
    ├── Dockerfile
    ├── nginx.conf         # 静态资源 + /api 反代
    ├── package.json
    └── src/               # Vue 页面（叶绿/土色主题）
```

## 配色说明

前端采用叶绿（`#3d6b3a`）与土色（`#8b6b45`）主色，米色底与侧栏深绿渐变，贴近温室场景。
