<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../api'

const route = useRoute()
const router = useRouter()

const greenhouses = ref([])
const greenhouseId = ref(null)
const bills = ref([])
const reconcile = ref(null)
const cycles = ref([])
const attachedCycleIds = ref(new Set())
const selectedId = ref(null)
const error = ref('')
const detailError = ref('')

function currentMonth() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

const billForm = reactive({
  billingMonth: currentMonth(),
  pricePerLiter: 0.0032,
})
const attachCycleId = ref('')

const selectedBill = computed(
  () => bills.value.find((b) => b.id === selectedId.value) || null
)
const availableCycles = computed(() =>
  cycles.value.filter((c) => !attachedCycleIds.value.has(c.id))
)

const cycleStatusLabel = {
  scheduled: '已排程',
  running: '进行中',
  done: '已完成',
  skipped: '已跳过',
}

function fmtErr(e, fallback) {
  const data = e.response?.data
  if (!data) return fallback
  if (typeof data === 'string') return data
  if (data.detail) return data.detail
  return Object.entries(data)
    .map(([k, v]) => `${k}: ${[].concat(v).join('；')}`)
    .join('；')
}

async function loadGreenhouses() {
  const { data } = await api.get('/greenhouses/')
  greenhouses.value = data.results || data
}

async function loadBills() {
  const { data } = await api.get('/water-share-bills/', {
    params: { greenhouseId: greenhouseId.value },
  })
  bills.value = data.results || data
  if (selectedId.value && !bills.value.some((b) => b.id === selectedId.value)) {
    selectedId.value = null
  }
}

async function loadReconcile() {
  const { data } = await api.get('/water-share-bills/reconcile/', {
    params: { greenhouseId: greenhouseId.value },
  })
  reconcile.value = (data.results || data)[0] || null
}

async function loadCycles() {
  const [{ data: cycleData }, { data: entryData }] = await Promise.all([
    api.get('/irrigation-cycles/', { params: { greenhouseId: greenhouseId.value } }),
    api.get('/water-share-entries/'),
  ])
  cycles.value = cycleData.results || cycleData
  const entries = entryData.results || entryData
  attachedCycleIds.value = new Set(entries.map((e) => e.cycleId))
}

async function loadAll() {
  error.value = ''
  try {
    await Promise.all([loadBills(), loadReconcile(), loadCycles()])
  } catch (e) {
    error.value = fmtErr(e, '加载分摊数据失败')
  }
}

function onSwitchGreenhouse() {
  if (String(greenhouseId.value) !== String(route.params.greenhouseId)) {
    router.push({ name: 'water-shares', params: { greenhouseId: greenhouseId.value } })
  }
}

watch(
  () => route.params.greenhouseId,
  async (id) => {
    if (!id) return
    greenhouseId.value = Number(id)
    selectedId.value = null
    await loadAll()
  }
)

async function createBill() {
  error.value = ''
  try {
    await api.post('/water-share-bills/', {
      greenhouseId: greenhouseId.value,
      billingMonth: billForm.billingMonth,
      pricePerLiter: billForm.pricePerLiter,
    })
    billForm.billingMonth = currentMonth()
    await loadAll()
  } catch (e) {
    error.value = fmtErr(e, '创建分摊单失败')
  }
}

async function removeBill(row) {
  if (!confirm(`确认删除 ${row.billingMonth} 的分摊单？明细将一并删除。`)) return
  error.value = ''
  try {
    await api.delete(`/water-share-bills/${row.id}/`)
    await loadAll()
  } catch (e) {
    error.value = fmtErr(e, '删除分摊单失败')
  }
}

function selectBill(row) {
  selectedId.value = row.id
  detailError.value = ''
  attachCycleId.value = ''
}

async function attach() {
  if (!attachCycleId.value) return
  detailError.value = ''
  try {
    await api.post('/water-share-entries/', {
      billId: selectedId.value,
      cycleId: Number(attachCycleId.value),
    })
    attachCycleId.value = ''
    await loadAll()
  } catch (e) {
    detailError.value = fmtErr(e, '挂入轮灌失败')
  }
}

async function detach(entryId) {
  detailError.value = ''
  try {
    await api.delete(`/water-share-entries/${entryId}/`)
    await loadAll()
  } catch (e) {
    detailError.value = fmtErr(e, '移除轮灌失败')
  }
}

async function seal() {
  if (!confirm('确认封账？封账后禁止再挂轮灌，且不可修改。')) return
  detailError.value = ''
  try {
    await api.post(`/water-share-bills/${selectedId.value}/seal/`)
    await loadAll()
  } catch (e) {
    detailError.value = fmtErr(e, '封账失败')
  }
}

onMounted(async () => {
  await loadGreenhouses()
  const fromRoute = Number(route.params.greenhouseId)
  if (fromRoute && greenhouses.value.some((g) => g.id === fromRoute)) {
    greenhouseId.value = fromRoute
  } else if (greenhouses.value.length) {
    greenhouseId.value = greenhouses.value[0].id
    router.replace({
      name: 'water-shares',
      params: { greenhouseId: greenhouseId.value },
    })
  }
  await loadAll()
})
</script>

