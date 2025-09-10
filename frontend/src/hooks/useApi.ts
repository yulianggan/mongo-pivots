import React from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiService } from '@/services/api'
import { useAppSelector, useAppDispatch } from './redux'
import { setRawBaseRows, setLoading, setError, setAvailableFields } from '@/store/appSlice'

export const useHealthCheck = () => {
  return useQuery({
    queryKey: ['health'],
    queryFn: () => apiService.checkHealth(),
    staleTime: 30 * 1000, // 30 seconds
  })
}

export const useCollections = () => {
  return useQuery({
    queryKey: ['collections'],
    queryFn: () => apiService.getCollections(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  })
}

export const useData = (collection: string, enabled = true) => {
  const { config } = useAppSelector((state) => state.app)
  const dispatch = useAppDispatch()
  
  const query = useQuery({
    queryKey: ['data', collection, config.limit, config.skip, config.filters],
    queryFn: () => apiService.getData({
      collection,
      limit: config.limit,
      skip: config.skip,
      filters: config.filters,
    }),
    enabled: enabled && !!collection,
  })

  // Handle success/error with useEffect-like pattern
  React.useEffect(() => {
    if (query.isSuccess && query.data) {
      dispatch(setRawBaseRows(query.data))
      dispatch(setLoading(false))
      
      // Extract field names from first row
      if (query.data.length > 0) {
        const fields = Object.keys(query.data[0])
        dispatch(setAvailableFields(fields))
      }
    }
    
    if (query.isError) {
      dispatch(setError(query.error?.message || 'Data loading failed'))
      dispatch(setLoading(false))
    }
    
    if (query.isLoading) {
      dispatch(setLoading(true))
    }
  }, [query.isSuccess, query.isError, query.isLoading, query.data, query.error, dispatch])

  return query
}

export const usePeekData = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: (collection: string) => apiService.peekData(collection, 50),
    onSuccess: (data, collection) => {
      // Update the main data query cache with preview data
      queryClient.setQueryData(['data', collection], data)
    },
  })
}

export const useCloudProfiles = () => {
  return useQuery({
    queryKey: ['cloud-profiles'],
    queryFn: () => apiService.listCloudProfiles(),
    staleTime: 2 * 60 * 1000, // 2 minutes
  })
}

export const useSaveCloudProfile = () => {
  const queryClient = useQueryClient()
  
  return useMutation({
    mutationFn: ({ name, config }: { name: string; config: unknown }) => 
      apiService.saveCloudProfile(name, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['cloud-profiles'] })
    },
  })
}

export const useLoadCloudProfile = () => {
  return useMutation({
    mutationFn: (name: string) => apiService.loadCloudProfile(name),
  })
}