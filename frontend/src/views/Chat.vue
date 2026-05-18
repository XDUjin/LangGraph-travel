<template>
  <div class="chat-container">
    <div class="chat-header">
      <a-button type="link" @click="goHome" style="padding: 0">
        <template #icon><span style="font-size: 16px">&larr;</span></template>
        返回首页
      </a-button>
      <h2 class="chat-title">旅行知识问答</h2>
      <a-tag v-if="ragStatus" :color="ragStatus.status === 'ready' ? 'green' : 'red'">
        知识库: {{ ragStatus.document_count }} 个文档块
      </a-tag>
    </div>

    <div class="chat-messages" ref="messagesContainer">
      <div v-if="messages.length === 0" class="welcome-section">
        <div class="welcome-icon">📚</div>
        <h3>旅行知识问答助手</h3>
        <p>基于旅行知识库的智能问答，试试问我：</p>
        <div class="suggestion-chips">
          <a-button
            v-for="suggestion in suggestions"
            :key="suggestion"
            size="small"
            class="suggestion-btn"
            @click="sendMessage(suggestion)"
          >
            {{ suggestion }}
          </a-button>
        </div>
      </div>

      <div
        v-for="msg in messages"
        :key="msg.id"
        :class="['message-row', msg.role === 'user' ? 'user-row' : 'assistant-row']"
      >
        <div :class="['message-bubble', msg.role]">
          <div class="message-content">{{ msg.content }}</div>
          <div v-if="msg.sources && msg.sources.length > 0" class="message-sources">
            <a-collapse size="small" :bordered="false">
              <a-collapse-panel header="参考来源" key="1">
                <div v-for="(src, i) in msg.sources" :key="i" class="source-item">
                  <a-tag color="blue">{{ formatSource(src.source) }}</a-tag>
                  <span class="source-text">{{ src.content }}...</span>
                </div>
              </a-collapse-panel>
            </a-collapse>
          </div>
          <div v-if="msg.intent" class="intent-tag">
            <a-tag v-if="msg.intent === 'travel_rag'" color="green">基于知识库回答</a-tag>
            <a-tag v-else color="default">通用回答</a-tag>
          </div>
        </div>
      </div>

      <div v-if="loading" class="message-row assistant-row">
        <div class="message-bubble assistant">
          <a-spin size="small" /> 正在思考...
        </div>
      </div>
    </div>

    <div class="chat-input-area">
      <a-input-group compact>
        <a-input
          v-model:value="inputValue"
          placeholder="输入你的旅行问题..."
          size="large"
          style="width: calc(100% - 80px)"
          :disabled="loading"
          @pressEnter="sendMessage"
          ref="inputRef"
        />
        <a-button
          type="primary"
          size="large"
          style="width: 80px"
          :loading="loading"
          :disabled="loading"
          @click="sendMessage"
        >
          发送
        </a-button>
      </a-input-group>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ragQuery, getRAGStatus } from '@/services/api'
import type { ChatMessage, RAGStatusResponse } from '@/types'

const router = useRouter()
const messages = ref<ChatMessage[]>([])
const inputValue = ref('')
const loading = ref(false)
const messagesContainer = ref<HTMLElement | null>(null)
const inputRef = ref<any>(null)
const ragStatus = ref<RAGStatusResponse | null>(null)

const suggestions = [
  '北京有哪些必去的景点？',
  '去成都旅游有什么美食推荐？',
  '一个人旅行需要注意什么？',
  '如何规划一次经济实惠的旅行？',
]

const goHome = () => router.push('/')

const scrollToBottom = () => {
  nextTick(() => {
    if (messagesContainer.value) {
      messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
    }
  })
}

const formatSource = (source: string): string => {
  const parts = source.replace(/\\/g, '/').split('/')
  return parts[parts.length - 1] || source
}

const sendMessage = async (text?: string | Event) => {
  const question = (typeof text === 'string' ? text : inputValue.value).trim()
  if (!question || loading.value) return

  const userMsg: ChatMessage = {
    id: Date.now().toString(),
    role: 'user',
    content: question,
    timestamp: Date.now(),
  }
  messages.value.push(userMsg)
  inputValue.value = ''
  await nextTick()
  inputRef.value?.focus()
  scrollToBottom()

  loading.value = true
  try {
    const response = await ragQuery(question)
    const assistantMsg: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: response.success ? (response.answer || '抱歉，无法生成回答') : response.message,
      sources: response.sources,
      intent: response.intent,
      timestamp: Date.now(),
    }
    messages.value.push(assistantMsg)
  } catch (error: any) {
    const errorMsg: ChatMessage = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: `抱歉，查询失败: ${error.message}`,
      timestamp: Date.now(),
    }
    messages.value.push(errorMsg)
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

onMounted(async () => {
  try {
    ragStatus.value = await getRAGStatus()
  } catch {
    // Non-critical, ignore
  }
})
</script>

<style scoped>
.chat-container {
  max-width: 900px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  height: calc(100vh - 160px);
}

.chat-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 16px 0;
  border-bottom: 1px solid #f0f0f0;
  margin-bottom: 16px;
}

.chat-title {
  margin: 0;
  font-size: 20px;
  flex: 1;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px 0;
}

.welcome-section {
  text-align: center;
  padding: 60px 20px;
}

.welcome-icon {
  font-size: 48px;
  margin-bottom: 16px;
}

.welcome-section h3 {
  font-size: 22px;
  color: #333;
  margin-bottom: 8px;
}

.welcome-section p {
  color: #666;
  margin-bottom: 24px;
}

.suggestion-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
}

.suggestion-btn {
  border-radius: 16px;
}

.message-row {
  display: flex;
  margin-bottom: 16px;
}

.user-row {
  justify-content: flex-end;
}

.assistant-row {
  justify-content: flex-start;
}

.message-bubble {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 12px;
  line-height: 1.6;
  word-break: break-word;
}

.message-bubble.user {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  border-bottom-right-radius: 4px;
}

.message-bubble.assistant {
  background: #f6f6f6;
  color: #333;
  border-bottom-left-radius: 4px;
}

.message-content {
  white-space: pre-wrap;
}

.message-sources {
  margin-top: 12px;
}

.intent-tag {
  margin-top: 8px;
  font-size: 12px;
}

.source-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 8px;
  font-size: 13px;
}

.source-text {
  color: #666;
  line-height: 1.4;
}

.chat-input-area {
  padding: 16px 0;
  border-top: 1px solid #f0f0f0;
}

:deep(.ant-input-search-button) {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-color: #667eea;
}

:deep(.ant-collapse-header) {
  font-size: 13px !important;
  padding: 4px 8px !important;
}

:deep(.ant-collapse-content-box) {
  padding: 8px !important;
}
</style>
