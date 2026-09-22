# ShadeCanopy-01 · 分区气候日志、轮灌计划与灌溉水费分摊

温室「分区气候日志与轮灌计划」全栈种子项目（非考勤 OA、非库存），含按温室的灌溉水费分摊与封账。

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

启动时 `entrypoint.sh` 会执行 `migrate` + `seed_data` 自动写入账号与示例业务数据。水费分摊种子覆盖四种场景：**已封账单**（g1 上月，2 笔正水量）、**可封账单**（g1 当月，2 笔正水量）、**不可封·总水量为零**（g2 当月，2 笔但合计 0 L）、**不可封·不足两笔**（g2 上月，仅 1 笔）。

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
6. **WaterBill（灌溉水费分摊单）**：greenhouseId / periodMonth / pricePerLiter / closedAt（可空）；同温室同账期月唯一
7. **WaterBillItem（分摊明细）**：分摊单编号 + 轮灌编号；轮灌所属分区必须属于该温室，一笔轮灌只能挂在一张未封账单上
8. **Dashboard**：温室数、growing 分区数、近 24h 气候日志数、今日 scheduled 轮灌数 → `GET /api/dashboard/`

### 水费费率与封账条件

- **费率公式**：`总费用 = 总升数 × 每升单价`，四舍五入保留到分（0.01 元），与精确值误差不超过 0.01。每升单价建单时设定，精度 4 位小数（如 0.0060 元/升）。
- **账期月**：形如 `2026-09` 的 `YYYY-MM`；同一温室同一账期月只能有一张分摊单。
- **挂明细**：仅能挂入本温室分区下的轮灌；一笔轮灌全库最多挂在一张分摊单上；已封账单禁止再挂/移除。
- **封账条件**（`POST /api/water-bills/{id}/close/`）：账单内**至少两笔轮灌**，且**各轮灌水量加总须为正**（> 0）。任一不满足返回 **409 Conflict**，`closedAt` 保持为空。封账后账单不可再挂明细、不可修改或删除。
- **费用对账**（`GET /api/water-fee-reconcile/`）：按温室汇总 `greenhouseTotalFee`（各单总费用之和），与各单合计 `billsTotalFee` 的差额 `diff` 不超过 0.01。

## API 一览

| 方法 | 路径 |
| --- | --- |
| POST | `/api/auth/token/` |
| POST | `/api/auth/token/refresh/` |
| GET | `/api/auth/me/` |
| CRUD | `/api/greenhouses/` |
| CRUD | `/api/zones/?greenhouseId=&status=` |
| CRUD | `/api/climate-logs/?zoneId=` |
| CRUD | `/api/irrigation-cycles/?zoneId=&status=` |
| CRUD | `/api/water-bills/?greenhouseId=&periodMonth=&closed=true\|false` |
| POST | `/api/water-bills/{id}/items/`（挂入轮灌，body: `{"irrigationCycleIds":[1,2]}`） |
| POST | `/api/water-bills/{id}/items/{itemId}/remove/`（移除明细，仅未封账） |
| POST | `/api/water-bills/{id}/close/`（封账；条件不满足 409 且 closedAt 保持空） |
| GET | `/api/water-fee-reconcile/`（按温室汇总总费用，与各单合计核对差额 ≤ 0.01） |
| GET | `/api/dashboard/` |

字段对外使用 camelCase（如 `areaM2`、`zoneCode`、`humidityPct`）。

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
│   └── core/              # 温室/分区/气候/轮灌 + seed_data
└── frontend/
    ├── Dockerfile
    ├── nginx.conf         # 静态资源 + /api 反代
    ├── package.json
    └── src/               # Vue 页面（叶绿/土色主题）
```

## 配色说明

前端采用叶绿（`#3d6b3a`）与土色（`#8b6b45`）主色，米色底与侧栏深绿渐变，贴近温室场景。
