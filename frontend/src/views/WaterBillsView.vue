<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import api from '../api'

const route = useRoute()

const greenhouses = ref([])
const bills = ref([])
const cycles = ref([])
const reconcileRows = ref([])
const error = ref('')
const notice = ref('')
const loading = ref(false)

const filterGreenhouseId = ref(
  route.query.greenhouseId ? Number(route.query.greenhouseId) : ''
)

function currentMonth() {
  const d = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}`
}

const form = reactive({
  greenhouseId: filterGreenhouseId.value || '',
  periodMonth: currentMonth(),
  pricePerLiter: 0.006,
})

const selectedId = ref(null)
const selected = ref(null)
const attachIds = ref([])

const greenhouseMap = computed(() => {
  const m = {}
  greenhouses.value.forEach((g) => (m[g.id] = g.name))
  return m
})

function extractError(e, fallback) {
  const d = e.response?.data
  if (!d) return fallback
  if (d.detail) return d.detail
  return Object.entries(d)
    .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join('；') : v}`)
    .join('；')
}

async function loadGreenhouses() {
  const { data } = await api.get('/greenhouses/')
  greenhouses.value = data.results || data
  if (!form.greenhouseId && greenhouses.value.length) {
    form.greenhouseId = greenhouses.value[0].id
  }
}

async function loadBills() {
  const params = {}
  if (filterGreenhouseId.value) params.greenhouseId = filterGreenhouseId.value
  const { data } = await api.get('/water-bills/', { params })
  bills.value = data.results || data
}

async function loadCycles() {
  const { data } = await api.get('/irrigation-cycles/')
  cycles.value = data.results || data
}

async function loadReconcile() {
  const { data } = await api.get('/water-fee-reconcile/')
  reconcileRows.value = data.results || []
}

async function refreshAll() {
  await Promise.all([loadBills(), loadCycles(), loadReconcile()])
  if (selectedId.value) await loadDetail(selectedId.value)
}

async function loadDetail(id) {
  selectedId.value = id
  attachIds.value = []
  const { data } = await api.get(`/water-bills/${id}/`)
  selected.value = data
}

function clearSelection() {
  selectedId.value = null
  selected.value = null
  attachIds.value = []
}

const billedCycleIds = computed(() => new Set(cycles.value.filter((c) => c.billItemId).map((c) => c.id)))

const attachableCycles = computed(() => {
  if (!selected.value) return []
  const attached = new Set(selected.value.items.map((i) => i.irrigationCycleId))
  return cycles.value.filter(
    (c) =>
      c.greenhouseId === selected.value.greenhouseId &&
      !attached.has(c.id) &&
      !billedCycleIds.value.has(c.id)
  )
})

async function createBill() {
  error.value = ''
  notice.value = ''
  try {
    const { data } = await api.post('/water-bills/', {
      greenhouseId: Number(form.greenhouseId),
      periodMonth: form.periodMonth,
      pricePerLiter: form.pricePerLiter,
    })
    notice.value = '分摊单已创建'
    filterGreenhouseId.value = Number(form.greenhouseId)
    await loadBills()
    await loadCycles()
    await loadDetail(data.id)
  } catch (e) {
    error.value = extractError(e, '创建分摊单失败')
  }
}

async function attach() {
  if (!selected.value || !attachIds.value.length) return
  error.value = ''
  try {
    const { data } = await api.post(
      `/water-bills/${selected.value.id}/items/`,
      { irrigationCycleIds: attachIds.value.map(Number) }
    )
    selected.value = data
    attachIds.value = []
    await Promise.all([loadBills(), loadCycles(), loadReconcile()])
  } catch (e) {
    error.value = extractError(e, '挂入轮灌失败')
  }
}

async function removeItem(item) {
  error.value = ''
  try {
    const { data } = await api.post(
      `/water-bills/${selected.value.id}/items/${item.id}/remove/`
    )
    selected.value = data
    await Promise.all([loadBills(), loadCycles(), loadReconcile()])
  } catch (e) {
    error.value = extractError(e, '移除明细失败')
  }
}

