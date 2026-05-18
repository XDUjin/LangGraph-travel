<template>
  <div class="ticket-booking-wrapper">
  <!-- 触发按钮 -->
  <a-button type="primary" class="ticket-button" @click="openModal" :disabled="!tripPlan">
    🎫 一键购票
  </a-button>

  <!-- 购票弹窗（使用显式绑定避免 ESLint vue/no-v-model-argument 误报） -->
  <a-modal
    :open="modalVisible"
    @update:open="setModalVisible"
    title="🎫 景点购票助手"
    :width="860"
    :footer="null"
    class="ticket-modal"
  >
    <!-- 加载状态 -->
    <div v-if="loading" class="loading-state">
      <a-spin size="large" />
      <p class="loading-text">AI 正在分析景点购票信息，请稍候...</p>
    </div>

    <!-- 错误状态 -->
    <a-alert v-else-if="error" type="error" :message="error" show-icon style="margin-bottom: 16px" />

    <!-- 结果展示 -->
    <div v-else-if="bookingData">
      <!-- 汇总栏 -->
      <div class="summary-bar">
        <div class="summary-item">
          <div class="summary-label">需要购票</div>
          <div class="summary-value paid">{{ bookingData.paid_count }} 处</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">免费景点</div>
          <div class="summary-value free">{{ bookingData.items.length - bookingData.paid_count }} 处</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">预估票价区间</div>
          <div class="summary-value price">
            ¥{{ bookingData.total_min_cost }} ~ ¥{{ bookingData.total_max_cost }}
          </div>
        </div>
        <a-button
          type="primary"
          danger
          :disabled="allPaidLinks.length === 0"
          @click="openAllLinks"
        >
          打开全部购票页 ({{ uniquePaidLinkCount }})
        </a-button>
      </div>

      <a-divider style="margin: 16px 0" />

      <!-- 逐景点列表 -->
      <div
        v-for="item in bookingData.items"
        :key="`${item.day_index}-${item.attraction_name}`"
        class="attraction-row"
        :class="item.needs_ticket ? 'needs-ticket' : 'is-free'"
      >
        <div class="row-header">
          <span class="day-badge">第 {{ item.day_index + 1 }} 天</span>
          <span class="attr-name">{{ item.attraction_name }}</span>
          <a-tag :color="item.needs_ticket ? 'red' : 'green'" class="price-tag">
            {{ item.needs_ticket
              ? (item.estimated_price_min === item.estimated_price_max
                  ? `¥${item.estimated_price_max}`
                  : `¥${item.estimated_price_min}~¥${item.estimated_price_max}`)
              : '免费' }}
          </a-tag>
        </div>

        <!-- 免费景点：显示原因 -->
        <p v-if="!item.needs_ticket && item.free_reason" class="free-reason">
          {{ item.free_reason }}
        </p>
        <!-- 免费但需注意 -->
        <p v-if="!item.needs_ticket && item.note" class="booking-note">
          ⚠️ {{ item.note }}
        </p>

        <!-- 收费景点：票种说明 + 购票注意 + 平台链接 -->
        <template v-if="item.needs_ticket">
          <p v-if="item.ticket_type_note" class="ticket-type-note">
            🎟️ {{ item.ticket_type_note }}
          </p>
          <p v-if="item.note" class="booking-note">
            ⚠️ {{ item.note }}
          </p>
          <div class="platform-links">
            <a
              v-for="link in item.booking_links"
              :key="link.platform_key"
              :href="link.url"
              target="_blank"
              rel="noopener noreferrer"
              :class="`platform-badge platform-${link.platform_key}`"
            >
              {{ link.display_name }}
            </a>
          </div>
        </template>
      </div>
    </div>

    <!-- 空状态（首次打开前） -->
    <div v-else class="empty-state">
      <p>点击"开始分析"获取购票信息</p>
    </div>
  </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { message } from 'ant-design-vue'
import type { TripPlan, TicketBookingResponse } from '@/types'
import { bookTickets } from '@/services/api'

const props = defineProps<{
  tripPlan: TripPlan | null
}>()

const modalVisible = ref(false)
const loading = ref(false)
const error = ref<string | null>(null)
const bookingData = ref<TicketBookingResponse | null>(null)

