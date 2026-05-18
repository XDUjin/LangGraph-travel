// 类型定义

export interface Location {
  longitude: number
  latitude: number
}

export interface Attraction {
  name: string
  address: string
  location: Location
  visit_duration: number
  description: string
  category?: string
  rating?: number
  image_url?: string
  ticket_price?: number
}

export interface Meal {
  type: 'breakfast' | 'lunch' | 'dinner' | 'snack'
  name: string
  address?: string
  location?: Location
  description?: string
  estimated_cost?: number
}

export interface Hotel {
  name: string
  address: string
  location?: Location
  price_range: string
  rating: string
  distance: string
  type: string
  estimated_cost?: number
}

export interface Budget {
  total_attractions: number
  total_hotels: number
  total_meals: number
  total_transportation: number
  total: number
}

export interface DayPlan {
  date: string
  day_index: number
  description: string
  transportation: string
  accommodation: string
  hotel?: Hotel
  attractions: Attraction[]
  meals: Meal[]
}

export interface WeatherInfo {
  date: string
  day_weather: string
  night_weather: string
  day_temp: number
  night_temp: number
  wind_direction: string
  wind_power: string
}

export interface TripPlan {
  city: string
  start_date: string
  end_date: string
  days: DayPlan[]
  weather_info: WeatherInfo[]
  overall_suggestions: string
  budget?: Budget
}

export interface TripFormData {
  city: string
  start_date: string
  end_date: string
  travel_days: number
  transportation: string
  accommodation: string
  preferences: string[]
  free_text_input: string
}

export interface TripPlanResponse {
  success: boolean
  message: string
  data?: TripPlan
}

// ---- 购票相关类型 ----

export interface BookingLink {
  platform: string
  platform_key: string
  url: string
  display_name: string
}

export interface TicketBookingItem {
  attraction_name: string
  city: string
  day_index: number
  needs_ticket: boolean
  estimated_price_min: number
  estimated_price_max: number
  ticket_type_note: string
  booking_links: BookingLink[]
  note: string
  free_reason?: string
}

export interface TicketBookingRequest {
  city: string
  trip_plan_summary: Array<{
    name: string
    city: string
    day_index: number
    category?: string
    ticket_price?: number
  }>
}

export interface TicketBookingResponse {
  success: boolean
  message: string
  items: TicketBookingItem[]
  total_min_cost: number
  total_max_cost: number
  paid_count: number
}

// ---- RAG 问答相关类型 ----

export interface RAGQueryRequest {
  question: string
}

export interface RAGSource {
  content: string
  source: string
}

export interface RAGQueryResponse {
  success: boolean
  message: string
  answer?: string
  sources: RAGSource[]
  intent: string
}

export interface RAGStatusResponse {
  status: string
  document_count: number
  chromadb_path: string
  collection_name: string
  embedding_model: string
  knowledge_base_path: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: RAGSource[]
  intent?: string
  timestamp: number
}

