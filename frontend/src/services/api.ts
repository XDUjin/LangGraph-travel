import axios from 'axios'
import type { TripFormData, TripPlanResponse, TicketBookingRequest, TicketBookingResponse, RAGQueryResponse, RAGStatusResponse } from '@/types'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 650000, // 约5.8分钟超时
  headers: {
    'Content-Type': 'application/json'
  }
})

// 请求拦截器
apiClient.interceptors.request.use(
  (config) => {
    console.log('发送请求:', config.method?.toUpperCase(), config.url)
    return config
  },
  (error) => {
    console.error('请求错误:', error)
    return Promise.reject(error)
  }
)

// 响应拦截器
apiClient.interceptors.response.use(
  (response) => {
    console.log('收到响应:', response.status, response.config.url)
    return response
  },
  (error) => {
    console.error('响应错误:', error.response?.status, error.message)
    return Promise.reject(error)
  }
)

/**
 * 生成旅行计划
 */
export async function generateTripPlan(formData: TripFormData): Promise<TripPlanResponse> {
  try {
    const response = await apiClient.post<TripPlanResponse>('/api/trip/plan', formData)
    return response.data
  } catch (error: any) {
    console.error('生成旅行计划失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '生成旅行计划失败')
  }
}

/**
 * 健康检查
 */
export async function healthCheck(): Promise<any> {
  try {
    const response = await apiClient.get('/health')
    return response.data
  } catch (error: any) {
    console.error('健康检查失败:', error)
    throw new Error(error.message || '健康检查失败')
  }
}

/**
 * 分析景点购票需求并获取各平台购票链接
 */
export async function bookTickets(request: TicketBookingRequest): Promise<TicketBookingResponse> {
  try {
    const response = await apiClient.post<TicketBookingResponse>('/api/trip/book-tickets', request)
    return response.data
  } catch (error: any) {
    console.error('购票分析失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '购票分析失败')
  }
}

/**
 * RAG 问答查询
 */
export async function ragQuery(question: string): Promise<RAGQueryResponse> {
  try {
    const response = await apiClient.post<RAGQueryResponse>('/api/rag/query', { question })
    return response.data
  } catch (error: any) {
    console.error('RAG 问答失败:', error)
    throw new Error(error.response?.data?.detail || error.message || 'RAG 问答失败')
  }
}

/**
 * 获取 RAG 服务状态
 */
export async function getRAGStatus(): Promise<RAGStatusResponse> {
  try {
    const response = await apiClient.get<RAGStatusResponse>('/api/rag/status')
    return response.data
  } catch (error: any) {
    console.error('获取 RAG 状态失败:', error)
    throw new Error(error.response?.data?.detail || error.message || '获取 RAG 状态失败')
  }
}

export default apiClient

