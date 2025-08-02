export interface HomeStats {
  num_accounts_connected: number
  num_accounts_registered: number
  num_accounts_registered_recent: number
  num_accounts_connected_recent: number
  num_characters: number
  num_rooms: number
  num_exits: number
  num_others: number
  page_title: string
  accounts_connected_recent: Array<{ username: string; last_login: string }>
}

export interface AccountData {
  id: number
  username: string
  display_name: string
  last_login: string | null
}

export interface LoginContext {
  site_name: string
  next: string
  user?: AccountData
}