<template>
  <div>
    <div class="page-head">
      <div>
        <h1>灌溉水费分摊</h1>
        <p>按温室账期月归集轮灌水量，总费用 = 总升数 × 每升单价；封账后固化</p>
      </div>
      <div class="actions">
        <select v-model="greenhouseId" @change="onSwitchGreenhouse">
          <option v-for="g in greenhouses" :key="g.id" :value="g.id">{{ g.name }}</option>
        </select>
      </div>
    </div>

    <div v-if="reconcile" class="stats">
      <div class="stat">
        <div class="label">分摊单数</div>
        <div class="value">{{ reconcile.billCount }}</div>
      </div>
      <div class="stat">
        <div class="label">总升数</div>
        <div class="value">{{ reconcile.totalLiters }} L</div>
      </div>
      <div class="stat">
        <div class="label">汇总总费用</div>
        <div class="value">¥ {{ reconcile.totalFee }}</div>
      </div>
      <div class="stat">
        <div class="label">与各单合计差</div>
        <div class="value">¥ {{ reconcile.diff }}</div>
      </div>
    </div>

    <div class="panel">
      <h3 style="margin-top:0">新建分摊单</h3>
      <div class="form-grid">
        <label>账期月<input v-model="billForm.billingMonth" type="month" /></label>
        <label>
          每升单价 (元)
          <input v-model.number="billForm.pricePerLiter" type="number" step="0.0001" min="0" />
        </label>
      </div>
      <p style="margin:8px 0 0;color:var(--muted)">同一温室同一账期月只能有一张分摊单。</p>
      <p v-if="error" class="error">{{ error }}</p>
      <div class="actions" style="margin-top:12px">
        <button class="btn" @click="createBill">创建分摊单</button>
      </div>
    </div>

    <div class="panel">
      <table>
        <thead>
          <tr>
            <th>账期月</th>
            <th>每升单价</th>
            <th>轮灌笔数</th>
            <th>总升数</th>
            <th>总费用</th>
            <th>状态</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in bills" :key="row.id">
            <td>{{ row.billingMonth }}</td>
            <td>¥ {{ row.pricePerLiter }}/L</td>
            <td>{{ row.entryCount }}</td>
            <td>{{ row.totalLiters }} L</td>
            <td>¥ {{ row.totalFee }}</td>
            <td>
              <span class="badge" :class="row.sealed ? 'done' : 'scheduled'">
                {{ row.sealed ? '已封账' : '未封账' }}
              </span>
            </td>
            <td class="actions">
              <button class="btn ghost" @click="selectBill(row)">明细</button>
              <button v-if="!row.sealed" class="btn danger" @click="removeBill(row)">删除</button>
            </td>
          </tr>
          <tr v-if="!bills.length">
            <td colspan="7" style="text-align:center;color:var(--muted)">暂无分摊单</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-if="selectedBill" class="panel">
      <h3 style="margin-top:0">
        分摊单 #{{ selectedBill.id }} · {{ selectedBill.billingMonth }} 明细
        <span class="badge" :class="selectedBill.sealed ? 'done' : 'scheduled'" style="margin-left:8px">
          {{ selectedBill.sealed ? '已封账' : '未封账' }}
        </span>
      </h3>
      <p v-if="selectedBill.sealed" style="color:var(--muted)">
        封账时刻：{{ new Date(selectedBill.sealedAt).toLocaleString() }}，封账后禁止再挂轮灌。
      </p>
      <table>
        <thead>
          <tr>
            <th>轮灌编号</th>
            <th>分区</th>
            <th>开始时间</th>
            <th>水量</th>
            <th>轮灌状态</th>
            <th v-if="!selectedBill.sealed">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in selectedBill.entries" :key="entry.id">
            <td>#{{ entry.cycleId }}</td>
            <td>{{ entry.zoneCode }}</td>
            <td>{{ new Date(entry.startAt).toLocaleString() }}</td>
            <td>{{ entry.waterLiters }} L</td>
            <td>{{ cycleStatusLabel[entry.cycleStatus] || entry.cycleStatus }}</td>
            <td v-if="!selectedBill.sealed" class="actions">
              <button class="btn danger" @click="detach(entry.id)">移除</button>
            </td>
          </tr>
          <tr v-if="!selectedBill.entries.length">
            <td :colspan="selectedBill.sealed ? 5 : 6" style="text-align:center;color:var(--muted)">
              尚未挂入轮灌
            </td>
          </tr>
        </tbody>
      </table>

      <template v-if="!selectedBill.sealed">
        <div class="form-grid" style="margin-top:12px">
          <label class="full">
            挂入轮灌（仅本温室未挂账的轮灌）
            <select v-model="attachCycleId">
              <option value="" disabled>选择轮灌</option>
              <option v-for="c in availableCycles" :key="c.id" :value="c.id">
                #{{ c.id }} · {{ c.zoneCode }} · {{ new Date(c.startAt).toLocaleString() }} · {{ c.waterLiters }} L
              </option>
            </select>
          </label>
        </div>
        <div class="actions" style="margin-top:12px">
          <button class="btn secondary" :disabled="!attachCycleId" @click="attach">挂入轮灌</button>
          <button class="btn" @click="seal">封账</button>
        </div>
        <p style="margin:8px 0 0;color:var(--muted)">
          封账条件：至少两笔轮灌，且各轮灌水量加总为正；不满足将拒绝（409）并保持未封账。
        </p>
      </template>
      <p v-if="detailError" class="error">{{ detailError }}</p>
    </div>
  </div>
</template>
