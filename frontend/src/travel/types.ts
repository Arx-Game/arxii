export interface TravelHub {
  id: number;
  name: string;
  description: string;
  travel_modes: string[];
  is_transit_stop: boolean;
  is_active: boolean;
}

export interface TravelMethod {
  id: number;
  name: string;
  description: string;
  travel_mode: string;
  base_speed: number;
  ship_type_id: number | null;
  is_default: boolean;
}

export interface VoyageParticipant {
  id: number;
  persona_id: number;
  persona_name: string;
  joined_at: string;
  left_at: string | null;
  legs_traveled: number;
}

export interface VoyageInvite {
  id: number;
  voyage_id: number;
  target_persona_id: number;
  target_persona_name: string;
  invited_by_id: number | null;
  invited_by_name: string | null;
  response: 'pending' | 'accepted' | 'declined';
  invited_at: string;
  responded_at: string | null;
  voyage_destination: string;
}

export interface Voyage {
  id: number;
  leader_id: number;
  leader_name: string;
  status: 'DRAFT' | 'IN_TRANSIT' | 'ARRIVED' | 'ABANDONED';
  origin_name: string;
  destination_name: string;
  travel_method_id: number;
  travel_method_name: string;
  current_leg_index: number;
  route_hubs: number[];
  participants: VoyageParticipant[];
  started_at: string;
  completed_at: string | null;
}