// 所有收费景点的购票链接（用于"打开全部"）
const allPaidLinks = computed(() => {
  if (!bookingData.value) return []
  return bookingData.value.items
    .filter(item => item.needs_ticket)
    .flatMap(item => item.booking_links)
})

// 去重后的链接数（同一URL只算一次）
const uniquePaidLinkCount = computed(() => {
  const seen = new Set(allPaidLinks.value.map(l => l.url))
  return seen.size
})

const openModal = async () => {
  if (!props.tripPlan) return
  modalVisible.value = true

  // 已有数据则不重复请求
  if (bookingData.value) return

  loading.value = true
  error.value = null

  try {
    const attractionSummary = props.tripPlan.days.flatMap(day =>
      day.attractions.map(attr => ({
        name: attr.name,
        city: props.tripPlan!.city,
        day_index: day.day_index,
        category: attr.category,
        ticket_price: attr.ticket_price,
      }))
    )

    bookingData.value = await bookTickets({
      city: props.tripPlan.city,
      trip_plan_summary: attractionSummary,
    })
  } catch (err: any) {
    error.value = err.message || '购票分析失败，请重试'
    message.error('购票分析失败')
  } finally {
    loading.value = false
  }
}

const setModalVisible = (v: boolean) => { modalVisible.value = v }

const openAllLinks = () => {
  const seen = new Set<string>()
  allPaidLinks.value.forEach(link => {
    if (!seen.has(link.url)) {
      seen.add(link.url)
      window.open(link.url, '_blank', 'noopener,noreferrer')
    }
  })
  message.success(`已在新标签页打开 ${seen.size} 个购票链接`)
}
</script>

<style scoped>
/* 包裹层不影响布局 */
.ticket-booking-wrapper {
  display: contents;
}

/* 触发按钮 */
.ticket-button {
  background: linear-gradient(135deg, #f5a623 0%, #e8750a 100%);
  border: none;
  font-weight: 600;
}

/* 加载状态 */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 48px 0;
  gap: 20px;
}

.loading-text {
  color: #666;
  font-size: 15px;
  margin: 0;
}

/* 汇总栏 */
.summary-bar {
  display: flex;
  align-items: center;
  gap: 32px;
  padding: 16px 20px;
  background: linear-gradient(135deg, #f5f7fa 0%, #fff 100%);
  border-radius: 10px;
  border: 1px solid #e8e8e8;
  flex-wrap: wrap;
}

.summary-item {
  text-align: center;
}

.summary-label {
  font-size: 12px;
  color: #888;
  margin-bottom: 4px;
}

.summary-value {
  font-size: 22px;
  font-weight: 700;
}

.summary-value.paid  { color: #ff4d4f; }
.summary-value.free  { color: #52c41a; }
.summary-value.price { color: #fa8c16; font-size: 18px; }

/* 景点行 */
.attraction-row {
  padding: 14px 16px;
  border-radius: 8px;
  border: 1px solid #e8e8e8;
  margin-bottom: 12px;
  border-left-width: 4px;
}

.needs-ticket { border-left-color: #ff4d4f; background: #fff8f8; }
.is-free      { border-left-color: #52c41a; background: #f6ffed; }

.row-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.day-badge {
  font-size: 12px;
  padding: 2px 10px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  border-radius: 10px;
  white-space: nowrap;
}

.attr-name {
  font-size: 16px;
  font-weight: 600;
  flex: 1;
  color: #333;
}

.price-tag {
  font-weight: 600;
  font-size: 14px;
}

.free-reason,
.ticket-type-note,
.booking-note {
  font-size: 13px;
  margin: 4px 0 6px;
  color: #555;
  line-height: 1.5;
}

.booking-note { color: #d46b08; }

/* 平台购票按钮 */
.platform-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 8px;
}

.platform-badge {
  display: inline-flex;
  align-items: center;
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: opacity 0.2s, transform 0.15s;
  cursor: pointer;
}

.platform-badge:hover {
  opacity: 0.85;
  transform: translateY(-1px);
}

.platform-ctrip      { background: #ff7d00; color: #fff; }
.platform-meituan    { background: #ffc300; color: #333; }
.platform-tongcheng  { background: #1677ff; color: #fff; }
.platform-baidu      { background: #2932e1; color: #fff; }

.empty-state {
  text-align: center;
  padding: 40px 0;
  color: #999;
}
</style>
