import { createSlice, PayloadAction } from '@reduxjs/toolkit';

export type DeepLinkKind = 'combo' | 'opponent' | 'participant' | 'condition' | 'clash';

export interface DeepLinkTarget {
  modal: DeepLinkKind;
  id: number;
}

interface DeepLinkModalState {
  current: DeepLinkTarget | null;
}

const initialState: DeepLinkModalState = {
  current: null,
};

export const deepLinkModalSlice = createSlice({
  name: 'deepLinkModal',
  initialState,
  reducers: {
    openDeepLink: (state, action: PayloadAction<DeepLinkTarget>) => {
      state.current = action.payload;
    },
    closeDeepLink: (state) => {
      state.current = null;
    },
  },
});

export const { openDeepLink, closeDeepLink } = deepLinkModalSlice.actions;