async function closeBill() {
  if (!confirm('封账后不可再挂轮灌、不可修改或删除，确认封账？')) return
  error.value = ''
  try {
    const { data } = await api.post(`/water-bills/${selected.value.id}/close/`)
    selected.value = data
    await Promise.all([loadBills(), loadReconcile()])
    notice.value = '封账成功'
  } catch (e) {
    if (e.response?.status === 409) {
      error.value = extractError(
        e,
        '封账条件不满足：至少两笔轮灌，且总水量为正'
      )
    } else {
      error.value = extractError(e, '封账失败')
    }
  }
}

async function removeBill(bill) {
  if (!confirm('确认删除该未封账分摊单？挂入的轮灌将释放。')) return
  error.value = ''
  try {
    await api.delete(`/water-bills/${bill.id}/`)
    if (selectedId.value === bill.id) clearSelection()
    await refreshAll()
  } catch (e) {
    error.value = extractError(e, '删除失败')
  }
}

function statusLabel(s) {
  return { scheduled: '已排程', running: '进行中', done: '已完成', skipped: '已跳过' }[s] || s
}

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    await loadGreenhouses()
    if (filterGreenhouseId.value) form.greenhouseId = filterGreenhouseId.value
    await Promise.all([loadBills(), loadCycles(), loadReconcile()])
  } catch {
    error.value = '加载水费分摊数据失败'
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>灌溉水费分摊</h1>
        <p>按温室与账期月生成分摊单，挂入多笔轮灌，封账后汇总费用</p>
      </div>
      <div class="actions">
        <label style="margin:0">
          温室筛选
          <select v-model="filterGreenhouseId" @change="loadBills">
            <option value="">全部温室</option>
            <option v-for="g in greenhouses" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
        </label>
      </div>
    </div>

    <div class="panel">
      <h3 style="margin-top:0">费率与封账规则</h3>
      <ul style="margin:6px 0 0; padding-left:20px; color:var(--muted); font-size:.9rem; line-height:1.8">
        <li>每升单价在建单时设定，总费用 = 总升数 × 每升单价（四舍五入到分，误差 ≤ 0.01）。</li>
        <li>同一温室同一账期月（形如 2026-09）只能有一张分摊单。</li>
        <li>仅可挂入本温室分区下的轮灌，一笔轮灌只能挂在一张未封账单上。</li>
        <li><strong>封账条件</strong>：至少两笔轮灌，且各轮灌水量加总为正；否则返回 409，封账时刻保持为空。</li>
        <li>封账后禁止再挂/移除轮灌，也不可修改或删除账单。</li>
      </ul>
    </div>

    <p v-if="error" class="error">{{ error }}</p>
    <p v-if="notice" class="hint" style="color:var(--leaf-deep)">{{ notice }}</p>

    <div class="panel">
      <h3 style="margin-top:0">新建分摊单</h3>
      <div class="form-grid">
        <label>
          所属温室
          <select v-model="form.greenhouseId">
            <option v-for="g in greenhouses" :key="g.id" :value="g.id">{{ g.name }}</option>
          </select>
        </label>
        <label>账期月<input v-model="form.periodMonth" type="month" required /></label>
        <label>
          每升单价（元/升）
          <input v-model.number="form.pricePerLiter" type="number" step="0.0001" min="0" />
        </label>
      </div>
      <div class="actions" style="margin-top:12px">
        <button class="btn" @click="createBill">生成分摊单</button>
      </div>
    </div>

    <div class="panel">
      <h3 style="margin-top:0">分摊单列表</h3>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>所属温室</th>
            <th>账期月</th>
            <th>每升单价</th>
            <th>明细数</th>
            <th>总升数 (L)</th>
            <th>总费用 (元)</th>
            <th>状态</th>
            <th>封账时刻</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in bills" :key="b.id">
            <td>{{ b.id }}</td>
            <td>{{ b.greenhouseName }}</td>
            <td>{{ b.periodMonth }}</td>
            <td>{{ b.pricePerLiter }}</td>
            <td>{{ b.itemCount }}</td>
            <td>{{ b.totalLiters }}</td>
            <td>{{ b.totalFee }}</td>
            <td>
              <span class="badge" :class="b.closedAt ? 'done' : 'growing'">
                {{ b.closedAt ? '已封账' : '未封账' }}
              </span>
            </td>
            <td>{{ b.closedAt ? new Date(b.closedAt).toLocaleString() : '—' }}</td>
            <td class="actions">
              <button class="btn ghost" @click="loadDetail(b.id)">
                {{ selectedId === b.id ? '刷新详情' : '详情/挂单' }}
              </button>
              <button v-if="!b.closedAt" class="btn danger" @click="removeBill(b)">删除</button>
            </td>
          </tr>
          <tr v-if="!bills.length">
            <td colspan="10" style="text-align:center; color:var(--muted)">暂无分摊单</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="selected" class="panel">
      <div class="page-head" style="margin-bottom:12px">
        <div>
          <h3 style="margin:0">
            分摊单 #{{ selected.id }} · {{ selected.greenhouseName }} · {{ selected.periodMonth }}
          </h3>
          <p style="margin:4px 0 0">
            单价 {{ selected.pricePerLiter }} 元/升 ·
            总升数 {{ selected.totalLiters }} L ·
            总费用 <strong>{{ selected.totalFee }}</strong> 元 ·
            <span class="badge" :class="selected.closedAt ? 'done' : 'growing'">
              {{ selected.closedAt ? '已封账' : '未封账' }}
            </span>
          </p>
        </div>
        <div class="actions">
          <button class="btn ghost" @click="clearSelection">收起详情</button>
          <button v-if="!selected.closedAt" class="btn" @click="closeBill">封账</button>
        </div>
      </div>

      <table>
        <thead>
          <tr>
            <th>明细ID</th>
            <th>轮灌编号</th>
            <th>分区</th>
            <th>起灌时间</th>
            <th>水量 (L)</th>
            <th>轮灌状态</th>
            <th v-if="!selected.closedAt">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in selected.items" :key="item.id">
            <td>{{ item.id }}</td>
            <td>{{ item.irrigationCycleId }}</td>
            <td>{{ item.zoneCode }}</td>
            <td>{{ new Date(item.startAt).toLocaleString() }}</td>
            <td>{{ item.waterLiters }}</td>
            <td><span class="badge" :class="item.status">{{ statusLabel(item.status) }}</span></td>
            <td v-if="!selected.closedAt">
              <button class="btn danger" @click="removeItem(item)">移除</button>
            </td>
          </tr>
          <tr v-if="!selected.items.length">
            <td :colspan="selected.closedAt ? 6 : 7" style="text-align:center; color:var(--muted)">
              暂无明细
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="!selected.closedAt" style="margin-top:14px">
        <label>
          挂入轮灌（仅限本温室分区、尚未挂单的轮灌，可多选）
          <select v-model="attachIds" multiple style="min-height:110px">
            <option v-for="c in attachableCycles" :key="c.id" :value="c.id">
              #{{ c.id }} · {{ c.zoneCode }} · {{ new Date(c.startAt).toLocaleString() }}
              · {{ c.waterLiters }} L · {{ statusLabel(c.status) }}
            </option>
          </select>
        </label>
        <div class="actions" style="margin-top:10px">
          <button class="btn secondary" :disabled="!attachIds.length" @click="attach">
            挂入选中轮灌（{{ attachIds.length }}）
          </button>
          <span v-if="!attachableCycles.length" class="hint">没有可挂入的空闲轮灌</span>
        </div>
      </div>
    </div>

    <div class="panel">
      <h3 style="margin-top:0">费用对账（按温室汇总）</h3>
      <table>
        <thead>
          <tr>
            <th>温室</th>
            <th>账单数</th>
            <th>总升数 (L)</th>
            <th>温室汇总费用 (元)</th>
            <th>各单合计 (元)</th>
            <th>差额</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in reconcileRows" :key="r.greenhouseId">
            <td>{{ r.greenhouseName }}</td>
            <td>{{ r.billCount }}</td>
            <td>{{ r.totalLiters }}</td>
            <td>{{ r.greenhouseTotalFee }}</td>
            <td>{{ r.billsTotalFee }}</td>
            <td>{{ r.diff }}</td>
          </tr>
          <tr v-if="!reconcileRows.length">
            <td colspan="6" style="text-align:center; color:var(--muted)">暂无账单</td>
          </tr>
        </tbody>
      </table>
      <p class="hint">温室汇总费用 = 各分摊单“总升数 × 每升单价（保留两位）”之和，与各单合计差额不超过 0.01。</p>
    </div>
  </div>
</template>
