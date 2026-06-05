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

export interface WaybillPreAlertUploadPayload {
  shipmentType: ShipmentType;
  airWaybillNumber: string;
  grossWeightKg: string;
  pieces: string;
  arrivalFlightNumber?: string;
  targetUserId?: string;
  airWaybillDocuments: File[];
  preAlertFile: File;
}

export interface WaybillPreAlertUploadResponse {
  uploadId: string;
  airWaybillNumber: string;
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
  status: WaybillUploadStatus;
  reviewedByUserId?: string | null;
  reviewedAt?: string | null;
  createdAt: string;
  updatedAt: string;
  user?: WaybillUploadUserItem | null;
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
