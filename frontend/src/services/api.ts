import axios, { AxiosInstance, AxiosResponse } from 'axios'
import { 
  ApiHealthResponse, 
  ApiCollectionsResponse, 
  ApiDataResponse, 
  DataRow,
  AppError,
  CollectionInfo
} from '@/types'

class ApiService {
  private client: AxiosInstance

  constructor(baseUrl: string = 'http://localhost:8000') {
    this.client = axios.create({
      baseURL: baseUrl,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
      },
    })

    // Response interceptor for error handling
    this.client.interceptors.response.use(
      (response: AxiosResponse) => response,
      (error) => {
        const message = error.response?.data?.message || error.message || '网络请求失败'
        const code = error.response?.status?.toString() || 'NETWORK_ERROR'
        throw new AppError(message, code, error.response?.data)
      }
    )
  }

  setBaseUrl(baseUrl: string): void {
    this.client.defaults.baseURL = baseUrl
  }

  async checkHealth(): Promise<ApiHealthResponse> {
    const response = await this.client.get<ApiHealthResponse>('/api/health')
    return response.data
  }

  async getCollections(): Promise<string[]> {
    const response = await this.client.get<ApiCollectionsResponse>('/api/collections')
    
    if (!response.data?.success) {
      throw new AppError(response.data?.error || '获取集合列表失败')
    }
    
    // 将新的对象格式转换为字符串数组以保持向后兼容
    return response.data.collections.map((collection: CollectionInfo) => collection.name)
  }

  async getCollectionsWithInfo(): Promise<CollectionInfo[]> {
    const response = await this.client.get<ApiCollectionsResponse>('/api/collections')
    
    if (!response.data?.success) {
      throw new AppError(response.data?.error || '获取集合列表失败')
    }
    
    return response.data.collections
  }

  async getData(params: {
    collection: string
    limit?: number
    skip?: number
    filters?: Record<string, any>
  }): Promise<DataRow[]> {
    const response = await this.client.post<ApiDataResponse>('/api/data', {
      collection: params.collection,
      limit: params.limit || 5000,
      skip: params.skip || 0,
      filters: params.filters || {}
    })

    if (!response.data.success) {
      throw new AppError(response.data.message || '数据加载失败')
    }

    return response.data.data || []
  }

  async peekData(collection: string, limit = 50): Promise<DataRow[]> {
    return this.getData({ collection, limit, skip: 0 })
  }

  // Cloud configuration methods
  async saveCloudProfile(name: string, config: any): Promise<void> {
    await this.client.post('/api/profiles', { name, config })
  }

  async loadCloudProfile(name: string): Promise<any> {
    const response = await this.client.get(`/api/profiles/${name}`)
    return response.data
  }

  async listCloudProfiles(): Promise<string[]> {
    const response = await this.client.get('/api/profiles')
    return response.data?.profiles || []
  }

  // Test multiple API bases to find working one
  static async findWorkingApiBase(candidates: string[]): Promise<string | null> {
    for (const baseUrl of candidates) {
      try {
        const service = new ApiService(baseUrl)
        const health = await service.checkHealth()
        if (health?.status === 'ok') {
          return baseUrl
        }
      } catch {
        // Try next candidate
        continue
      }
    }
    return null
  }

  // Generate API base candidates
  static generateApiBaseCandidates(): string[] {
    const candidates: string[] = []
    
    // From window config if available
    if (typeof window !== 'undefined' && (window as any).__APP_CONFIG__?.API_BASE) {
      candidates.push((window as any).__APP_CONFIG__.API_BASE)
    }

    // Common development ports
    const host = typeof window !== 'undefined' 
      ? window.location.hostname || 'localhost' 
      : 'localhost'
    
    candidates.push(
      `http://${host}:7002`,
      `http://${host}:8000`,
      'http://localhost:7002',
      'http://localhost:8000'
    )

    // Remove duplicates
    return [...new Set(candidates)]
  }
}

// Create default instance
export const apiService = new ApiService()
export { ApiService }