/**
 * 澶氭暟鎹簮鍚屾鐩稿叧API
 */
import { ApiClient } from './request'

// 鏁版嵁婧愮姸鎬佹帴鍙?export interface DataSourceStatus {
  name: string
  priority: number
  available: boolean
  description: string
  token_source?: 'database' | 'env'  // Token 鏉ユ簮锛堜粎 Tushare锛?}

// 鍚屾鐘舵€佹帴鍙?export interface SyncStatus {
  job: string
  status: 'idle' | 'running' | 'success' | 'success_with_errors' | 'failed' | 'never_run'
  started_at?: string
  finished_at?: string
  total: number
  inserted: number
  updated: number
  errors: number
  last_trade_date?: string
  data_sources_used: string[]
  source_stats?: Record<string, Record<string, number>>
  message?: string
}

// 鍚屾璇锋眰鍙傛暟
export interface SyncRequest {
  force?: boolean
  preferred_sources?: string[]
}

// API鍝嶅簲鏍煎紡
export interface ApiResponse<T = any> {
  success: boolean
  message: string
  data: T
}

// 鍩虹娴嬭瘯缁撴灉鎺ュ彛
export interface BaseTestResult {
  success: boolean
  message: string
  count?: number
  date?: string
}

// 娴嬭瘯缁撴灉鎺ュ彛锛堢畝鍖栫増锛?export interface DataSourceTestResult {
  name: string
  priority: number
  available: boolean
  message: string
  token_source?: 'database' | 'env'  // Token 鏉ユ簮锛堜粎 Tushare锛?}

// 浣跨敤寤鸿鎺ュ彛
export interface SyncRecommendations {
  primary_source?: {
    name: string
    priority: number
    reason: string
  }
  fallback_sources: Array<{
    name: string
    priority: number
  }>
  suggestions: string[]
  warnings: string[]
}

/**
 * 鑾峰彇鏁版嵁婧愮姸鎬? */
export const getDataSourcesStatus = (): Promise<ApiResponse<DataSourceStatus[]>> => {
  return ApiClient.get('/api/multi-source-sync/sources/status')
}

/**
 * 鑾峰彇褰撳墠姝ｅ湪浣跨敤鐨勬暟鎹簮
 */
export const getCurrentDataSource = (): Promise<ApiResponse<{
  name: string
  priority: number
  description: string
  token_source?: 'database' | 'env'
  token_source_display?: string
}>> => {
  return ApiClient.get('/api/multi-source-sync/sources/current')
}

/**
 * 鑾峰彇鍚屾鐘舵€? */
export const getSyncStatus = (): Promise<ApiResponse<SyncStatus>> => {
  return ApiClient.get('/api/multi-source-sync/status')
}

/**
 * 杩愯鑲＄エ鍩虹淇℃伅鍚屾
 */
export const runStockBasicsSync = (params?: {
  force?: boolean
  preferred_sources?: string
}): Promise<ApiResponse<SyncStatus>> => {
  const queryParams = new URLSearchParams()
  if (params?.force) {
    queryParams.append('force', 'true')
  }
  if (params?.preferred_sources) {
    queryParams.append('preferred_sources', params.preferred_sources)
  }

  const url = `/api/multi-source-sync/stock_basics/run${queryParams.toString() ? '?' + queryParams.toString() : ''}`
  return ApiClient.post(url, undefined, {
    timeout: 600000 // 馃敟 鍚屾鎿嶄綔闇€瑕佹洿闀挎椂闂达紝璁剧疆涓?0鍒嗛挓锛圔aoStock闇€瑕侀€愪釜鑾峰彇浼板€兼暟鎹級
  })
}

/**
 * 娴嬭瘯鏁版嵁婧愯繛鎺? * @param sourceName - 鍙€夛紝鎸囧畾瑕佹祴璇曠殑鏁版嵁婧愬悕绉般€傚鏋滀笉鎸囧畾锛屽垯娴嬭瘯鎵€鏈夋暟鎹簮
 */
export const testDataSources = (sourceName?: string): Promise<ApiResponse<{ test_results: DataSourceTestResult[] }>> => {
  const params = sourceName ? { source_name: sourceName } : {}
  return ApiClient.post('/api/multi-source-sync/test-sources', params, {
    timeout: 15000 // 鍗曚釜鏁版嵁婧愭祴璇曡秴鏃?5绉掞紝澶氫釜鏁版嵁婧愭渶澶?0绉?  })
}

/**
 * 鑾峰彇鍚屾寤鸿
 */
export const getSyncRecommendations = (): Promise<ApiResponse<SyncRecommendations>> => {
  return ApiClient.get('/api/multi-source-sync/recommendations')
}

/**
 * 鑾峰彇鍚屾鍘嗗彶璁板綍
 */
export const getSyncHistory = (params?: {
  page?: number
  page_size?: number
  status?: string
}): Promise<ApiResponse<{
  records: SyncStatus[]
  total: number
  page: number
  page_size: number
  has_more: boolean
}>> => {
  const queryParams = new URLSearchParams()
  if (params?.page) {
    queryParams.append('page', params.page.toString())
  }
  if (params?.page_size) {
    queryParams.append('page_size', params.page_size.toString())
  }
  if (params?.status) {
    queryParams.append('status', params.status)
  }

  const url = `/api/multi-source-sync/history${queryParams.toString() ? '?' + queryParams.toString() : ''}`
  return ApiClient.get(url)
}

/**
 * 娓呯┖鍚屾缂撳瓨
 */
export const clearSyncCache = (): Promise<ApiResponse<{ cleared: boolean }>> => {
  return ApiClient.delete('/api/multi-source-sync/cache')
}

// 浼犵粺鍗曚竴鏁版嵁婧愬悓姝PI锛堜繚鎸佸吋瀹规€э級
export const runSingleSourceSync = (): Promise<ApiResponse<any>> => {
  return ApiClient.post('/api/sync/stock_basics/run')
}

export const getSingleSourceSyncStatus = (): Promise<ApiResponse<any>> => {
  return ApiClient.get('/api/sync/stock_basics/status')
}
