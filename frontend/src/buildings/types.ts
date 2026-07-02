import type { components } from '@/generated/api';

export type BuildingManagerPayload = components['schemas']['BuildingManager'];
export type ManagerBuilding = components['schemas']['BuildingManager']['building'];
export type ManagerRoom = components['schemas']['BuildingManager']['rooms'][number];
export type ManagerExit = components['schemas']['BuildingManager']['exits'][number];
export type ManagerTenancy = ManagerRoom['tenancies'][number];
export type ForRoomResult = components['schemas']['ForRoomResult'];
export type RoomSizeTier = components['schemas']['RoomSizeTier'];
export type DecorationTemplate = components['schemas']['DecorationTemplate'];
export type PaginatedRoomSizeTierList = components['schemas']['PaginatedRoomSizeTierList'];
export type PaginatedDecorationTemplateList =
  components['schemas']['PaginatedDecorationTemplateList'];

/** Registry keys of the Room Builder actions this surface dispatches. */
export type RoomBuilderActionKey =
  | 'edit_room'
  | 'dig_room'
  | 'resize_room'
  | 'remove_room'
  | 'link_rooms'
  | 'unlink_rooms'
  | 'rename_exit'
  | 'place_room'
  | 'assign_room_tenant'
  | 'end_room_tenancy'
  | 'set_primary_home'
  | 'commission_decoration'
  | 'start_building_extension';
