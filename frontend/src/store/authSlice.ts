import { createSlice, PayloadAction } from '@reduxjs/toolkit'
import type { AccountData } from '../evennia_replacements/types'

interface AuthState {
  account: AccountData | null
}

const initialState: AuthState = {
  account: null,
}

export const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    setAccount: (state, action: PayloadAction<AccountData | null>) => {
      state.account = action.payload
    },
  },
})

export const { setAccount } = authSlice.actions
