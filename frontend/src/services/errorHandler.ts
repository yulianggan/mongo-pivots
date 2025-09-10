import { AppError } from '@/types'

export class ErrorHandler {
  static handle(error: unknown): AppError {
    if (error instanceof AppError) {
      return error
    }
    
    if (error instanceof Error) {
      return new AppError(error.message, 'UNKNOWN_ERROR')
    }
    
    if (typeof error === 'string') {
      return new AppError(error, 'UNKNOWN_ERROR')
    }
    
    return new AppError('发生未知错误', 'UNKNOWN_ERROR', error)
  }
  
  static getDisplayMessage(error: AppError): string {
    const errorMessages: Record<string, string> = {
      'NETWORK_ERROR': '网络连接失败，请检查网络设置',
      '404': '请求的资源未找到',
      '401': '身份验证失败',
      '403': '没有权限访问该资源',
      '500': '服务器内部错误',
      'TIMEOUT': '请求超时，请稍后重试',
      'UNKNOWN_ERROR': '发生未知错误',
    }
    
    return errorMessages[error.code || 'UNKNOWN_ERROR'] || error.message
  }
  
  static shouldRetry(error: AppError): boolean {
    const retryableCodes = ['NETWORK_ERROR', 'TIMEOUT', '500', '502', '503', '504']
    return retryableCodes.includes(error.code || '')
  }
  
  static logError(error: AppError, context?: string): void {
    const logData = {
      message: error.message,
      code: error.code,
      context: context || 'Unknown',
      details: error.details,
      timestamp: new Date().toISOString(),
      stack: error.stack,
    }
    
    // In a real app, send to logging service
    console.error('[ErrorHandler]', logData)
  }
}