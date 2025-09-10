import { configureStore } from '@reduxjs/toolkit'
import { appSlice } from './appSlice'

export const store = configureStore({
  reducer: {
    app: appSlice.reducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: ['app/setRawBaseRows', 'app/setCurrentRows', 'app/setFilteredRows'],
        ignoredPaths: ['app.rawBaseRows', 'app.currentRows', 'app.filteredRows'],
      },
    }),
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch