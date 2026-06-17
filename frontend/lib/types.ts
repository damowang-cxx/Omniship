export type UserRole = "admin" | "user";
export type UserStatus = "active" | "disabled";

export interface AppUser {
  id: string;
  email: string;
  username: string;
  role: UserRole;
  status: UserStatus;
  lastLoginAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AuthUserResponse {
  user: AppUser;
}

export interface UserListResponse {
  items: AppUser[];
}

export interface UserCreateRequest {
  email: string;
  username: string;
  password: string;
}

export type ShipmentType = "Air" | "Road" | "Train";
export type WaybillUploadStatus = "pending_review" | "approved" | "rejected";
export type WaybillTrackingStatus =
  | "created"
  | "noa_received"
  | "received"
  | "ready_to_scan"
  | "scanning"
  | "pending_clearance"
  | "cleared"
  | "partial_inbound"
  | "inbound"
  | "partial_outbound"
  | "outbound";
export type WaybillFycoStatus = "released" | "fyco";
export type WaybillParcelStatus =
  | "created"
  | "pending_check"
  | "inspection"
  | "released"
  | "temporary_released"
  | "exception"
  | "confiscated"
  | "destroyed"
  | "on_hold"
  | "inbound"
  | "outbound";

export interface WaybillPreAlertUploadPayload {
  shipmentType: ShipmentType;
  airWaybillNumber: string;
  grossWeightKg: string;
  pieces: string;
  arrivalFlightNumber?: string;
  airportOfDeparture: string;
  airportOfArrival: string;
  targetUserId?: string;
  airWaybillDocuments: File[];
  preAlertFile: File;
}

export interface WaybillPreAlertUploadResponse {
  uploadId: string;
  airWaybillNumber: string;
  airportOfDeparture: string;
  airportOfArrival: string;
  status: WaybillUploadStatus;
  boundUserId: string;
}

export interface WaybillUploadFileItem {
  id: string;
  fileKind: "air_waybill_document" | "customer_pre_alert" | string;
  originalFilename: string;
  contentType?: string | null;
  sizeBytes: number;
  sha256: string;
  createdAt: string;
}

export interface WaybillUploadUserItem {
  id: string;
  email: string;
  username: string;
}

export interface WaybillUploadItem {
  id: string;
  userId: string;
  uploadedByUserId?: string | null;
  shipmentType: ShipmentType;
  airWaybillNumber: string;
  grossWeightKg: string;
  pieces: number;
  arrivalFlightNumber?: string | null;
  airportOfDeparture?: string | null;
  airportOfArrival?: string | null;
  status: WaybillUploadStatus;
  reviewedByUserId?: string | null;
  reviewedAt?: string | null;
  createdAt: string;
  updatedAt: string;
  user?: WaybillUploadUserItem | null;
  uploadedBy?: WaybillUploadUserItem | null;
  files: WaybillUploadFileItem[];
}

export interface WaybillUploadListResponse {
  items: WaybillUploadItem[];
}

export interface WaybillUploadFilters {
  userId?: string;
  status?: WaybillUploadStatus | "";
  q?: string;
}

export interface WaybillUploadDeleteResponse {
  status: "deleted";
  uploadId: string;
}

export interface WaybillPodFileItem {
  id: string;
  originalFilename: string;
  contentType?: string | null;
  sizeBytes: number;
  createdAt: string;
}

export interface WaybillPodDeleteResponse {
  status: "deleted";
  podFileId: string;
}

export interface WaybillParcelItem {
  id: string;
  parcelUnitNumber: string;
  status: WaybillParcelStatus;
  numberOfItems: number;
  weightKg: string;
  destinationRaw?: string | null;
  destinationCode?: string | null;
  destinationName?: string | null;
  inbound: boolean;
  outbound: boolean;
  specialInstruction: boolean;
  createdAt: string;
  updatedAt: string;
}

export interface WaybillParcelListResponse {
  items: WaybillParcelItem[];
}

export interface WaybillParcelBulkUpdatePayload {
  parcelIds: string[];
  status?: WaybillParcelStatus;
  inbound?: boolean;
  outbound?: boolean;
  specialInstruction?: boolean;
}

export interface WaybillItem {
  id: string;
  publicCode: string;
  uploadId: string;
  userId: string;
  number: string;
  status: WaybillTrackingStatus;
  airportOfDeparture?: string | null;
  airportOfArrival?: string | null;
  statusChangedAt: string;
  weightKg: string;
  pieces: number;
  receivedCount: number;
  receivedTotal: number;
  inWarehouseCount: number;
  palletCount: number;
  fycoStatus?: WaybillFycoStatus | null;
  releasedCount: number;
  outboundCount: number;
  noaAt?: string | null;
  collectionAt?: string | null;
  scannedAt?: string | null;
  customsClearanceAt?: string | null;
  outboundAt?: string | null;
  createdAt: string;
  updatedAt: string;
  user?: WaybillUploadUserItem | null;
  podFiles: WaybillPodFileItem[];
}

export interface WaybillListResponse {
  items: WaybillItem[];
}

export interface WaybillFilters {
  userId?: string;
  status?: WaybillTrackingStatus | "";
  q?: string;
}

export interface WaybillUpdatePayload {
  status?: WaybillTrackingStatus;
  receivedCount?: number;
  receivedTotal?: number;
  inWarehouseCount?: number;
  palletCount?: number;
  fycoStatus?: WaybillFycoStatus | null;
  releasedCount?: number;
  outboundCount?: number;
  noaAt?: string | null;
  collectionAt?: string | null;
  scannedAt?: string | null;
  customsClearanceAt?: string | null;
  outboundAt?: string | null;
}
