import type { AppConfig, AppState } from '@/types'

interface StoredConfig {
  apiBase?: string
  collection?: string
  limit?: number
  skip?: number
  viewMode?: 'pivot' | 'raw'
  subtotalEnabled?: boolean
  iferrDefaultEnabled?: boolean
  iferrDefaultFallback?: number
}

const STORAGE_KEY = 'mongo-pivot-config'
const PROFILES_KEY = 'mongo-pivot-profiles'

export class ConfigService {
  static save(config: Partial<AppConfig>): void {
    try {
      const stored = this.load()
      const updated = { ...stored, ...config }
      localStorage.setItem(STORAGE_KEY, JSON.stringify(updated))
    } catch (error) {
      console.warn('Failed to save config to localStorage:', error)
    }
  }
  
  static load(): StoredConfig {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      return stored ? JSON.parse(stored) : {}
    } catch (error) {
      console.warn('Failed to load config from localStorage:', error)
      return {}
    }
  }
  
  static clear(): void {
    try {
      localStorage.removeItem(STORAGE_KEY)
    } catch (error) {
      console.warn('Failed to clear config from localStorage:', error)
    }
  }
  
  static saveProfile(name: string, state: Partial<AppState>): void {
    try {
      const profiles = this.getProfiles()
      profiles[name] = {
        ...state,
        timestamp: new Date().toISOString(),
      }
      localStorage.setItem(PROFILES_KEY, JSON.stringify(profiles))
    } catch (error) {
      console.warn('Failed to save profile:', error)
    }
  }
  
  static loadProfile(name: string): Partial<AppState> | null {
    try {
      const profiles = this.getProfiles()
      return profiles[name] || null
    } catch (error) {
      console.warn('Failed to load profile:', error)
      return null
    }
  }
  
  static deleteProfile(name: string): void {
    try {
      const profiles = this.getProfiles()
      delete profiles[name]
      localStorage.setItem(PROFILES_KEY, JSON.stringify(profiles))
    } catch (error) {
      console.warn('Failed to delete profile:', error)
    }
  }
  
  static getProfiles(): Record<string, any> {
    try {
      const stored = localStorage.getItem(PROFILES_KEY)
      return stored ? JSON.parse(stored) : {}
    } catch (error) {
      console.warn('Failed to load profiles:', error)
      return {}
    }
  }
  
  static listProfileNames(): string[] {
    const profiles = this.getProfiles()
    return Object.keys(profiles).sort()
  }
  
  static exportConfig(): string {
    const config = this.load()
    const profiles = this.getProfiles()
    const exportData = {
      config,
      profiles,
      exportedAt: new Date().toISOString(),
      version: '2.0.0',
    }
    return JSON.stringify(exportData, null, 2)
  }
  
  static importConfig(jsonData: string): boolean {
    try {
      const data = JSON.parse(jsonData)
      
      if (data.config) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data.config))
      }
      
      if (data.profiles) {
        localStorage.setItem(PROFILES_KEY, JSON.stringify(data.profiles))
      }
      
      return true
    } catch (error) {
      console.error('Failed to import config:', error)
      return false
    }
  }
  
  static getDefaultApiCandidates(): string[] {
    const candidates: string[] = []
    
    // From window config if available
    if (typeof window !== 'undefined' && (window as any).__APP_CONFIG__?.API_BASE) {
      candidates.push((window as any).__APP_CONFIG__.API_BASE)
    }
    
    // From saved config
    const saved = this.load()
    if (saved.apiBase) {
      candidates.push(saved.apiBase)
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